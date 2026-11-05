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

HOST = "https://api.lever.co"
logger = logging.getLogger(__name__)

# Canonical employment type values accepted by JobCreate
_EMPLOYMENT_TYPE_MAP: dict[str, str] = {
    "full-time": "full_time",
    "fulltime": "full_time",
    "full_time": "full_time",
    "part-time": "part_time",
    "parttime": "part_time",
    "part_time": "part_time",
    "contract": "contract",
    "contractor": "contract",
    "internship": "internship",
    "intern": "internship",
    "temporary": "temporary",
    "temp": "temporary",
}


def _normalize_employment_type(value: str) -> str | None:
    """Map raw employment type strings to canonical values; return None if unrecognized."""
    return _EMPLOYMENT_TYPE_MAP.get(value.lower().replace(" ", ""))


async def verify_public_host() -> None:
    """Fixed host only, HTTPS certificate verification, no environment proxies."""
    try:
        addresses = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo("api.lever.co", 443), timeout=5
        )
    except (OSError, TimeoutError) as exc:
        raise SourceError("Lever DNS resolution failed") from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise SourceError("Lever DNS resolved to a non-public address")


class LeverConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    site: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class LeverAdapter:
    """Only documented public GETs for Lever public postings."""

    def __init__(
        self,
        config: dict[str, Any],
        client: httpx.AsyncClient,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        try:
            self.config = LeverConfig.model_validate(config)
        except ValidationError as exc:
            raise SourceError("Invalid Lever site configuration") from exc
        self.client = client
        self.sleep = sleep

    async def _payload(self) -> list[dict[str, Any]]:
        await verify_public_host()
        url = f"{HOST}/v0/postings/{self.config.site}"
        for attempt in range(3):
            try:
                async with self.client.stream(
                    "GET",
                    url,
                    params={"mode": "json"},
                    timeout=httpx.Timeout(15, connect=5),
                    follow_redirects=False,
                ) as response:
                    transient = response.status_code == 429 or 500 <= response.status_code <= 599
                    if transient and attempt < 2:
                        delay = self._retry_delay(response.headers.get("retry-after"), attempt)
                    else:
                        if response.status_code != 200:
                            raise SourceError(f"Lever HTTP status {response.status_code}")
                        chunks = bytearray()
                        async for chunk in response.aiter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > 20_000_000:
                                raise SourceError("Lever response exceeds 20 MB")
                        try:
                            import json

                            payload = json.loads(chunks)
                        except (ValueError, UnicodeError) as exc:
                            raise SourceError("Lever response is not valid JSON") from exc
                        if not isinstance(payload, list):
                            raise SourceError("Lever response must be an array of postings")
                        return payload
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == 2:
                    raise SourceError("Lever connection/timeout failure") from exc
                delay = 0.5 * 2**attempt
            except httpx.HTTPError as exc:
                raise SourceError("Lever HTTP transport failure") from exc
            logger.warning("Lever transient retry", extra={"attempt": attempt + 1, "delay": delay})
            await self.sleep(delay)
        raise SourceError("Lever retry budget exhausted")

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
            if delay > 30:
                raise SourceError("Lever Retry-After exceeds manual-run retry budget")
            if 0 <= delay <= 30:
                return delay
        return 0.5 * 2**attempt

    async def fetch_jobs(self) -> list[RawJob]:
        payload = await self._payload()
        result = []
        identities = set()
        for post in payload:
            if not isinstance(post, dict):
                raise SourceError("Lever posting must be an object")
            post_id = post.get("id")
            if not isinstance(post_id, str) or not post_id.strip():
                raise SourceError("Lever posting has invalid or missing id")
            if post_id in identities:
                raise SourceError("Lever board contains duplicate post ids")
            identities.add(post_id)

            title = post.get("text")
            if not isinstance(title, str) or not title.strip():
                raise SourceError("Lever posting is missing required title")

            # Build full description from main description, lists, and additional text
            desc_parts = []
            desc = post.get("description")
            if isinstance(desc, str) and desc.strip():
                desc_parts.append(desc)

            lists = post.get("lists")
            if isinstance(lists, list):
                for item in lists:
                    if isinstance(item, dict):
                        list_title = item.get("text")
                        list_content = item.get("content")
                        if list_title and isinstance(list_title, str):
                            desc_parts.append(f"<h3>{list_title}</h3>")
                        if list_content and isinstance(list_content, str):
                            desc_parts.append(list_content)

            additional = post.get("additional")
            if isinstance(additional, str) and additional.strip():
                desc_parts.append(additional)

            full_description = "".join(desc_parts) or post.get("descriptionPlain") or ""

            # Extract location from categories
            categories = post.get("categories")
            location = "Location not specified"
            employment_type = None
            if isinstance(categories, dict):
                loc = categories.get("location")
                if isinstance(loc, str) and loc.strip():
                    location = loc.strip()
                elif (
                    isinstance(categories.get("allLocations"), list) and categories["allLocations"]
                ):
                    first_loc = categories["allLocations"][0]
                    if isinstance(first_loc, str) and first_loc.strip():
                        location = first_loc.strip()

                commitment = categories.get("commitment")
                if isinstance(commitment, str) and commitment.strip():
                    employment_type = _normalize_employment_type(commitment.strip())

            url = post.get("hostedUrl") or post.get("applyUrl")
            if not isinstance(url, str) or not url.strip():
                raise SourceError("Lever posting is missing URL")

            posted_at = None
            created_at = post.get("createdAt")
            if isinstance(created_at, (int, float)) and created_at > 0:
                try:
                    posted_at = datetime.fromtimestamp(created_at / 1000.0, tz=UTC)
                except (ValueError, OverflowError, OSError):
                    posted_at = None

            result.append(
                RawJob(
                    external_id=post_id,
                    title=title,
                    description=full_description,
                    location=location,
                    url=url,
                    posted_at=posted_at,
                    employment_type=employment_type,
                    raw=post,
                )
            )
        return result

    async def health_check(self) -> HealthResult:
        try:
            await self.fetch_jobs()
        except SourceError as exc:
            return HealthResult(False, str(exc))
        return HealthResult(True, "public board readable")
