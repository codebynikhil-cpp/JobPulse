from abc import ABC, abstractmethod
from dataclasses import dataclass

from playwright.async_api import Page

from app.browser.providers import BrowserProvider
from app.browser.security import BrowserURLPolicy
from app.sources.base import HealthResult, RawJob, SourceError


@dataclass(frozen=True)
class BrowserSourceConfig:
    career_url: str
    ready_selector: str
    timeout_ms: int = 15000
    max_pages: int = 20
    max_jobs: int = 10000

    def __post_init__(self):
        if not self.career_url or not self.ready_selector:
            raise ValueError("Career URL and explicit readiness selector are required")
        if (
            not 1 <= self.max_pages <= 100
            or not 1 <= self.max_jobs <= 10000
            or not 1 <= self.timeout_ms <= 90000
        ):
            raise ValueError("Browser extraction bounds are invalid")


class BrowserSourceAdapter(ABC):
    """Company-specific subclasses implement extraction/interaction, never persistence."""

    def __init__(
        self, config: BrowserSourceConfig, provider: BrowserProvider, policy: BrowserURLPolicy
    ):
        self.config, self.provider, self.policy = config, provider, policy

    @abstractmethod
    async def extract_jobs(self, page: Page) -> list[RawJob]: ...

    @abstractmethod
    async def advance(self, page: Page) -> bool:
        """Navigate/click and await stable readiness; false means complete."""
        ...

    async def prepare_page(self, page: Page) -> None:
        """Optional company-specific request/response observation before navigation."""
        return None

    async def fetch_jobs(self) -> list[RawJob]:
        try:
            await self.policy.validate(self.config.career_url)
            records: dict[str, RawJob] = {}
            async with self.provider.page(self.policy, timeout_ms=self.config.timeout_ms) as page:
                await self.prepare_page(page)
                response = await page.goto(self.config.career_url, wait_until="domcontentloaded")
                if response is None or response.status >= 400:
                    raise SourceError("Company career page failed")
                await page.wait_for_selector(self.config.ready_selector)
                for _ in range(self.config.max_pages):
                    batch = await self.extract_jobs(page)
                    for job in batch:
                        if not job.external_id or not job.title.strip() or not job.url:
                            raise SourceError("Malformed browser job record")
                        await self.policy.validate(job.url)
                        previous = records.get(job.external_id)
                        if previous is not None and previous != job:
                            raise SourceError("Conflicting repeated browser job identity")
                        records[job.external_id] = job
                    if len(records) > self.config.max_jobs:
                        raise SourceError("Browser job bound exceeded")
                    if not await self.advance(page):
                        return list(records.values())
                raise SourceError("Browser pagination bound exceeded; incomplete batch")
        except Exception as exc:
            if isinstance(exc, SourceError):
                raise
            raise SourceError("Browser extraction failed") from exc

    async def health_check(self) -> HealthResult:
        try:
            await self.fetch_jobs()
        except SourceError:
            return HealthResult(False, "Company browser source failed")
        return HealthResult(True, "Company browser source usable")
