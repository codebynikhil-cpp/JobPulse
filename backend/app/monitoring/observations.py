from sqlalchemy import case, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.catalog import JobSource
from app.models.job import Job
from app.models.monitoring import JobMatch, JobMonitorState, ProfileCompany, SourceMonitorState
from app.models.profile import Profile
from app.monitoring.config import MonitoringConfig
from app.schemas.job import JobCreate


def record_observation(
    db: Session,
    source: JobSource,
    jobs: list[JobCreate],
    classifications: dict[str, str],
    config: MonitoringConfig,
    previous_failures: int,
) -> tuple[bool, int]:
    """Called inside ingestion's transaction after upserts; no fetching/normalization."""
    state = db.get(SourceMonitorState, source.id)
    if state is None:
        state = SourceMonitorState(source_id=source.id)
        db.add(state)
    baseline = state.last_clean_count
    if baseline is None:
        total = db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.source_id == source.id, Job.status == "open")
        )
        baseline = total - sum(v == "created" for v in classifications.values())
    anomaly = bool(
        baseline
        and (len(jobs) == 0 or (baseline - len(jobs)) / baseline > config.anomaly_drop_fraction)
    )
    db.execute(
        insert(JobMonitorState)
        .from_select(
            ["job_id", "missing_count", "pending"],
            select(Job.id, literal(0), literal(False)).where(Job.source_id == source.id),
        )
        .on_conflict_do_nothing()
    )
    seen = [j.external_job_id for j in jobs]
    seen_ids = select(Job.id).where(Job.source_id == source.id, Job.external_job_id.in_(seen))
    db.execute(
        update(JobMonitorState).where(JobMonitorState.job_id.in_(seen_ids)).values(missing_count=0)
    )
    changed = [identity for identity, kind in classifications.items() if kind != "unchanged"]
    db.execute(
        update(JobMonitorState)
        .where(
            JobMonitorState.job_id.in_(
                select(Job.id).where(Job.source_id == source.id, Job.external_job_id.in_(changed))
            )
        )
        .values(
            pending=True,
            event_kind=case(
                (
                    JobMonitorState.job_id.in_(
                        select(Job.id).where(
                            Job.source_id == source.id,
                            Job.external_job_id.in_(
                                [key for key, kind in classifications.items() if kind == "created"]
                            ),
                        )
                    ),
                    "new",
                ),
                else_="changed",
            ),
        )
    )
    # New subscriptions and edited/reactivated profiles need fresh evaluation even
    # when the provider returns identical job content. Only unchanged jobs enter
    # this path, preserving the new/changed ingestion event classification above.
    unchanged = [identity for identity, kind in classifications.items() if kind == "unchanged"]
    stale_jobs = (
        select(Job.id)
        .join(ProfileCompany, ProfileCompany.company_id == Job.company_id)
        .join(Profile, Profile.id == ProfileCompany.profile_id)
        .outerjoin(
            JobMatch,
            (JobMatch.job_id == Job.id) & (JobMatch.profile_id == Profile.id),
        )
        .where(
            Job.source_id == source.id,
            Job.status == "open",
            Job.external_job_id.in_(unchanged),
            Profile.active.is_(True),
            or_(JobMatch.profile_id.is_(None), JobMatch.updated_at < Profile.updated_at),
        )
    )
    db.execute(
        update(JobMonitorState)
        .where(JobMonitorState.job_id.in_(stale_jobs))
        .values(pending=True, event_kind="changed")
    )
    closed = 0
    if anomaly:
        source.consecutive_failures = previous_failures + 1
        source.health_status = "failing" if source.consecutive_failures >= 3 else "degraded"
        if source.consecutive_failures >= config.pause_after_failures:
            source.active = False
    else:
        state.last_clean_count = len(jobs)
        absent = select(Job.id).where(
            Job.source_id == source.id, Job.status == "open", Job.external_job_id.not_in(seen)
        )
        db.execute(
            update(JobMonitorState)
            .where(JobMonitorState.job_id.in_(absent))
            .values(missing_count=JobMonitorState.missing_count + 1)
        )
        ready = select(JobMonitorState.job_id).where(JobMonitorState.missing_count >= 2)
        result = db.execute(
            update(Job)
            .where(Job.source_id == source.id, Job.status == "open", Job.id.in_(ready))
            .values(status="closed", closed_at=source.last_checked_at)
        )
        closed = result.rowcount
    return anomaly, closed
