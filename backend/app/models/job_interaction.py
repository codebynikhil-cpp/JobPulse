from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import Timestamps


class UserJobInteraction(Timestamps, Base):
    __tablename__ = "user_job_interactions"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_user_job_interactions"),
        Index("ix_user_job_interactions_user_status", "user_id", "status"),
        CheckConstraint(
            "status IN ('saved', 'applied', 'ignored')",
            name="ck_user_job_interactions_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
