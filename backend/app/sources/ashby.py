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

HOST = "https://api.ashbyhq.com"
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
    return _EMPLOYMENT_TYPE_MAP.get(value.lower().replace(" ", "").replace("_", ""))


async def verify_public_host() -> None:
    """Fixed host only, HTTPS certificate verification, no environment proxies."""
    try:
        addresses = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo("api.ashbyhq.com", 443), timeout=5
        )
    except (OSError, TimeoutError) as exc:
        raise SourceError("Ashby DNS resolution failed") from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise SourceError("Ashby DNS resolved to a non-public address")


class AshbyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    job_board_name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class AshbyAdapter:
    """Only documented public GETs for Ashby public job boards."""

    def __init__(
        self,
        config: dict[str, Any],
        client: httpx.AsyncClient,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        try:
            self.config = AshbyConfig.model_validate(config)
        except ValidationError as exc:
            raise SourceError("Invalid Ashby job board configuration") from exc
        self.client = client
        self.sleep = sleep

    async def _payload(self) -> dict[str, Any]:
        await verify_public_host()
        url = f"{HOST}/posting-api/job-board/{self.config.job_board_name}"
        for attempt in range(3):
            try:
                async with self.client.stream(
                    "GET",
                    url,
                    timeout=httpx.Timeout(15, connect=5),
                    follow_redirects=False,
                ) as response:
                    transient = response.status_code == 429 or 500 <= response.status_code <= 599
                    if transient and attempt < 2:
                        delay = self._retry_delay(response.headers.get("retry-after"), attempt)
                    else:
                        if response.status_code != 200:
                            raise SourceError(f"Ashby HTTP status {response.status_code}")
                        chunks = bytearray()
                        async for chunk in response.aiter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > 20_000_000:
                                raise SourceError("Ashby response exceeds 20 MB")
                        try:
                            import json

                            payload = json.loads(chunks)
                        except (ValueError, UnicodeError) as exc:
                            raise SourceError("Ashby response is not valid JSON") from exc
                        if not isinstance(payload, dict):
                            raise SourceError("Ashby response must be a JSON object")
                        return payload
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == 2:
                    raise SourceError("Ashby connection/timeout failure") from exc
                delay = 0.5 * 2**attempt
            except httpx.HTTPError as exc:
                raise SourceError("Ashby HTTP transport failure") from exc
            logger.warning("Ashby transient retry", extra={"attempt": attempt + 1, "delay": delay})
            await self.sleep(delay)
        raise SourceError("Ashby retry budget exhausted")

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
                raise SourceError("Ashby Retry-After exceeds manual-run retry budget")
            if 0 <= delay <= 30:
                return delay
        return 0.5 * 2**attempt

    async def fetch_jobs(self) -> list[RawJob]:
        payload = await self._payload()
        jobs = payload.get("jobs")
        if not isinstance(jobs, list):
            raise SourceError("Ashby response missing jobs list")

        result = []
        identities = set()
        for job in jobs:
            if not isinstance(job, dict):
                raise SourceError("Ashby job record must be an object")

            # Check if role is unlisted
            if job.get("isListed") is False:
                continue

            job_id = job.get("id")
            if not isinstance(job_id, str) or not job_id.strip():
                raise SourceError("Ashby job has invalid or missing id")
            if job_id in identities:
                raise SourceError("Ashby board contains duplicate job ids")
            identities.add(job_id)

            title = job.get("title")
            if not isinstance(title, str) or not title.strip():
                raise SourceError("Ashby job is missing required title")

            description = job.get("descriptionHtml") or job.get("descriptionPlain") or ""
            if not isinstance(description, str):
                description = ""

            location = "Location not specified"
            loc = job.get("location")
            if isinstance(loc, str) and loc.strip():
                location = loc.strip()
            elif isinstance(job.get("secondaryLocations"), list) and job["secondaryLocations"]:
                first_sec = job["secondaryLocations"][0]
                if isinstance(first_sec, dict) and isinstance(first_sec.get("location"), str):
                    location = first_sec["location"].strip()
            elif job.get("isRemote") is True or str(job.get("workplaceType")).lower() == "remote":
                location = "Remote"

            url = job.get("jobUrl") or job.get("applyUrl")
            if not isinstance(url, str) or not url.strip():
                raise SourceError("Ashby job is missing jobUrl or applyUrl")

            posted_at = None
            pub = job.get("publishedAt") or job.get("publishedDate")
            if isinstance(pub, str) and pub.strip():
                try:
                    posted_at = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                except ValueError:
                    posted_at = None

            emp_type = job.get("employmentType")
            employment_type = (
                _normalize_employment_type(emp_type.strip())
                if isinstance(emp_type, str) and emp_type.strip()
                else None
            )

            result.append(
                RawJob(
                    external_id=job_id,
                    title=title,
                    description=description,
                    location=location,
                    url=url,
                    posted_at=posted_at,
                    employment_type=employment_type,
                    raw=job,
                )
            )
        return result

    async def health_check(self) -> HealthResult:
        try:
            await self.fetch_jobs()
        except SourceError as exc:
            return HealthResult(False, str(exc))
        return HealthResult(True, "public board readable")
