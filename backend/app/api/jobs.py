from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.auth import check_origin
from app.api.dependencies import DB, CurrentUser
from app.schemas.job_feed import JobFeedItem, JobFeedResponse
from app.schemas.job_interaction import JobInteractionOut, JobInteractionUpdate
from app.services import job_feed, job_interactions

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=JobFeedResponse)
def list_jobs(
    db: DB,
    user: CurrentUser,
    profile_id: Annotated[uuid.UUID | None, Query()] = None,
    company_id: Annotated[uuid.UUID | None, Query()] = None,
    location: Annotated[str | None, Query()] = None,
    job_status: Annotated[str | None, Query()] = "open",
    user_status: Annotated[str | None, Query()] = None,
    min_score: Annotated[float | None, Query(ge=0, le=100)] = None,
    employment_type: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    discovered_after: Annotated[datetime | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> JobFeedResponse:
    """Retrieve paginated, profile-aware jobs matched for the authenticated user."""
    return job_feed.get_user_job_feed(
        db,
        user.id,
        profile_id=profile_id,
        company_id=company_id,
        location=location,
        job_status=job_status,
        user_status=user_status,
        min_score=min_score,
        employment_type=employment_type,
        search=search,
        discovered_after=discovered_after,
        page=page,
        page_size=page_size,
    )


@router.get("/{job_id}", response_model=JobFeedItem)
def get_job_detail(
    job_id: uuid.UUID,
    db: DB,
    user: CurrentUser,
) -> JobFeedItem:
    """Retrieve single job with user match explanation and interaction state."""
    return job_feed.get_user_job_detail(db, user.id, job_id)


@router.get("/{job_id}/status", response_model=JobInteractionOut)
def get_job_interaction_status(
    job_id: uuid.UUID,
    db: DB,
    user: CurrentUser,
) -> JobInteractionOut:
    """Retrieve user-specific interaction status for a canonical job."""
    interaction = job_interactions.get_user_job_interaction(db, user.id, job_id)
    if interaction is None:
        return JobInteractionOut(
            job_id=job_id,
            status="new",
            applied_at=None,
            notes="",
            updated_at=datetime.now(UTC),
        )
    return interaction  # type: ignore[return-value]


@router.patch(
    "/{job_id}/status", response_model=JobInteractionOut, dependencies=[Depends(check_origin)]
)
@router.post(
    "/{job_id}/status", response_model=JobInteractionOut, dependencies=[Depends(check_origin)]
)
def update_job_interaction_status(
    job_id: uuid.UUID,
    body: JobInteractionUpdate,
    db: DB,
    user: CurrentUser,
) -> JobInteractionOut:
    """Update user-specific interaction status without altering canonical Job table."""
    result = job_interactions.set_user_job_interaction(
        db, user.id, job_id, body.status, notes=body.notes
    )
    return JobInteractionOut(**result)
