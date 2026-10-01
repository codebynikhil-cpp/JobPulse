import httpx

from app.core.catalog import SourceType
from app.sources.base import JobSourceAdapter, SourceError
from app.sources.greenhouse import GreenhouseAdapter

AVAILABLE_ADAPTERS = frozenset({SourceType.GREENHOUSE})


def build_adapter(
    source_type: SourceType, config: dict, client: httpx.AsyncClient
) -> JobSourceAdapter:
    if source_type == SourceType.GREENHOUSE:
        return GreenhouseAdapter(config, client)
    raise SourceError(f"No adapter implemented for source type {source_type}")
