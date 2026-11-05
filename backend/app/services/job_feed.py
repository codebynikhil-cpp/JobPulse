from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.catalog import Company
from app.models.job import Job
from app.models.job_interaction import UserJobInteraction
from app.models.monitoring import JobMatch
from app.models.profile import Profile
from app.schemas.job_feed import JobFeedItem, JobFeedResponse, MatchedProfileInfo
from app.services.current_matches import current_matches


def extract_match_reasons(evidence: dict[str, Any] | None) -> list[str]:
    """Extract human-readable match explanations from persisted MatchResult evidence."""
    if not evidence or not isinstance(evidence, dict):
        return []
    persisted = evidence.get("reasons")
    if isinstance(persisted, list):
        return [r for r in persisted if isinstance(r, str)]
    reasons: list[str] = []
    breakdown = evidence.get("breakdown")
    if isinstance(breakdown, dict):
        roles = breakdown.get("matched_roles")
        if roles and isinstance(roles, list):
            reasons.append(f"Role matched: {', '.join(str(r) for r in roles)}")
        skills = breakdown.get("matched_skills")
        if skills and isinstance(skills, list):
            reasons.append(f"Skills matched: {', '.join(str(s) for s in skills)}")
        loc = breakdown.get("location_match")
        if loc and loc is not True:
            reasons.append(f"Location: {loc}")
        elif loc is True:
            reasons.append("Location matched")
        exp = breakdown.get("exp_match")
        if exp and exp is not True:
            reasons.append(f"Experience: {exp}")
        elif exp is True:
            reasons.append("Experience compatible")
        wm = breakdown.get("work_mode_match")
        if wm and wm is not True:
            reasons.append(f"Work mode: {wm}")
        elif wm is True:
            reasons.append("Work mode matched")

    summary = evidence.get("summary")
    if summary and isinstance(summary, str) and not reasons:
        reasons.append(summary.strip())
    return reasons


def get_user_job_feed(
    db: Session,
    user_id: uuid.UUID,
    *,
    profile_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
    location: str | None = None,
    job_status: str | None = "open",
    user_status: str | None = None,
    min_score: float | None = None,
    employment_type: str | None = None,
    search: str | None = None,
    discovered_after: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> JobFeedResponse:
    """Retrieve paginated, profile-aware jobs matched for the user.

    Multiple matching profiles for the same job are aggregated into a single item.
    """
    base_match = current_matches(user_id).with_only_columns(JobMatch.job_id)

    if profile_id:
        base_match = base_match.where(Profile.id == profile_id)
    if min_score is not None:
        base_match = base_match.where(JobMatch.score >= min_score)

    # Core query for distinct jobs
    query = (
        select(
            Job,
            Company.name.label("company_name"),
            UserJobInteraction.status.label("user_interaction_status"),
        )
        .join(Company, Company.id == Job.company_id)
        .outerjoin(
            UserJobInteraction,
            (UserJobInteraction.job_id == Job.id) & (UserJobInteraction.user_id == user_id),
        )
        .where(Job.id.in_(base_match))
    )

    if discovered_after is not None:
        query = query.where(Job.first_seen_at >= discovered_after)
    if company_id:
        query = query.where(Job.company_id == company_id)
    if job_status:
        query = query.where(Job.status == job_status)
    if location:
        query = query.where(Job.location.ilike(f"%{location.strip()}%"))
    if employment_type:
        query = query.where(Job.employment_type == employment_type)
    if search:
        s = f"%{search.strip()}%"
        query = query.where(
            or_(Job.title.ilike(s), Job.description.ilike(s), Company.name.ilike(s))
        )

    # User interaction status filter
    if user_status == "saved":
        query = query.where(UserJobInteraction.status == "saved")
    elif user_status == "applied":
        query = query.where(UserJobInteraction.status == "applied")
    elif user_status == "ignored":
        query = query.where(UserJobInteraction.status == "ignored")
    elif user_status == "new":
        query = query.where(UserJobInteraction.status.is_(None))
    elif user_status is None:
        # Default view: hide ignored jobs unless explicitly requested
        query = query.where(
            or_(UserJobInteraction.status.is_(None), UserJobInteraction.status != "ignored")
        )

    # Total count query
    count_subquery = query.subquery()
    total_count = db.scalar(select(func.count()).select_from(count_subquery)) or 0

    # Pagination and sorting
    offset = (page - 1) * page_size
    query = (
        query.order_by(
            func.coalesce(Job.posted_at, Job.first_seen_at).desc(),
            Job.id.desc(),
        )
        .offset(offset)
        .limit(page_size)
    )

    rows = db.execute(query).all()
    job_ids = [row.Job.id for row in rows]

    if not job_ids:
        return JobFeedResponse(
            items=[],
            total=total_count,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total_count / page_size) if total_count > 0 else 0,
        )

    # Fetch all matching profile details for these jobs in a single query
    match_query = (
        current_matches(user_id)
        .with_only_columns(JobMatch, Profile.name.label("profile_name"))
        .where(JobMatch.job_id.in_(job_ids))
    )

    matches_by_job: dict[uuid.UUID, list[MatchedProfileInfo]] = {}
    for match, prof_name in db.execute(match_query).all():
        evidence = match.evidence or {}
        reasons = extract_match_reasons(evidence)
        matches_by_job.setdefault(match.job_id, []).append(
            MatchedProfileInfo(
                profile_id=match.profile_id,
                profile_name=prof_name,
                score=float(match.score or 0.0),
                evidence=evidence,
                match_reasons=reasons,
            )
        )

    items: list[JobFeedItem] = []
    for row in rows:
        job = row.Job
        matched_profiles = matches_by_job.get(job.id, [])
        best_score = max((p.score for p in matched_profiles), default=0.0)

        # Score filter if specified
        if min_score is not None and best_score < min_score:
            continue

        all_reasons = []
        for p in matched_profiles:
            for r in p.match_reasons:
                if r not in all_reasons:
                    all_reasons.append(r)

        items.append(
            JobFeedItem(
                id=job.id,
                company_id=job.company_id,
                company_name=row.company_name,
                title=job.title,
                description=job.description,
                location=job.location,
                employment_type=job.employment_type,
                experience_text=job.experience_text,
                min_exp_years=float(job.min_exp_years) if job.min_exp_years is not None else None,
                max_exp_years=float(job.max_exp_years) if job.max_exp_years is not None else None,
                posted_at=job.posted_at,
                first_seen_at=job.first_seen_at,
                application_url=job.application_url,
                source_url=job.source_url,
                status=job.status,
                user_status=row.user_interaction_status or "new",
                best_score=best_score,
                matched_profiles=matched_profiles,
                match_reasons=all_reasons,
            )
        )

    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0
    return JobFeedResponse(
        items=items,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


def get_user_job_detail(db: Session, user_id: uuid.UUID, job_id: uuid.UUID) -> JobFeedItem:
    """Retrieve full details of a specific job for the authenticated user."""
    from app.services.job_interactions import require_matched_job

    require_matched_job(db, user_id, job_id)
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    company = db.get(Company, job.company_id)
    company_name = company.name if company else "Company"

    interaction = db.scalar(
        select(UserJobInteraction).where(
            UserJobInteraction.job_id == job_id,
            UserJobInteraction.user_id == user_id,
        )
    )

    matches = db.execute(
        current_matches(user_id)
        .with_only_columns(JobMatch, Profile.name.label("profile_name"))
        .where(JobMatch.job_id == job_id)
    ).all()

    matched_profiles: list[MatchedProfileInfo] = []
    all_reasons: list[str] = []
    for match, prof_name in matches:
        evidence = match.evidence or {}
        reasons = extract_match_reasons(evidence)
        for r in reasons:
            if r not in all_reasons:
                all_reasons.append(r)
        matched_profiles.append(
            MatchedProfileInfo(
                profile_id=match.profile_id,
                profile_name=prof_name,
                score=float(match.score or 0.0),
                evidence=evidence,
                match_reasons=reasons,
            )
        )

    best_score = max((p.score for p in matched_profiles), default=0.0)

    return JobFeedItem(
        id=job.id,
        company_id=job.company_id,
        company_name=company_name,
        title=job.title,
        description=job.description,
        location=job.location,
        employment_type=job.employment_type,
        experience_text=job.experience_text,
        min_exp_years=float(job.min_exp_years) if job.min_exp_years is not None else None,
        max_exp_years=float(job.max_exp_years) if job.max_exp_years is not None else None,
        posted_at=job.posted_at,
        first_seen_at=job.first_seen_at,
        application_url=job.application_url,
        source_url=job.source_url,
        status=job.status,
        user_status=interaction.status if interaction else "new",
        best_score=best_score,
        matched_profiles=matched_profiles,
        match_reasons=all_reasons,
    )
