import math
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from app.core.catalog import SourceType


class DataModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    @field_validator("*", mode="before")
    @classmethod
    def safe_values(cls, value: Any) -> Any:
        def check(item: Any) -> None:
            if isinstance(item, str) and chr(0) in item:
                raise ValueError("Null characters are not allowed")
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError("Nonfinite JSON numbers are not allowed")
            if isinstance(item, dict):
                for k, v in item.items():
                    check(k)
                    check(v)
            if isinstance(item, list):
                for v in item:
                    check(v)

        check(value)
        return value


class CompanyCreate(DataModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=200, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    enabled: bool = True

    @field_validator("name", "slug", mode="before")
    @classmethod
    def trim(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class CompanyOut(CompanyCreate):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SourceCreate(DataModel):
    company_id: uuid.UUID
    source_type: SourceType
    config: dict[str, JsonValue] = Field(default_factory=dict)
    active: bool = False
    poll_interval_sec: int = Field(default=3600, ge=60, le=2147483647)


class SourceOut(SourceCreate):
    id: uuid.UUID
    last_checked_at: datetime | None
    last_success_at: datetime | None
    last_error_at: datetime | None
    consecutive_failures: int
    health_status: Literal["unknown", "healthy", "degraded", "failing", "unsupported"]
    created_at: datetime
    updated_at: datetime
