import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, HttpUrl, JsonValue, field_validator, model_validator

from app.schemas.catalog import DataModel
from app.schemas.profile import EmploymentType

Years = Annotated[Decimal, Field(ge=0, le=100, max_digits=4, decimal_places=1)]


class JobCreate(DataModel):
    company_id: uuid.UUID
    source_id: uuid.UUID
    external_job_id: str = Field(min_length=1, max_length=512)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=1000000)
    location: str = Field(default="", max_length=300)
    employment_type: EmploymentType | None = None
    experience_text: str | None = Field(default=None, max_length=1000000)
    min_exp_years: Years | None = None
    max_exp_years: Years | None = None
    posted_at: AwareDatetime | None = None
    first_seen_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: AwareDatetime = Field(default_factory=lambda data: data["first_seen_at"])
    closed_at: AwareDatetime | None = None
    application_url: HttpUrl
    source_url: HttpUrl | None = None
    raw_data: dict[str, JsonValue] = Field(default_factory=dict)
    content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    status: Literal["open", "closed"] = "open"

    @field_validator("external_job_id", "title")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value cannot be blank")
        return value

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (
            self.min_exp_years is not None
            and self.max_exp_years is not None
            and self.min_exp_years > self.max_exp_years
        ):
            raise ValueError("Minimum experience must not exceed maximum experience")
        if self.last_seen_at < self.first_seen_at:
            raise ValueError("last_seen_at must not precede first_seen_at")
        if self.status == "closed" and (
            self.closed_at is None or self.closed_at < self.last_seen_at
        ):
            raise ValueError("Closed jobs require closed_at at or after last_seen_at")
        if self.status == "open" and self.closed_at is not None:
            raise ValueError("Open jobs must not have closed_at")
        return self


class JobOut(JobCreate):
    id: uuid.UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
