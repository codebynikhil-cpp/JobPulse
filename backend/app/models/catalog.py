import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.catalog import SourceType
from app.db.session import Base
from app.models.mixins import Timestamps


class Company(Timestamps, Base):
    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_companies_name"),
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="ck_companies_slug"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class JobSource(Timestamps, Base):
    __tablename__ = "job_sources"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_job_sources_identity_company"),
        CheckConstraint("poll_interval_sec >= 60", name="ck_job_sources_poll_interval"),
        CheckConstraint("consecutive_failures >= 0", name="ck_job_sources_failures"),
        CheckConstraint(
            "health_status IN ('unknown','healthy','degraded','failing','unsupported')",
            name="ck_job_sources_health",
        ),
        CheckConstraint("jsonb_typeof(config) = 'object'", name="ck_job_sources_config"),
        CheckConstraint(
            "acquisition_method IN ('http','browser')", name="ck_job_sources_acquisition"
        ),
        CheckConstraint(
            "acquisition_method != 'browser' OR career_url IS NOT NULL",
            name="ck_job_sources_browser_url",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    source_type: Mapped[SourceType] = mapped_column(
        Enum(
            SourceType,
            values_callable=lambda items: [item.value for item in items],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            length=16,
            name="ck_job_sources_source_type",
        )
    )
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    career_url: Mapped[str | None] = mapped_column(String(2048))
    acquisition_method: Mapped[str] = mapped_column(
        String(16), default="http", server_default="http"
    )
    adapter_key: Mapped[str | None] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    poll_interval_sec: Mapped[int] = mapped_column(Integer, default=3600)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    health_status: Mapped[str] = mapped_column(String(16), default="unknown")
