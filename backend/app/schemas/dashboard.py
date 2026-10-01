from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.schemas.job_feed import JobFeedItem
from app.schemas.subscription import SubscriptionCompanyOut


class DashboardStats(BaseModel):
    active_profiles_count: int
    monitored_companies_count: int
    new_jobs_count: int
    saved_jobs_count: int
    applied_jobs_count: int
    ignored_jobs_count: int
    unread_notifications_count: int


class SourceHealthSummary(BaseModel):
    healthy_count: int
    degraded_count: int
    failing_count: int
    unsupported_count: int


class DashboardResponse(BaseModel):
    stats: DashboardStats
    source_health_summary: SourceHealthSummary
    recent_jobs: list[JobFeedItem]
    recent_notifications: list[dict[str, Any]]
    monitored_companies: list[SubscriptionCompanyOut]
