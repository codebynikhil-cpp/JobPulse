from __future__ import annotations

import uuid

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.models.job_interaction import UserJobInteraction
from app.models.monitoring import JobMatch, ProfileCompany
from app.models.notification import Notification
from app.models.profile import Profile
from app.schemas.dashboard import (
    DashboardResponse,
    DashboardStats,
    SourceHealthSummary,
)
from app.services.job_feed import get_user_job_feed
from app.services.notifications import list_user_notifications
from app.services.subscriptions import list_user_company_subscriptions


def get_user_dashboard(db: Session, user_id: uuid.UUID) -> DashboardResponse:
    """Aggregate actionable metrics, recent items, and monitored source health for authenticated user."""
    # Active profiles count
    active_profiles_count = (
        db.scalar(
            select(func.count(Profile.id)).where(
                Profile.user_id == user_id,
                Profile.active.is_(True),
            )
        )
        or 0
    )

    # User active profile IDs
    user_prof_ids = list(
        db.scalars(
            select(Profile.id).where(
                Profile.user_id == user_id,
                Profile.active.is_(True),
            )
        )
    )

    # Monitored companies count (distinct companies across user's active profiles)
    if user_prof_ids:
        monitored_companies_count = (
            db.scalar(
                select(func.count(distinct(ProfileCompany.company_id))).where(
                    ProfileCompany.profile_id.in_(user_prof_ids)
                )
            )
            or 0
        )
    else:
        monitored_companies_count = 0

    # Job interaction counts
    interaction_counts = dict(
        db.execute(
            select(UserJobInteraction.status, func.count(UserJobInteraction.id))
            .where(UserJobInteraction.user_id == user_id)
            .group_by(UserJobInteraction.status)
        ).all()
    )
    saved_jobs_count = interaction_counts.get("saved", 0)
    applied_jobs_count = interaction_counts.get("applied", 0)
    ignored_jobs_count = interaction_counts.get("ignored", 0)

    # New jobs count: matched jobs for user's active profiles without an interaction record
    if user_prof_ids:
        matched_job_ids_subquery = (
            select(JobMatch.job_id)
            .join(Profile, Profile.id == JobMatch.profile_id)
            .where(
                Profile.user_id == user_id,
                Profile.active.is_(True),
                JobMatch.matched.is_(True),
                JobMatch.status == "evaluated",
            )
        )
        new_jobs_count = (
            db.scalar(
                select(func.count(distinct(Job.id)))
                .outerjoin(
                    UserJobInteraction,
                    (UserJobInteraction.job_id == Job.id) & (UserJobInteraction.user_id == user_id),
                )
                .where(
                    Job.id.in_(matched_job_ids_subquery),
                    Job.status == "open",
                    UserJobInteraction.id.is_(None),
                )
            )
            or 0
        )
    else:
        new_jobs_count = 0

    # Unread notifications count
    unread_notifications_count = (
        db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
        )
        or 0
    )

    # Source health summary across user-monitored companies
    monitored_companies = list_user_company_subscriptions(db, user_id)
    subscribed_only = [c for c in monitored_companies if c.is_subscribed]

    healthy_count = sum(1 for c in subscribed_only if c.source_health == "healthy")
    degraded_count = sum(1 for c in subscribed_only if c.source_health == "degraded")
    failing_count = sum(1 for c in subscribed_only if c.source_health == "failing")
    unsupported_count = sum(1 for c in subscribed_only if c.source_health == "unsupported")

    health_summary = SourceHealthSummary(
        healthy_count=healthy_count,
        degraded_count=degraded_count,
        failing_count=failing_count,
        unsupported_count=unsupported_count,
    )

    # Top 5 recent jobs
    recent_feed = get_user_job_feed(db, user_id, page=1, page_size=5)

    # Top 5 recent notifications
    recent_notifs = list_user_notifications(db, user_id, limit=5, offset=0)
    notif_dicts = [
        {
            "id": str(n.id),
            "kind": n.kind,
            "job_id": str(n.job_id),
            "company_name": n.company_name,
            "job_title": n.job_title,
            "match_score": n.match_score,
            "matching_profiles": n.matching_profiles,
            "delivery_status": n.delivery_status,
            "is_read": n.is_read,
            "read_at": n.read_at,
            "apply_url": n.apply_url,
            "created_at": n.created_at,
        }
        for n in recent_notifs
    ]

    return DashboardResponse(
        stats=DashboardStats(
            active_profiles_count=active_profiles_count,
            monitored_companies_count=monitored_companies_count,
            new_jobs_count=new_jobs_count,
            saved_jobs_count=saved_jobs_count,
            applied_jobs_count=applied_jobs_count,
            ignored_jobs_count=ignored_jobs_count,
            unread_notifications_count=unread_notifications_count,
        ),
        source_health_summary=health_summary,
        recent_jobs=recent_feed.items,
        recent_notifications=notif_dicts,
        monitored_companies=subscribed_only,
    )
