from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    job_id: uuid.UUID
    kind: str
    revision: str
    material_hash: str
    payload: dict[str, Any]
    status: str
    attempts: int
    available_at: datetime
    first_attempt_at: datetime | None
    sent_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
