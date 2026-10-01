import asyncio
import ipaddress
from urllib.parse import urlsplit

from app.sources.base import SourceError


class BrowserURLPolicy:
    """Trusted adapter allowlist; never take a private-network exception from source config."""

    def __init__(self, allowed_hosts: frozenset[str]):
        self.allowed_hosts = allowed_hosts

    async def validate(self, url: str) -> None:
        try:
            value = urlsplit(url)
            port = value.port
        except ValueError:
            raise SourceError("Invalid browser URL") from None
        if value.scheme not in ("http", "https") or value.username or value.password:
            raise SourceError("Browser URL must be public HTTP(S) without credentials")
        if value.hostname not in self.allowed_hosts:
            raise SourceError("Browser destination is not allowlisted")
        try:
            records = await asyncio.wait_for(
                asyncio.get_running_loop().getaddrinfo(
                    value.hostname, port or (443 if value.scheme == "https" else 80)
                ),
                timeout=5,
            )
        except (OSError, TimeoutError) as exc:
            raise SourceError("Browser destination DNS failed") from exc
        if not records or any(not ipaddress.ip_address(r[4][0]).is_global for r in records):
            raise SourceError("Browser destination resolved to a non-public address")
