from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JobInteractionUpdate(BaseModel):
    status: Literal["new", "saved", "applied", "ignored"]
    notes: str = Field(default="", max_length=2000)


class JobInteractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    status: str
    applied_at: datetime | None
    notes: str
    updated_at: datetime
