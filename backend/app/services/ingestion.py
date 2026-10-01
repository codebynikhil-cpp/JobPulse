import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic

import httpx
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.models.catalog import JobSource
from app.models.job import Job
from app.schemas.job import JobCreate
from app.services.normalization import normalize_job
from app.sources.base import JobSourceAdapter, SourceError
from app.sources.registry import build_adapter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    fetched_count: int = 0
    normalized_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    failed_count: int = 0
    duration_seconds: float = 0


class IngestionError(SourceError):
    def __init__(self, message: str, result: IngestionResult):
        super().__init__(message)
        self.result = result


def upsert_job(db: Session, data: JobCreate) -> str:
    """Database identity resolves insert races; caller owns transaction/source lock."""
    values = data.model_dump()
    values["application_url"] = str(data.application_url)
    values["source_url"] = str(data.source_url) if data.source_url else None
    inserted = db.scalar(
        insert(Job)
        .values(**values)
        .on_conflict_do_nothing(constraint="uq_jobs_source_external_id")
        .returning(Job.id)
    )
    if inserted:
        return "created"
    job = db.scalar(
        select(Job)
        .where(Job.source_id == data.source_id, Job.external_job_id == data.external_job_id)
        .with_for_update()
    )
    if job is None:
        raise RuntimeError("Conflicting job disappeared during ingestion")
    if job.company_id != data.company_id:
        raise ValueError("Job company must match its source company")
    changed = job.content_hash != data.content_hash
    # Raw/provider metadata refreshes do not alone constitute material updates.
    for key, value in values.items():
        if key not in {
            "company_id",
            "source_id",
            "external_job_id",
            "first_seen_at",
            "last_seen_at",
        }:
            setattr(job, key, value)
    job.last_seen_at = max(job.last_seen_at, data.last_seen_at)
    db.flush()
    return "updated" if changed else "unchanged"


async def ingest_source(
    factory: sessionmaker[Session],
    source_id: uuid.UUID,
    *,
    adapter: JobSourceAdapter | None = None,
) -> IngestionResult:
    """One manual run; owns atomic job transaction and separate failure metadata."""
    started = monotonic()
    checked_at = datetime.now(UTC)
    fetched = normalized = 0
    with factory() as db:
        source = db.get(JobSource, source_id)
        if source is None:
            raise LookupError("Source not found")
        company_id, source_type, config = source.company_id, source.source_type, source.config
    try:
        if adapter is None:
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
                raw_jobs = await build_adapter(source_type, config, client).fetch_jobs()
        else:
            raw_jobs = await adapter.fetch_jobs()
        fetched = len(raw_jobs)
        jobs = []
        identities = set()
        for raw in raw_jobs:
            if raw.external_id in identities:
                raise SourceError("Duplicate external identity in source batch")
            identities.add(raw.external_id)
            jobs.append(
                normalize_job(raw, company_id=company_id, source_id=source_id, seen_at=checked_at)
            )
            normalized += 1
        counts = {"created": 0, "updated": 0, "unchanged": 0}
        with factory.begin() as db:
            source = db.scalar(select(JobSource).where(JobSource.id == source_id).with_for_update())
            if source is None:
                raise LookupError("Source removed during ingestion")
            if (
                source.company_id != company_id
                or source.source_type != source_type
                or source.config != config
            ):
                raise SourceError("Source configuration changed during ingestion; retry manually")
            # Serialize per-source runs; stale observations never overwrite newer ones.
            if source.last_checked_at and checked_at < source.last_checked_at:
                raise SourceError("Ingestion superseded by a newer completed run")
            for job in jobs:
                counts[upsert_job(db, job)] += 1
            source.last_checked_at = checked_at
            source.last_success_at = checked_at
            source.consecutive_failures = 0
            source.health_status = "healthy"
        result = IngestionResult(
            fetched,
            normalized,
            counts["created"],
            counts["updated"],
            counts["unchanged"],
            0,
            monotonic() - started,
        )
        logger.info(
            "Source ingestion succeeded",
            extra={"source_id": str(source_id), "result": result.__dict__},
        )
        return result
    except Exception as exc:
        # Rollback has completed before independent error bookkeeping. Never close jobs.
        with factory.begin() as db:
            source = db.scalar(select(JobSource).where(JobSource.id == source_id).with_for_update())
            if source and (source.last_checked_at is None or checked_at >= source.last_checked_at):
                source.last_checked_at = checked_at
                source.last_error_at = checked_at
                source.consecutive_failures += 1
                source.health_status = "degraded"
        result = IngestionResult(
            fetched_count=fetched,
            normalized_count=normalized,
            failed_count=max(1, fetched),
            duration_seconds=monotonic() - started,
        )
        # Do not log provider content, credentials, or SQL parameter values.
        logger.error(
            "Source ingestion failed",
            extra={"source_id": str(source_id), "error_type": type(exc).__name__},
        )
        message = str(exc) if isinstance(exc, SourceError) else "Source ingestion failed"
        if isinstance(exc, ValidationError):
            message = "Source record failed canonical validation"
        raise IngestionError(message, result) from exc
