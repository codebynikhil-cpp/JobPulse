import asyncio
import logging
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from time import monotonic

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.matching.config import ScoringConfig
from app.matching.matcher import DeterministicMatcher, Matcher
from app.models.catalog import Company, JobSource
from app.models.monitoring import MonitorRun, ProfileCompany
from app.models.profile import Profile
from app.monitoring.config import MonitoringConfig
from app.monitoring.evaluation import evaluate_pending, json_value, matcher_identity
from app.monitoring.observations import record_observation
from app.services.ingestion import IngestionError, IngestionResult, ingest_source
from app.services.source_lock import source_lock
from app.sources.base import JobSourceAdapter
from app.sources.registry import DEFAULT_REGISTRY, AdapterRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MonitoringResult:
    source_id: uuid.UUID
    started_at: datetime
    completed_at: datetime
    status: str
    duration_seconds: float = 0
    ingestion: IngestionResult = field(default_factory=IngestionResult)
    evaluated_count: int = 0
    matched_count: int = 0
    evaluation_failed_count: int = 0
    closed_count: int = 0
    error: dict | None = None
    run_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    acquisition_method: str | None = None
    adapter_key: str | None = None

    @property
    def fetched_count(self) -> int:
        return self.ingestion.fetched_count

    @property
    def normalized_count(self) -> int:
        return self.ingestion.normalized_count

    @property
    def created_count(self) -> int:
        return self.ingestion.created_count

    @property
    def updated_count(self) -> int:
        return self.ingestion.updated_count

    @property
    def unchanged_count(self) -> int:
        return self.ingestion.unchanged_count

    @property
    def failed_count(self) -> int:
        return self.ingestion.failed_count + self.evaluation_failed_count

    def to_dict(self) -> dict:
        return json_value(asdict(self)) | {
            name: getattr(self, name)
            for name in (
                "fetched_count",
                "normalized_count",
                "created_count",
                "updated_count",
                "unchanged_count",
                "failed_count",
            )
        }


async def run_source(
    factory: sessionmaker[Session],
    source_id: uuid.UUID,
    *,
    adapter: JobSourceAdapter | None = None,
    matcher: Matcher | None = None,
    scoring: ScoringConfig | None = None,
    config: MonitoringConfig | None = None,
    due_only: bool = False,
    registry: AdapterRegistry | None = None,
) -> MonitoringResult:
    config = config or MonitoringConfig()
    registry = registry or DEFAULT_REGISTRY
    scoring = scoring or ScoringConfig()
    matcher = matcher or DeterministicMatcher(scoring)
    started_at, started = datetime.now(UTC), monotonic()
    result = MonitoringResult(source_id, started_at, started_at, "running")
    with source_lock(factory, source_id) as acquired:
        if not acquired:
            return replace(
                result,
                status="busy",
                completed_at=datetime.now(UTC),
                duration_seconds=monotonic() - started,
            )
        with factory.begin() as db:
            source = db.get(JobSource, source_id)
            if source is None:
                raise LookupError("Source not found")
            # An acquired lock means any prior running record was interrupted.
            db.execute(
                update(MonitorRun)
                .where(MonitorRun.source_id == source_id, MonitorRun.status == "running")
                .values(
                    status="abandoned",
                    completed_at=started_at,
                    result={"error": {"stage": "worker", "error_type": "InterruptedRun"}},
                )
            )
            company = db.get(Company, source.company_id)
            status = None
            if not registry.supports(
                source.source_type, source.acquisition_method, source.adapter_key
            ):
                status = "unsupported"
                source.health_status = "unsupported"
            elif not source.active or not company.enabled:
                status = "disabled"
            elif due_only and not db.scalar(
                select(ProfileCompany.profile_id)
                .join(Profile)
                .where(ProfileCompany.company_id == company.id, Profile.active.is_(True))
                .limit(1)
            ):
                status = "disabled"
            elif (
                due_only
                and source.last_checked_at
                and source.last_checked_at + timedelta(seconds=source.poll_interval_sec)
                > started_at
            ):
                status = "not_due"
            previous_failures = source.consecutive_failures
            run = MonitorRun(
                source_id=source_id, started_at=started_at, status="running", result={}
            )
            db.add(run)
            db.flush()
            result = replace(
                result,
                run_id=run.id,
                company_id=company.id,
                acquisition_method=source.acquisition_method,
                adapter_key=source.adapter_key or source.source_type.value,
            )
        if status is not None:
            result = replace(result, status=status)
        else:
            observations = {"anomaly": False, "closed": 0}

            def hook(db, source, jobs, classifications):
                observations["anomaly"], observations["closed"] = record_observation(
                    db, source, jobs, classifications, config, previous_failures
                )

            try:
                async with asyncio.timeout(config.source_timeout_seconds):
                    ingestion = await ingest_source(
                        factory,
                        source_id,
                        adapter=adapter,
                        on_persist=hook,
                        lock_held=True,
                        registry=registry,
                    )
                result = replace(
                    result,
                    ingestion=ingestion,
                    status="anomaly" if observations["anomaly"] else "success",
                    closed_count=observations["closed"],
                )
                if observations["anomaly"]:
                    result = replace(
                        result, error={"stage": "observation", "error_type": "BoardCountAnomaly"}
                    )
                evaluated, matched, failed = evaluate_pending(
                    factory, source_id, matcher, matcher_identity(scoring), config
                )
                result = replace(
                    result,
                    evaluated_count=evaluated,
                    matched_count=matched,
                    evaluation_failed_count=failed,
                    status="partial" if failed and result.status == "success" else result.status,
                )
                if failed:
                    result = replace(
                        result,
                        error={
                            "stage": "matching",
                            "error_type": "ProfileEvaluationFailure",
                            "count": failed,
                        },
                    )
            except Exception as exc:
                ingestion = exc.result if isinstance(exc, IngestionError) else result.ingestion
                ingestion_failed = result.status == "running"
                if ingestion_failed and not isinstance(exc, IngestionError):
                    ingestion = replace(ingestion, failed_count=1)
                # IngestionError already records failure; timeout/cancellation of fetch does not.
                with factory.begin() as db:
                    source = db.scalar(
                        select(JobSource).where(JobSource.id == source_id).with_for_update()
                    )
                    if source and ingestion_failed:
                        if not isinstance(exc, IngestionError):
                            source.last_checked_at = started_at
                            source.last_error_at = started_at
                            source.consecutive_failures += 1
                        source.health_status = (
                            "failing" if source.consecutive_failures >= 3 else "degraded"
                        )
                        if source.consecutive_failures >= config.pause_after_failures:
                            source.active = False
                result = replace(
                    result,
                    status="failed",
                    ingestion=ingestion,
                    error={
                        "stage": "ingestion" if result.status == "running" else "matching",
                        "error_type": type(exc).__name__,
                    },
                )
                logger.error(
                    "Monitoring source failed",
                    extra={
                        "source_id": str(source_id),
                        "company_id": str(result.company_id),
                        "error_type": type(exc).__name__,
                        "error_detail": str(exc)[:500],
                    },
                    exc_info=True,
                )
        result = replace(
            result, completed_at=datetime.now(UTC), duration_seconds=monotonic() - started
        )
        with factory.begin() as db:
            run = db.get(MonitorRun, result.run_id)
            run.completed_at, run.status, run.result = (
                result.completed_at,
                result.status,
                result.to_dict(),
            )
        logger.info(
            "Monitoring source completed",
            extra={
                "source_id": str(source_id),
                "company_id": str(result.company_id),
                "adapter_key": result.adapter_key,
                "acquisition_method": result.acquisition_method,
                "run_id": str(result.run_id),
                "status": result.status,
                "matched_count": result.matched_count,
                "created_count": result.created_count,
                "updated_count": result.updated_count,
                "unchanged_count": result.unchanged_count,
                "failed_count": result.failed_count,
                "duration_seconds": round(result.duration_seconds, 3),
            },
        )
        return result
