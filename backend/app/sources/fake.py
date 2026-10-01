from copy import deepcopy

from app.sources.base import HealthResult, RawJob, SourceError


class FakeSource:
    """Deterministic in-memory adapter. Not a persisted source classification."""

    def __init__(self, batches: list[list[RawJob]], *, error: SourceError | None = None):
        self.batches = batches
        self.error = error

    async def fetch_jobs(self) -> list[RawJob]:
        if self.error:
            raise self.error
        return deepcopy([job for batch in self.batches for job in batch])

    async def health_check(self) -> HealthResult:
        return HealthResult(self.error is None, "fake source")
