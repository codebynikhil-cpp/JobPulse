import asyncio
import ipaddress
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.sources.base import HealthResult, RawJob, SourceError

HOST = "https://boards-api.greenhouse.io"
logger = logging.getLogger(__name__)


async def verify_public_host() -> None:
    """Fixed host only, HTTPS certificate verification, no environment proxies."""
    try:
        addresses = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo("boards-api.greenhouse.io", 443), timeout=5
        )
    except (OSError, TimeoutError) as exc:
        raise SourceError("Greenhouse DNS resolution failed") from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise SourceError("Greenhouse DNS resolved to a non-public address")


class GreenhouseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    board_token: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class GreenhouseAdapter:
    """Only documented public GETs; tokens cannot change host/path structure."""

    def __init__(
        self,
        config: dict[str, Any],
        client: httpx.AsyncClient,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        try:
            self.config = GreenhouseConfig.model_validate(config)
        except ValidationError as exc:
            raise SourceError("Invalid Greenhouse board configuration") from exc
        self.client = client
        self.sleep = sleep

    async def _payload(self) -> dict[str, Any]:
        await verify_public_host()
        url = f"{HOST}/v1/boards/{self.config.board_token}/jobs"
        for attempt in range(3):
            try:
                async with self.client.stream(
                    "GET",
                    url,
                    params={"content": "true"},
                    timeout=httpx.Timeout(15, connect=5),
                    follow_redirects=False,
                ) as response:
                    transient = response.status_code == 429 or 500 <= response.status_code <= 599
                    if transient and attempt < 2:
                        delay = self._retry_delay(response.headers.get("retry-after"), attempt)
                    else:
                        if response.status_code != 200:
                            raise SourceError(f"Greenhouse HTTP status {response.status_code}")
                        chunks = bytearray()
                        async for chunk in response.aiter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > 20_000_000:
                                raise SourceError("Greenhouse response exceeds 20 MB")
                        try:
                            import json

                            payload = json.loads(chunks)
                        except (ValueError, UnicodeError) as exc:
                            raise SourceError("Greenhouse response is not valid JSON") from exc
                        if not isinstance(payload, dict):
                            raise SourceError("Greenhouse response must be an object")
                        return payload
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == 2:
                    raise SourceError("Greenhouse connection/timeout failure") from exc
                delay = 0.5 * 2**attempt
            except httpx.HTTPError as exc:
                raise SourceError("Greenhouse HTTP transport failure") from exc
            logger.warning(
                "Greenhouse transient retry", extra={"attempt": attempt + 1, "delay": delay}
            )
            await self.sleep(delay)
        raise SourceError("Greenhouse retry budget exhausted")

    @staticmethod
    def _retry_delay(value: str | None, attempt: int) -> float:
        if value:
            try:
                delay = float(value)
            except ValueError:
                try:
                    delay = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
                except (ValueError, TypeError, OverflowError):
                    delay = 0.5 * 2**attempt
            # Avoid blocking manual runs for an unbounded server directive.
            if delay > 30:
                raise SourceError("Greenhouse Retry-After exceeds manual-run retry budget")
            if 0 <= delay <= 30:
                return delay
        return 0.5 * 2**attempt

    async def fetch_jobs(self) -> list[RawJob]:
        payload = await self._payload()
        jobs = payload.get("jobs")
        total = (
            payload.get("meta", {}).get("total") if isinstance(payload.get("meta"), dict) else None
        )
        if not isinstance(jobs, list) or type(total) is not int or total != len(jobs):
            raise SourceError("Greenhouse incomplete or malformed board response")
        result = []
        identities = set()
        for job in jobs:
            if not isinstance(job, dict) or type(job.get("id")) is not int or job["id"] <= 0:
                raise SourceError("Greenhouse job has invalid post id")
            if job["id"] in identities:
                raise SourceError("Greenhouse board contains duplicate post ids")
            identities.add(job["id"])
            if not all(
                isinstance(job.get(key), str) for key in ("title", "absolute_url", "content")
            ):
                raise SourceError("Greenhouse job is missing required content fields")
            location = job.get("location")
            if not isinstance(location, dict) or not isinstance(location.get("name"), str):
                raise SourceError("Greenhouse job has invalid location")
            result.append(
                RawJob(
                    external_id=str(job["id"]),
                    title=job["title"],
                    description=job["content"],
                    location=location["name"],
                    url=job["absolute_url"],
                    raw=job,
                    # List response updated_at is NOT a publication timestamp.
                )
            )
        return result

    async def health_check(self) -> HealthResult:
        try:
            await self.fetch_jobs()
        except SourceError as exc:
            return HealthResult(False, str(exc))
        return HealthResult(True, "public board readable")
