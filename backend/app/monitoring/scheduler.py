import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.catalog import Company, JobSource
from app.models.monitoring import ProfileCompany
from app.models.profile import Profile
from app.monitoring.config import MonitoringConfig
from app.monitoring.runner import MonitoringResult, run_source
from app.sources.registry import DEFAULT_REGISTRY, AdapterRegistry

logger = logging.getLogger(__name__)


def due_sources(
    factory: sessionmaker[Session],
    config: MonitoringConfig,
    *,
    now: datetime | None = None,
    registry: AdapterRegistry | None = None,
):
    now = now or datetime.now(UTC)
    registry = registry or DEFAULT_REGISTRY
    capabilities = [
        and_(
            JobSource.source_type == r.source_type,
            JobSource.acquisition_method == r.acquisition_method,
            or_(
                JobSource.adapter_key == r.key,
                JobSource.adapter_key.is_(None) if r.key == r.source_type.value else False,
            ),
        )
        for r in registry.registrations
    ]
    if not capabilities:
        return []
    with factory() as db:
        # make_interval's seconds argument keeps the polling interval in SQL.
        interval = func.make_interval(0, 0, 0, 0, 0, 0, JobSource.poll_interval_sec)
        return list(
            db.scalars(
                select(JobSource.id)
                .join(Company)
                .where(
                    JobSource.active.is_(True),
                    Company.enabled.is_(True),
                    exists(
                        select(ProfileCompany.profile_id)
                        .join(Profile)
                        .where(
                            ProfileCompany.company_id == JobSource.company_id,
                            Profile.active.is_(True),
                        )
                    ),
                    or_(*capabilities),
                    or_(
                        JobSource.last_checked_at.is_(None),
                        JobSource.last_checked_at + interval <= now,
                    ),
                )
                .order_by(JobSource.last_checked_at.asc().nullsfirst(), JobSource.id)
                .limit(config.source_batch_size)
            )
        )


async def run_due(
    factory: sessionmaker[Session],
    *,
    config: MonitoringConfig | None = None,
    adapter_factory=None,
    matcher=None,
    registry: AdapterRegistry | None = None,
) -> list[MonitoringResult]:
    config = config or MonitoringConfig()
    results = []
    for source_id in due_sources(factory, config, registry=registry):
        try:
            result = await run_source(
                factory,
                source_id,
                config=config,
                due_only=True,
                adapter=adapter_factory(source_id) if adapter_factory else None,
                matcher=matcher,
                registry=registry,
            )
            results.append(result)
        except Exception as exc:
            # Database/control-plane failures still must be visible to supervision.
            logger.error(
                "Monitoring control-plane failure",
                extra={"source_id": str(source_id), "error_type": type(exc).__name__},
            )
            now = datetime.now(UTC)
            results.append(
                MonitoringResult(
                    source_id,
                    now,
                    now,
                    "failed",
                    error={"stage": "control", "error_type": type(exc).__name__},
                )
            )
    return results


async def worker(
    factory: sessionmaker[Session], config: MonitoringConfig, *, stop: asyncio.Event | None = None
):
    stop = stop if stop is not None else asyncio.Event()
    while not stop.is_set():
        try:
            await run_due(factory, config=config)
        except Exception as exc:
            logger.error(
                "Unexpected monitoring cycle failure: %s",
                exc,
                extra={"error_type": type(exc).__name__},
                exc_info=True,
            )
        try:
            await asyncio.wait_for(stop.wait(), timeout=config.tick_seconds)
        except TimeoutError:
            pass
