import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import Timestamps


class Job(Timestamps, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source_id", "external_job_id", name="uq_jobs_source_external_id"),
        ForeignKeyConstraint(
            ["source_id", "company_id"],
            ["job_sources.id", "job_sources.company_id"],
            ondelete="RESTRICT",
            name="fk_jobs_source_company",
        ),
        Index("ix_jobs_content_hash", "content_hash"),
        Index("ix_jobs_company_closed_at", "company_id", "closed_at"),
        Index("ix_jobs_first_seen_at", "first_seen_at"),
        CheckConstraint("length(trim(external_job_id)) > 0", name="ck_jobs_external_id"),
        CheckConstraint("length(trim(title)) > 0", name="ck_jobs_title"),
        CheckConstraint(
            "employment_type IS NULL OR employment_type IN ('full_time','part_time','contract','internship','temporary')",
            name="ck_jobs_employment_type",
        ),
        CheckConstraint(
            "min_exp_years IS NULL OR min_exp_years BETWEEN 0 AND 100", name="ck_jobs_min_exp"
        ),
        CheckConstraint(
            "max_exp_years IS NULL OR max_exp_years BETWEEN 0 AND 100", name="ck_jobs_max_exp"
        ),
        CheckConstraint(
            "min_exp_years IS NULL OR max_exp_years IS NULL OR min_exp_years <= max_exp_years",
            name="ck_jobs_exp_range",
        ),
        CheckConstraint("last_seen_at >= first_seen_at", name="ck_jobs_seen_range"),
        CheckConstraint(
            "(status = 'open' AND closed_at IS NULL) OR (status = 'closed' AND closed_at >= last_seen_at)",
            name="ck_jobs_status_closed",
        ),
        CheckConstraint(
            "status != 'closed' OR closed_at IS NOT NULL", name="ck_jobs_closed_required"
        ),
        CheckConstraint(
            "content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'", name="ck_jobs_content_hash"
        ),
        CheckConstraint("jsonb_typeof(raw_data) = 'object'", name="ck_jobs_raw_data"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    source_id: Mapped[uuid.UUID] = mapped_column(index=True)
    external_job_id: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(300), default="")
    employment_type: Mapped[str | None] = mapped_column(String(24))
    experience_text: Mapped[str | None] = mapped_column(Text)
    min_exp_years: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    max_exp_years: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    application_url: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="open")
