"""Optional LIVE Browserbase provider check. Not part of ordinary tests."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.browser.providers import BrowserbasePlaywrightProvider  # noqa: E402
from app.browser.security import BrowserURLPolicy  # noqa: E402
from app.core.config import settings  # noqa: E402


async def verify(url: str):
    policy = BrowserURLPolicy(frozenset({urlsplit(url).hostname}))
    await policy.validate(url)
    provider = BrowserbasePlaywrightProvider(
        settings.browserbase_api_key.get_secret_value(), settings.browserbase_project_id
    )
    async with provider.page(policy, timeout_ms=15000) as page:
        response = await page.goto(url, wait_until="domcontentloaded")
        if response is None or response.status >= 400:
            raise ValueError("Public provider probe page failed")


def main():
    parser = argparse.ArgumentParser(
        description="Explicit live Browserbase provider probe (uses a paid session)"
    )
    parser.add_argument("public_url")
    args = parser.parse_args()
    try:
        asyncio.run(verify(args.public_url))
    except Exception as exc:
        print(json.dumps({"verified": False, "error_type": type(exc).__name__}))
        return 1
    print(json.dumps({"verified": True, "provider": "browserbase"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
