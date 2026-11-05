from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.job_interaction import UserJobInteraction
from app.models.monitoring import JobMatch
from app.services.current_matches import current_matches


def get_user_job_interaction(
    db: Session, user_id: uuid.UUID, job_id: uuid.UUID
) -> UserJobInteraction | None:
    """Retrieve interaction state for a specific job and user."""
    require_matched_job(db, user_id, job_id)
    return db.scalar(
        select(UserJobInteraction).where(
            UserJobInteraction.user_id == user_id,
            UserJobInteraction.job_id == job_id,
        )
    )


def set_user_job_interaction(
    db: Session,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    status: str,
    notes: str = "",
) -> dict:
    """Update or remove user interaction state.

    Setting status to 'new' restores the job by removing the interaction record.
    Canonical Job entity remains completely untouched.
    """
    require_matched_job(db, user_id, job_id)

    if status == "new":
        db.execute(
            delete(UserJobInteraction).where(
                UserJobInteraction.user_id == user_id,
                UserJobInteraction.job_id == job_id,
            )
        )
        db.commit()
        return {
            "job_id": job_id,
            "status": "new",
            "applied_at": None,
            "notes": "",
            "updated_at": datetime.now(UTC),
        }

    now = datetime.now(UTC)
    applied_at = now if status == "applied" else None

    stmt = (
        insert(UserJobInteraction)
        .values(
            user_id=user_id,
            job_id=job_id,
            status=status,
            notes=notes,
            applied_at=applied_at,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=[UserJobInteraction.user_id, UserJobInteraction.job_id],
            set_={
                "status": status,
                "notes": notes,
                "applied_at": applied_at,
                "updated_at": now,
            },
        )
        .returning(UserJobInteraction)
    )
    result = db.scalar(stmt)
    db.commit()
    return {
        "job_id": result.job_id,
        "status": result.status,
        "applied_at": result.applied_at,
        "notes": result.notes,
        "updated_at": result.updated_at,
    }


def require_matched_job(db: Session, user_id: uuid.UUID, job_id: uuid.UUID) -> None:
    match = db.scalar(
        current_matches(user_id)
        .with_only_columns(JobMatch.job_id)
        .where(JobMatch.job_id == job_id)
        .limit(1)
    )
    if match is None:
        raise HTTPException(status_code=404, detail="Job not found")
