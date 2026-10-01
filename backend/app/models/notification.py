import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import Timestamps


class Notification(Timestamps, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", "kind", "revision", name="uq_notifications_identity"),
        Index("ix_notifications_due", "status", "available_at", "id"),
        Index("ix_notifications_user_read", "user_id", "read_at"),
        Index("ix_notifications_user_created", "user_id", "created_at", "id"),
        CheckConstraint("kind IN ('new_job','changed_job')", name="ck_notifications_kind"),
        CheckConstraint(
            "status IN ('pending','processing','failed','sent','permanently_failed','cancelled')",
            name="ck_notifications_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_notifications_attempts"),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="ck_notifications_payload"),
        CheckConstraint(
            "(status = 'processing') = (claim_token IS NOT NULL AND lease_until IS NOT NULL)",
            name="ck_notifications_claim",
        ),
        CheckConstraint("(status = 'sent') = (sent_at IS NOT NULL)", name="ck_notifications_sent"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24))
    revision: Mapped[str] = mapped_column(String(64))
    material_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[uuid.UUID | None] = mapped_column()
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_id: Mapped[str | None] = mapped_column(String(128))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def next_attempt_at(self) -> datetime:
        return self.available_at

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    @property
    def company_name(self) -> str:
        if isinstance(self.payload, dict):
            return str(self.payload.get("company", "Company"))
        return "Company"

    @property
    def job_title(self) -> str:
        if isinstance(self.payload, dict) and isinstance(self.payload.get("job"), dict):
            return str(self.payload["job"].get("title", "Job"))
        return "Job"

    @property
    def match_score(self) -> int:
        if isinstance(self.payload, dict) and isinstance(self.payload.get("profiles"), list):
            profiles = self.payload["profiles"]
            if profiles and isinstance(profiles[0], dict):
                return max(int(p.get("score", 0)) for p in profiles if isinstance(p, dict))
        return 0

    @property
    def matching_profiles(self) -> list[str]:
        if isinstance(self.payload, dict) and isinstance(self.payload.get("profiles"), list):
            return [
                str(p.get("name", ""))
                for p in self.payload["profiles"]
                if isinstance(p, dict) and p.get("name")
            ]
        return []

    @property
    def apply_url(self) -> str | None:
        if isinstance(self.payload, dict) and isinstance(self.payload.get("job"), dict):
            return self.payload["job"].get("application_url")
        return None

    @property
    def delivery_status(self) -> str:
        return self.status
