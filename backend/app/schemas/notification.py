from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    job_id: uuid.UUID
    kind: str
    revision: str
    material_hash: str
    status: str
    attempts: int
    available_at: datetime
    first_attempt_at: datetime | None
    sent_at: datetime | None
    read_at: datetime | None = None
    is_read: bool = False
    delivery_status: str = "pending"
    company_name: str = "Company"
    job_title: str = "Job"
    match_score: int = 0
    matching_profiles: list[str] = []
    apply_url: str | None = None
    created_at: datetime
    updated_at: datetime


class NotificationReadResponse(BaseModel):
    id: uuid.UUID
    read_at: datetime
    is_read: bool = True


class NotificationReadAllResponse(BaseModel):
    marked_count: int
