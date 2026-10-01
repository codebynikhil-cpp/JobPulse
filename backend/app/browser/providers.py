import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol
from urllib.parse import urlsplit

import httpx
from playwright.async_api import Browser, Page, async_playwright

from app.browser.security import BrowserURLPolicy
from app.sources.base import SourceError

logger = logging.getLogger(__name__)


class BrowserProvider(Protocol):
    def page(
        self, policy: BrowserURLPolicy, *, timeout_ms: int
    ) -> AbstractAsyncContextManager[Page]: ...


@asynccontextmanager
async def guarded_page(browser: Browser, policy: BrowserURLPolicy, timeout_ms: int):
    context = await browser.new_context(service_workers="block", accept_downloads=False)
    blocked = []

    async def guard(route):
        try:
            await policy.validate(route.request.url)
        except SourceError:
            blocked.append(True)
            await route.abort()
        else:
            await route.continue_()

    async def block_socket(socket):
        blocked.append(True)
        await socket.close()

    try:
        await context.route("**/*", guard)
        await context.route_web_socket("**/*", block_socket)
        page = await context.new_page()
        page.set_default_timeout(timeout_ms)
        page.set_default_navigation_timeout(timeout_ms)
        # Browser adapters use one page only. Popups are never followed automatically.
        context.on("page", lambda popup: asyncio.create_task(popup.close()))
        yield page
        if blocked:
            raise SourceError("Browser source attempted a blocked destination")
    finally:
        await context.close()


class LocalPlaywrightProvider:
    def __init__(self, *, max_sessions: int = 1, chromium_sandbox: bool = True):
        if max_sessions < 1:
            raise ValueError("Browser capacity must be positive")
        self._capacity = asyncio.Semaphore(max_sessions)
        self.chromium_sandbox = chromium_sandbox

    @asynccontextmanager
    async def page(self, policy: BrowserURLPolicy, *, timeout_ms: int) -> AsyncIterator[Page]:
        async with self._capacity, async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True, chromium_sandbox=self.chromium_sandbox, timeout=timeout_ms
            )
            try:
                async with guarded_page(browser, policy, timeout_ms) as page:
                    yield page
            finally:
                await browser.close()


class BrowserbasePlaywrightProvider:
    def __init__(
        self,
        api_key: str,
        project_id: str,
        *,
        max_sessions: int = 1,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if not api_key or not project_id or max_sessions < 1:
            raise ValueError("Browserbase requires credentials and positive capacity")
        self._api_key, self._project_id = api_key, project_id
        self._capacity = asyncio.Semaphore(max_sessions)
        self._transport = transport

    @asynccontextmanager
    async def page(self, policy: BrowserURLPolicy, *, timeout_ms: int) -> AsyncIterator[Page]:
        async with (
            self._capacity,
            httpx.AsyncClient(
                base_url="https://api.browserbase.com",
                headers={"X-BB-API-Key": self._api_key},
                transport=self._transport,
                timeout=15,
                trust_env=False,
                follow_redirects=False,
            ) as client,
        ):
            session_id = None
            browser = None
            try:
                response = await client.post(
                    "/v1/sessions",
                    json={
                        "projectId": self._project_id,
                        "keepAlive": False,
                        "timeout": 120,
                        "browserSettings": {
                            "solveCaptchas": False,
                            "advancedStealth": False,
                            "recordSession": False,
                            "logSession": False,
                            "allowedDomains": sorted(policy.allowed_hosts),
                        },
                    },
                )
                response.raise_for_status()
                data = response.json()
                session_id = str(uuid.UUID(data["id"]))
                endpoint = data["connectUrl"]
                url = urlsplit(endpoint)
                if (
                    url.scheme != "wss"
                    or not url.hostname
                    or not (
                        url.hostname == "connect.browserbase.com"
                        or url.hostname.endswith(".browserbase.com")
                    )
                    or url.username
                    or url.password
                    or url.port not in (None, 443)
                ):
                    raise SourceError("Browserbase returned an invalid connection endpoint")
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.connect_over_cdp(
                        endpoint, timeout=timeout_ms
                    )
                    try:
                        async with guarded_page(browser, policy, timeout_ms) as page:
                            yield page
                    finally:
                        await browser.close()
            except Exception:
                # CDP errors/URLs can contain credentials; expose only a stable safe error.
                raise SourceError("Browserbase browser operation failed") from None
            finally:
                if session_id is not None:
                    try:
                        release = await client.post(
                            f"/v1/sessions/{session_id}", json={"status": "REQUEST_RELEASE"}
                        )
                        release.raise_for_status()
                    except Exception as exc:
                        logger.error(
                            "Browserbase session release failed",
                            extra={"error_type": type(exc).__name__},
                        )
                        raise SourceError("Browserbase session release failed") from None


def configured_provider() -> BrowserProvider:
    from app.core.config import settings

    if settings.browser_provider == "local":
        return LocalPlaywrightProvider(max_sessions=settings.browser_max_sessions)
    return BrowserbasePlaywrightProvider(
        settings.browserbase_api_key.get_secret_value(),
        settings.browserbase_project_id,
        max_sessions=settings.browser_max_sessions,
    )
