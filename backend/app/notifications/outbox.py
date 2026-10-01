from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.catalog import Company, JobSource
from app.models.job import Job
from app.models.monitoring import JobMatch, JobMonitorState, ProfileCompany
from app.models.notification import Notification
from app.models.profile import Profile
from app.notifications.config import NotificationConfig


def material_fields(job: Job) -> dict:
    return {
        name: getattr(job, name)
        for name in (
            "title",
            "description",
            "location",
            "employment_type",
            "experience_text",
            "min_exp_years",
            "max_exp_years",
            "application_url",
        )
    }


def material_hash(job: Job) -> str:
    serialized = json.dumps(
        material_fields(job),
        default=str,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def matching_rows(db: Session, job: Job):
    return db.execute(
        select(Profile, JobMatch)
        .join(JobMatch, JobMatch.profile_id == Profile.id)
        .join(ProfileCompany, ProfileCompany.profile_id == Profile.id)
        .where(
            JobMatch.job_id == job.id,
            Profile.active.is_(True),
            ProfileCompany.company_id == job.company_id,
            JobMatch.matched.is_(True),
            JobMatch.status == "evaluated",
            JobMatch.content_hash == job.content_hash,
        )
        .order_by(Profile.user_id, Profile.id)
    ).all()


def previous_relevant_users(db: Session, job_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(Profile.user_id)
            .join(JobMatch, JobMatch.profile_id == Profile.id)
            .where(
                JobMatch.job_id == job_id,
                JobMatch.matched.is_(True),
                Profile.active.is_(True),
            )
        )
    )


def enqueue_matches(
    db: Session,
    job: Job,
    work: JobMonitorState,
    previous_users: set[uuid.UUID],
    config: NotificationConfig,
) -> int:
    """Atomic outbox notification generator; invoked in the same transaction as match writes."""
    if not config.enabled or job.status != "open":
        return 0

    groups: dict[uuid.UUID, list[dict]] = {}
    for profile, match in matching_rows(db, job):
        groups.setdefault(profile.user_id, []).append(
            {
                "id": str(profile.id),
                "name": profile.name,
                "score": match.score,
                "evidence": match.evidence,
            }
        )

    if not groups:
        return 0

    company = db.get(Company, job.company_id)
    company_name = company.name if company else "Company"
    source = db.get(JobSource, job.source_id)
    career_url = source.career_url if source else None
    fingerprint = material_hash(job)
    created = 0

    for owner, profiles in groups.items():
        kind = "new_job" if work.event_kind == "new" else "changed_job"
        if kind == "changed_job" and (
            config.changed_policy == "off"
            or (config.changed_policy == "newly_relevant" and owner in previous_users)
        ):
            continue

        revision = "initial" if kind == "new_job" else fingerprint

        existing = db.scalar(
            select(Notification)
            .where(
                Notification.user_id == owner,
                Notification.job_id == job.id,
                Notification.kind == kind,
                Notification.revision == revision,
            )
            .with_for_update()
        )

        user = db.get(User, owner)
        recipient = user.email if user else ""

        payload = json.loads(
            json.dumps(
                {
                    "kind": kind,
                    "recipient": recipient,
                    "company": company_name,
                    "job": material_fields(job)
                    | {
                        "id": str(job.id),
                        "source_url": job.source_url,
                        "career_url": career_url,
                    },
                    "profiles": profiles,
                },
                default=str,
            )
        )

        if existing:
            # Pending and unattempted outbox record can be updated with aggregated evidence
            if (
                existing.status == "pending"
                and existing.attempts == 0
                and existing.material_hash == fingerprint
            ):
                existing.payload = payload
            continue

        # A changed revision already represented by a prior alert with the same material hash is skipped
        if db.scalar(
            select(Notification.id).where(
                Notification.user_id == owner,
                Notification.job_id == job.id,
                Notification.material_hash == fingerprint,
            )
        ):
            continue

        db.add(
            Notification(
                user_id=owner,
                job_id=job.id,
                kind=kind,
                revision=revision,
                material_hash=fingerprint,
                payload=payload,
                available_at=datetime.now(UTC),
            )
        )
        created += 1

    db.flush()
    return created
