import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import Timestamps


class ProfileCompany(Timestamps, Base):
    __tablename__ = "profile_companies"
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class MonitorRun(Timestamps, Base):
    __tablename__ = "monitor_runs"
    __table_args__ = (
        Index("ix_monitor_runs_source_started", "source_id", "started_at"),
        CheckConstraint(
            "status IN ('running','success','partial','failed','anomaly','unsupported','disabled','not_due','abandoned')",
            name="ck_monitor_runs_status",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at", name="ck_monitor_runs_times"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_sources.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="running")
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class SourceMonitorState(Timestamps, Base):
    __tablename__ = "source_monitor_state"
    __table_args__ = (
        CheckConstraint(
            "last_clean_count IS NULL OR last_clean_count >= 0", name="ck_source_monitor_count"
        ),
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_sources.id", ondelete="CASCADE"), primary_key=True
    )
    last_clean_count: Mapped[int | None] = mapped_column(Integer)


class JobMonitorState(Timestamps, Base):
    __tablename__ = "job_monitor_state"
    __table_args__ = (
        CheckConstraint("missing_count >= 0", name="ck_job_monitor_missing"),
        Index("ix_job_monitor_pending", "pending", "job_id"),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    missing_count: Mapped[int] = mapped_column(Integer, default=0)
    pending: Mapped[bool] = mapped_column(Boolean, default=False)


class JobMatch(Timestamps, Base):
    __tablename__ = "job_matches"
    __table_args__ = (
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 100", name="ck_job_matches_score"),
        CheckConstraint("status IN ('evaluated','error')", name="ck_job_matches_status"),
        CheckConstraint(
            "(status = 'evaluated' AND matched IS NOT NULL AND score IS NOT NULL) OR (status = 'error' AND matched IS NULL AND score IS NULL)",
            name="ck_job_matches_state",
        ),
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    matched: Mapped[bool | None] = mapped_column(Boolean)
    score: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    profile_hash: Mapped[str] = mapped_column(String(64))
    matcher_identity: Mapped[str] = mapped_column(String(100))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB)
