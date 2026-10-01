import json
import logging
import uuid
from dataclasses import asdict
from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.matching.config import ScoringConfig
from app.matching.matcher import Matcher, MatchingProfile
from app.models.job import Job
from app.models.monitoring import JobMatch, JobMonitorState, ProfileCompany
from app.models.profile import Profile
from app.monitoring.config import MonitoringConfig
from app.notifications.config import NotificationConfig
from app.notifications.outbox import enqueue_matches, previous_relevant_users

logger = logging.getLogger(__name__)
MATCHER_VERSION = "phase5-exact-v1"


def json_value(value):
    return json.loads(json.dumps(value, default=str, sort_keys=True))


def digest(value) -> str:
    return sha256(
        json.dumps(json_value(value), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def matcher_identity(config: ScoringConfig) -> str:
    return MATCHER_VERSION + ":" + digest(asdict(config))


def materialize_profile(profile: Profile) -> MatchingProfile:
    return MatchingProfile(
        roles=tuple(r.name for r in profile.roles),
        required_skills=tuple(s.name for s in profile.skills if s.kind == "required"),
        preferred_skills=tuple(s.name for s in profile.skills if s.kind == "preferred"),
        preferred_locations=tuple(
            location.name for location in profile.locations if not location.excluded
        ),
        excluded_locations=tuple(
            location.name for location in profile.locations if location.excluded
        ),
        excluded_terms=tuple(e.term for e in profile.exclusions),
        employment_types=tuple(profile.employment_types),
        work_modes=tuple(profile.work_modes),
        exp_min=profile.exp_min,
        exp_max=profile.exp_max,
    )


def evaluate_pending(
    factory: sessionmaker[Session],
    source_id: uuid.UUID,
    matcher: Matcher,
    identity: str,
    config: MonitoringConfig,
    notification_config: NotificationConfig | None = None,
) -> tuple[int, int, int]:
    notification_config = notification_config or NotificationConfig.from_settings()
    evaluated = matched = failed = 0
    after_job = None
    while True:
        with factory() as db:
            query = (
                select(JobMonitorState.job_id)
                .join(Job, Job.id == JobMonitorState.job_id)
                .where(Job.source_id == source_id, JobMonitorState.pending.is_(True))
            )
            if after_job is not None:
                query = query.where(JobMonitorState.job_id > after_job)
            ids = list(
                db.scalars(query.order_by(JobMonitorState.job_id).limit(config.job_batch_size))
            )
        if not ids:
            break
        for job_id in ids:
            with factory.begin() as db:
                job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
                work = db.get(JobMonitorState, job_id)
                if job is None or work is None:
                    continue
                if job.status != "open":
                    work.pending = False
                    continue
                after_profile = None
                job_failed = False
                previous_users = previous_relevant_users(db, job.id)
                while True:
                    query = (
                        select(Profile)
                        .join(ProfileCompany)
                        .where(
                            ProfileCompany.company_id == job.company_id, Profile.active.is_(True)
                        )
                    )
                    if after_profile is not None:
                        query = query.where(Profile.id > after_profile)
                    profiles = list(
                        db.scalars(
                            query.options(
                                *(
                                    selectinload(getattr(Profile, name))
                                    for name in ("roles", "skills", "locations", "exclusions")
                                )
                            )
                            .order_by(Profile.id)
                            .limit(config.profile_batch_size)
                            .with_for_update(of=Profile)
                        )
                    )
                    if not profiles:
                        break
                    for profile in profiles:
                        p_hash = ""
                        try:
                            with db.begin_nested():
                                inputs = materialize_profile(profile)
                                p_hash = digest(asdict(inputs))
                                existing = db.get(JobMatch, (profile.id, job.id))
                                if (
                                    existing
                                    and existing.status == "evaluated"
                                    and (
                                        existing.content_hash,
                                        existing.profile_hash,
                                        existing.matcher_identity,
                                    )
                                    == (job.content_hash, p_hash, identity)
                                ):
                                    continue
                                result = matcher.match(job, inputs)
                                values = dict(
                                    profile_id=profile.id,
                                    job_id=job.id,
                                    matched=result.matched,
                                    score=result.score,
                                    status="evaluated",
                                    content_hash=job.content_hash,
                                    profile_hash=p_hash,
                                    matcher_identity=identity,
                                    evidence=json_value(asdict(result)),
                                    updated_at=func.clock_timestamp(),
                                )
                                statement = insert(JobMatch).values(**values)
                                db.execute(
                                    statement.on_conflict_do_update(
                                        index_elements=[JobMatch.profile_id, JobMatch.job_id],
                                        set_={
                                            k: v
                                            for k, v in values.items()
                                            if k not in ("profile_id", "job_id")
                                        }
                                        | {"updated_at": statement.excluded.updated_at},
                                    )
                                )
                            evaluated += 1
                            matched += int(result.matched)
                        except Exception as exc:
                            job_failed = True
                            failed += 1
                            logger.error(
                                "Profile evaluation failed",
                                extra={
                                    "source_id": str(source_id),
                                    "job_id": str(job.id),
                                    "profile_id": str(profile.id),
                                    "error_type": type(exc).__name__,
                                },
                            )
                            values = dict(
                                profile_id=profile.id,
                                job_id=job.id,
                                matched=None,
                                score=None,
                                status="error",
                                content_hash=job.content_hash,
                                profile_hash=p_hash,
                                matcher_identity=identity,
                                evidence={"error_type": type(exc).__name__, "stage": "matching"},
                                updated_at=func.clock_timestamp(),
                            )
                            statement = insert(JobMatch).values(**values)
                            db.execute(
                                statement.on_conflict_do_update(
                                    index_elements=[JobMatch.profile_id, JobMatch.job_id],
                                    set_={
                                        k: v
                                        for k, v in values.items()
                                        if k not in ("profile_id", "job_id")
                                    }
                                    | {"updated_at": statement.excluded.updated_at},
                                )
                            )
                    after_profile = profiles[-1].id
                work.pending = job_failed
                # Outside profile savepoints: failure rolls back this job's match
                # writes and all corresponding notification intent together.
                enqueue_matches(db, job, work, previous_users, notification_config)
        after_job = ids[-1]
    return evaluated, matched, failed


def list_current_matches(db: Session, user_id: uuid.UUID, *, limit: int = 100) -> list[JobMatch]:
    """Owner-scoped current state for future consumers; not a notification outbox."""
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100")
    return list(
        db.scalars(
            select(JobMatch)
            .join(Profile)
            .join(Job, Job.id == JobMatch.job_id)
            .join(
                ProfileCompany,
                (ProfileCompany.profile_id == Profile.id)
                & (ProfileCompany.company_id == Job.company_id),
            )
            .where(
                Profile.user_id == user_id,
                Profile.active.is_(True),
                Job.status == "open",
                JobMatch.matched.is_(True),
                JobMatch.status == "evaluated",
                JobMatch.content_hash == Job.content_hash,
                JobMatch.updated_at >= Profile.updated_at,
            )
            .order_by(JobMatch.updated_at.desc(), JobMatch.profile_id, JobMatch.job_id)
            .limit(limit)
        )
    )
