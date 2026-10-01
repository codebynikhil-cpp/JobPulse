from collections.abc import Callable
from dataclasses import dataclass

import httpx

from app.core.catalog import SourceType
from app.sources.base import JobSourceAdapter, SourceError
from app.sources.greenhouse import GreenhouseAdapter

# Compatibility inventory: platform classification alone is never a capability check.
AVAILABLE_ADAPTERS = frozenset({SourceType.GREENHOUSE})


@dataclass(frozen=True)
class AdapterRegistration:
    key: str
    source_type: SourceType
    acquisition_method: str
    build: Callable[[dict, httpx.AsyncClient, str | None], JobSourceAdapter]


class AdapterRegistry:
    def __init__(self, registrations: tuple[AdapterRegistration, ...]):
        self.registrations = registrations
        if len({r.key for r in registrations}) != len(registrations):
            raise ValueError("Duplicate adapter key")

    def resolve(
        self, source_type: SourceType, acquisition_method: str, adapter_key: str | None
    ) -> AdapterRegistration:
        key = adapter_key or source_type.value
        for registration in self.registrations:
            if (registration.key, registration.source_type, registration.acquisition_method) == (
                key,
                source_type,
                acquisition_method,
            ):
                return registration
        raise SourceError("No adapter implemented for this career source acquisition")

    def supports(
        self, source_type: SourceType, acquisition_method: str, adapter_key: str | None
    ) -> bool:
        try:
            self.resolve(source_type, acquisition_method, adapter_key)
        except SourceError:
            return False
        return True


DEFAULT_REGISTRY = AdapterRegistry(
    (
        AdapterRegistration(
            "greenhouse",
            SourceType.GREENHOUSE,
            "http",
            lambda config, client, career_url: GreenhouseAdapter(config, client),
        ),
    )
)


def build_adapter(
    source_type: SourceType,
    config: dict,
    client: httpx.AsyncClient,
    *,
    acquisition_method: str = "http",
    adapter_key: str | None = None,
    career_url: str | None = None,
    registry: AdapterRegistry | None = None,
) -> JobSourceAdapter:
    registration = (registry or DEFAULT_REGISTRY).resolve(
        source_type, acquisition_method, adapter_key
    )
    return registration.build(config, client, career_url)
