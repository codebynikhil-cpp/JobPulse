from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class RawJob:
    external_id: str
    title: str
    description: str
    location: str
    url: str
    posted_at: datetime | None = None
    employment_type: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HealthResult:
    healthy: bool
    detail: str


class SourceError(Exception):
    """A failed fetch is never represented as an empty successful fetch."""


class JobSourceAdapter(Protocol):
    async def fetch_jobs(self) -> list[RawJob]: ...

    async def health_check(self) -> HealthResult: ...
