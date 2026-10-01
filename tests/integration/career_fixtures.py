"""Local deterministic career sites and adapters. Never registered in production."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from app.browser.providers import LocalPlaywrightProvider
from app.browser.security import BrowserURLPolicy
from app.core.catalog import SourceType
from app.sources.base import HealthResult, RawJob, SourceError
from app.sources.browser import BrowserSourceAdapter, BrowserSourceConfig
from app.sources.registry import AdapterRegistration, AdapterRegistry

HTML = (Path(__file__).parents[1] / "fixtures" / "career_sites" / "company_a.html").read_bytes()


@pytest.fixture
def career_sites():
    state = {"description": "Python"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            mode = query.get("mode", ["pages"])[0]
            code, kind = 200, "application/json"
            if parsed.path == "/a/careers":
                code = 503 if mode == "failure" else 200
                kind, body = "text/html", HTML
            elif parsed.path == "/a/data":
                page = int(query.get("page", ["1"])[0])
                ids = ["1", "2"] if page == 1 else ["3"]
                if mode in ("duplicate", "conflict") and page == 2:
                    ids = ["2", "3"]
                jobs = [
                    {
                        "id": identity,
                        "title": "Software Engineer",
                        "description": state.get(identity, state["description"]),
                        "url": origin + "/a/jobs/" + identity,
                    }
                    for identity in ids
                ]
                if mode == "malformed" and page == 1 or mode == "partial" and page == 2:
                    jobs[-1]["title"] = ""
                if mode == "conflict" and page == 2:
                    jobs[0]["title"] = "Changed conflict"
                if mode == "badurl":
                    jobs[0]["url"] = "http://169.254.169.254/metadata"
                body = json.dumps({"jobs": jobs, "more": page == 1 or mode == "endless"}).encode()
            elif parsed.path == "/b/jobs.json":
                body = json.dumps(
                    {
                        "jobs": [
                            {
                                "id": "b1",
                                "title": "Software Engineer",
                                "description": state.get("b1", state["description"]),
                                "url": origin + "/b/jobs/1",
                            }
                        ]
                    }
                ).encode()
            else:
                code, body = 404, b"{}"
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    origin = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield origin, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class FixtureOnlyPolicy(BrowserURLPolicy):
    def __init__(self, origin):
        super().__init__(frozenset({"127.0.0.1"}))
        self.origin = origin

    async def validate(self, url):
        value = urlsplit(url)
        if value.scheme + "://" + value.netloc != self.origin or value.username or value.password:
            raise SourceError("Test browser attempted to leave local fixture origin")


class FixtureCompanyBrowser(BrowserSourceAdapter):
    def __init__(self, origin, *, mode="pages", max_pages=4, timeout_ms=3000):
        super().__init__(
            BrowserSourceConfig(
                origin + "/a/careers?mode=" + mode,
                "body[data-ready]",
                timeout_ms=timeout_ms,
                max_pages=max_pages,
            ),
            LocalPlaywrightProvider(chromium_sandbox=False),
            FixtureOnlyPolicy(origin),
        )
        self.requests = []

    async def prepare_page(self, page):
        page.on("request", lambda request: self.requests.append(urlsplit(request.url).path))

    async def extract_jobs(self, page):
        records = []
        for row in await page.locator("article").all():
            link = row.locator("a.title")
            if await link.count() != 1:
                raise SourceError("Fixture DOM changed: title link missing")
            records.append(
                RawJob(
                    await row.get_attribute("data-id"),
                    await link.inner_text(),
                    await row.locator("p").inner_text(),
                    "",
                    await link.get_attribute("href"),
                )
            )
        return records

    async def advance(self, page):
        button = page.locator("button:visible").first
        if await page.locator("button:visible").count() == 0:
            return False
        previous = await page.locator("body").get_attribute("data-ready")
        await button.click()
        await page.wait_for_function(
            "previous => document.body.dataset.ready && document.body.dataset.ready !== previous",
            arg=previous,
        )
        return True


class FixtureCompanyHTTP:
    def __init__(self, client, url):
        self.client, self.url = client, url

    async def fetch_jobs(self):
        response = await self.client.get(self.url)
        response.raise_for_status()
        return [
            RawJob(j["id"], j["title"], j["description"], "", j["url"])
            for j in response.json()["jobs"]
        ]

    async def health_check(self):
        return HealthResult(True, "fixture")


def fixture_registry(origin):
    return AdapterRegistry(
        (
            AdapterRegistration(
                "fixture-browser",
                SourceType.CUSTOM,
                "browser",
                lambda config, client, url: FixtureCompanyBrowser(
                    origin, mode=config.get("mode", "pages")
                ),
            ),
            AdapterRegistration(
                "fixture-http",
                SourceType.CUSTOM,
                "http",
                lambda config, client, url: FixtureCompanyHTTP(client, url),
            ),
        )
    )
