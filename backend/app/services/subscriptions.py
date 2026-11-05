from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.catalog import Company, JobSource
from app.models.job import Job
from app.models.monitoring import ProfileCompany
from app.models.profile import Profile
from app.schemas.subscription import SubscriptionCompanyOut
from app.services.current_matches import current_matches
from app.sources.registry import DEFAULT_REGISTRY


def derive_source_health(source: JobSource | None, company: Company | None) -> str:
    """Documented user-facing source health derivation:
    - unsupported: source is inactive, company is disabled, or adapter not supported.
    - failing: consecutive_failures >= 3 or state failing.
    - degraded: consecutive_failures between 1 and 2 or state degraded.
    - healthy: active, enabled, zero consecutive failures.
    """
    if (
        source is None
        or not source.active
        or (company and not company.enabled)
        or source.health_status == "unsupported"
        or not DEFAULT_REGISTRY.supports(
            source.source_type, source.acquisition_method, source.adapter_key
        )
    ):
        return "unsupported"
    if source.consecutive_failures >= 3 or source.health_status == "failing":
        return "failing"
    if 1 <= source.consecutive_failures < 3 or source.health_status == "degraded":
        return "degraded"
    return "healthy"


def list_user_company_subscriptions(
    db: Session, user_id: uuid.UUID
) -> list[SubscriptionCompanyOut]:
    """Retrieve all available companies along with the user's active monitoring status."""
    companies = list(
        db.scalars(
            select(Company)
            .where(
                or_(
                    Company.enabled.is_(True),
                    Company.id.in_(
                        select(ProfileCompany.company_id)
                        .join(Profile, Profile.id == ProfileCompany.profile_id)
                        .where(Profile.user_id == user_id, Profile.active.is_(True))
                    ),
                )
            )
            .order_by(Company.name)
        )
    )

    # Active profiles for user
    profiles = list(
        db.scalars(
            select(Profile).where(
                Profile.user_id == user_id,
                Profile.active.is_(True),
            )
        )
    )
    user_prof_ids = [p.id for p in profiles]
    prof_names = {p.id: p.name for p in profiles}

    # Profile companies subscriptions for this user
    user_subs = db.execute(
        select(ProfileCompany.company_id, ProfileCompany.profile_id).where(
            ProfileCompany.profile_id.in_(user_prof_ids)
        )
    ).all()

    subs_by_company: dict[uuid.UUID, list[uuid.UUID]] = {}
    for cid, pid in user_subs:
        subs_by_company.setdefault(cid, []).append(pid)

    # Primary source per company
    sources = list(
        db.scalars(
            select(JobSource).where(
                JobSource.company_id.in_([c.id for c in companies]),
            )
        )
    )
    sources_by_company: dict[uuid.UUID, JobSource] = {}
    company_by_id = {c.id: c for c in companies}
    severity = {"healthy": 0, "degraded": 1, "failing": 2, "unsupported": 3}
    for source in sorted(sources, key=lambda s: str(s.id)):
        previous = sources_by_company.get(source.company_id)
        company = company_by_id[source.company_id]
        if (
            previous is None
            or severity[derive_source_health(source, company)]
            > severity[derive_source_health(previous, company)]
        ):
            sources_by_company[source.company_id] = source

    # Recent matching open jobs count per company for this user
    match_counts = dict(
        db.execute(
            current_matches(user_id)
            .with_only_columns(Job.company_id, func.count(func.distinct(Job.id)))
            .where(Job.status == "open")
            .group_by(Job.company_id)
        ).all()
    )

    items: list[SubscriptionCompanyOut] = []
    for c in companies:
        sub_pids = subs_by_company.get(c.id, [])
        is_sub = len(sub_pids) > 0
        catalog_source = sources_by_company.get(c.id)
        src = catalog_source if is_sub else None
        health = derive_source_health(src, c) if is_sub else None

        items.append(
            SubscriptionCompanyOut(
                company_id=c.id,
                company_name=c.name,
                company_slug=c.slug,
                career_url=catalog_source.career_url if catalog_source else None,
                source_id=src.id if src else None,
                source_health=health,
                last_checked_at=src.last_checked_at if src else None,
                last_success_at=src.last_success_at if src else None,
                recent_failure=bool(src and src.consecutive_failures > 0),
                acquisition_method=src.acquisition_method if src else None,
                is_subscribed=is_sub,
                subscribed_profile_ids=sub_pids,
                subscribed_profile_names=[prof_names[pid] for pid in sub_pids if pid in prof_names],
                recent_matches_count=match_counts.get(c.id, 0),
            )
        )
    return items


def toggle_company_subscription(
    db: Session,
    user_id: uuid.UUID,
    company_id: uuid.UUID,
    subscribed: bool,
    profile_id: uuid.UUID | None = None,
) -> None:
    """Subscribe or unsubscribe user profiles for a company."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    if profile_id is not None:
        profile = db.scalar(
            select(Profile).where(
                Profile.id == profile_id,
                Profile.user_id == user_id,
            )
        )
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found for this user")
        target_pids = [profile.id]
    else:
        # All active profiles for this user
        target_pids = list(
            db.scalars(
                select(Profile.id).where(
                    Profile.user_id == user_id,
                    Profile.active.is_(True),
                )
            )
        )
        if not target_pids:
            raise HTTPException(status_code=400, detail="User has no active profiles to subscribe")

    if subscribed:
        for pid in target_pids:
            db.execute(
                insert(ProfileCompany)
                .values(profile_id=pid, company_id=company_id)
                .on_conflict_do_nothing()
            )
    else:
        db.execute(
            delete(ProfileCompany).where(
                ProfileCompany.company_id == company_id,
                ProfileCompany.profile_id.in_(target_pids),
            )
        )
    db.commit()


def get_source_health_for_user(
    db: Session, user_id: uuid.UUID, source_id: uuid.UUID
) -> dict[str, Any]:
    """Retrieve source health for sources the authenticated user is subscribed to."""
    source = db.get(JobSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    company = db.get(Company, source.company_id)

    # Authorization: user must have at least one active profile subscribed to this source's company
    has_sub = db.scalar(
        select(ProfileCompany.profile_id)
        .join(Profile, Profile.id == ProfileCompany.profile_id)
        .where(
            ProfileCompany.company_id == source.company_id,
            Profile.user_id == user_id,
            Profile.active.is_(True),
        )
        .limit(1)
    )
    if not has_sub:
        raise HTTPException(
            status_code=403, detail="You are not subscribed to this source's company"
        )

    health = derive_source_health(source, company)
    return {
        "source_id": str(source.id),
        "company_id": str(source.company_id),
        "company_name": company.name if company else "Company",
        "career_url": source.career_url,
        "health_status": health,
        "acquisition_method": source.acquisition_method,
        "last_checked_at": source.last_checked_at,
        "last_success_at": source.last_success_at,
        "recent_failure": source.consecutive_failures > 0,
        "consecutive_failures": source.consecutive_failures,
        "active": source.active,
    }
