import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.browser import providers
from app.browser.providers import BrowserbasePlaywrightProvider
from app.browser.security import BrowserURLPolicy
from app.sources.base import SourceError


def mocked_browser(monkeypatch, *, connection_failure=False):
    page = Mock()
    context = SimpleNamespace(
        route=AsyncMock(),
        route_web_socket=AsyncMock(),
        new_page=AsyncMock(return_value=page),
        on=Mock(),
        close=AsyncMock(),
    )
    browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
    connect = AsyncMock(
        side_effect=RuntimeError("secret-CDP-url") if connection_failure else None,
        return_value=browser,
    )

    @asynccontextmanager
    async def playwright():
        yield SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=connect))

    monkeypatch.setattr(providers, "async_playwright", playwright)
    return browser, context, page, connect


@pytest.mark.parametrize("fail_at", [None, "connect", "page"])
def test_browserbase_protocol_create_connect_release_without_live_account(monkeypatch, fail_at):
    browser, context, page, connect = mocked_browser(
        monkeypatch, connection_failure=fail_at == "connect"
    )
    seen = []
    sid = str(uuid.uuid4())

    def handle(request):
        seen.append((request.url.path, json.loads(request.content)))
        assert request.headers["X-BB-API-Key"] == "test-secret"
        if request.url.path.endswith(sid):
            return httpx.Response(200, json={"status": "COMPLETED"})
        return httpx.Response(
            201, json={"id": sid, "connectUrl": "wss://connect.browserbase.com?apiKey=test-secret"}
        )

    provider = BrowserbasePlaywrightProvider(
        "test-secret", "project", transport=httpx.MockTransport(handle)
    )

    async def scenario():
        async with provider.page(
            BrowserURLPolicy(frozenset({"example.com"})), timeout_ms=1000
        ) as opened:
            assert opened is page
            if fail_at == "page":
                raise ValueError("secret-content")

    if fail_at:
        with pytest.raises(SourceError) as error:
            asyncio.run(scenario())
        assert "secret" not in str(error.value)
    else:
        asyncio.run(scenario())
    assert seen[-1] == ("/v1/sessions/" + sid, {"status": "REQUEST_RELEASE"})
    assert seen[0][1]["browserSettings"]["solveCaptchas"] is False
    assert seen[0][1]["browserSettings"]["advancedStealth"] is False
    assert seen[0][1]["keepAlive"] is False
    if fail_at != "connect":
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()


@pytest.mark.parametrize(
    "endpoint",
    [
        "ws://connect.browserbase.com",
        "wss://evil.example",
        "wss://browserbase.com.evil.example",
        "wss://user:pass@connect.browserbase.com",
        "wss://connect.browserbase.com:123",
    ],
)
def test_browserbase_rejects_invalid_cdp_and_still_releases(monkeypatch, endpoint):
    _, _, _, connect = mocked_browser(monkeypatch)
    seen = []
    sid = str(uuid.uuid4())

    def handle(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={"id": sid, "connectUrl": endpoint})

    provider = BrowserbasePlaywrightProvider(
        "test-secret", "project", transport=httpx.MockTransport(handle)
    )

    async def scenario():
        async with provider.page(BrowserURLPolicy(frozenset({"example.com"})), timeout_ms=1000):
            pytest.fail("Invalid endpoint must not yield a page")

    with pytest.raises(SourceError):
        asyncio.run(scenario())
    connect.assert_not_awaited()
    assert seen[-1] == "/v1/sessions/" + sid


def test_browserbase_missing_credentials_fail_without_request():
    with pytest.raises(ValueError):
        BrowserbasePlaywrightProvider("", "")


def test_guarded_page_blocked_request_not_success(monkeypatch):
    browser, context, _, _ = mocked_browser(monkeypatch)

    async def scenario():
        async with providers.guarded_page(
            browser, BrowserURLPolicy(frozenset({"example.com"})), 1000
        ):
            handler = context.route.call_args.args[1]
            route = SimpleNamespace(
                request=SimpleNamespace(url="http://127.0.0.1/"),
                abort=AsyncMock(),
                continue_=AsyncMock(),
            )
            await handler(route)
            route.abort.assert_awaited_once()
            route.continue_.assert_not_awaited()

    with pytest.raises(SourceError, match="blocked destination"):
        asyncio.run(scenario())
    context.close.assert_awaited_once()


def test_browserbase_session_capacity_and_cancellation_release(monkeypatch):
    mocked_browser(monkeypatch)
    seen = []
    sid = str(uuid.uuid4())

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={"id": sid, "connectUrl": "wss://connect.browserbase.com"})

    provider = BrowserbasePlaywrightProvider(
        "test-secret", "project", max_sessions=1, transport=httpx.MockTransport(handler)
    )

    async def scenario():
        entered = asyncio.Event()

        async def hold():
            async with provider.page(BrowserURLPolicy(frozenset({"example.com"})), timeout_ms=1000):
                entered.set()
                await asyncio.Event().wait()

        first = asyncio.create_task(hold())
        await entered.wait()
        second = asyncio.create_task(hold())
        await asyncio.sleep(0)
        assert seen == ["/v1/sessions"]
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        for _ in range(20):
            if seen.count("/v1/sessions") == 2:
                break
            await asyncio.sleep(0)
        assert seen.count("/v1/sessions") == 2
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second

    asyncio.run(scenario())
    assert seen.count("/v1/sessions/" + sid) == 2
