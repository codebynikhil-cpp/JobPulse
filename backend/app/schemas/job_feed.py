from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class MatchedProfileInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID
    profile_name: str
    score: float
    evidence: dict[str, Any] = {}
    match_reasons: list[str] = []


class JobFeedItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    company_name: str
    title: str
    description: str
    location: str
    employment_type: str | None
    experience_text: str | None
    min_exp_years: float | None
    max_exp_years: float | None
    posted_at: datetime | None
    first_seen_at: datetime
    application_url: str
    source_url: str | None
    status: str
    user_status: str
    best_score: float
    matched_profiles: list[MatchedProfileInfo]
    match_reasons: list[str] = []


class JobFeedResponse(BaseModel):
    items: list[JobFeedItem]
    total: int
    page: int
    page_size: int
    total_pages: int
