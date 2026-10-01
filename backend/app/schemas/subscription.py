from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SubscriptionCompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_id: uuid.UUID
    company_name: str
    company_slug: str
    career_url: str | None
    source_id: uuid.UUID | None
    source_health: str | None
    last_checked_at: datetime | None
    last_success_at: datetime | None
    recent_failure: bool
    acquisition_method: str | None
    is_subscribed: bool
    subscribed_profile_ids: list[uuid.UUID]
    subscribed_profile_names: list[str]
    recent_matches_count: int


class SubscriptionToggle(BaseModel):
    company_id: uuid.UUID
    profile_id: uuid.UUID | None = None
    subscribed: bool
