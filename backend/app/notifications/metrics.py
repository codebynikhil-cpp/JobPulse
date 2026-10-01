from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Float, case, cast, func, select
from sqlalchemy.orm import Session

from app.models.notification import Notification


@dataclass(frozen=True)
class NotificationMetrics:
    pending_count: int = 0
    processing_count: int = 0
    sent_count: int = 0
    failed_count: int = 0
    permanently_failed_count: int = 0
    total_count: int = 0
    avg_attempts: float = 0.0
    avg_latency_seconds: float | None = None
    max_latency_seconds: float | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pending_count": self.pending_count,
            "processing_count": self.processing_count,
            "sent_count": self.sent_count,
            "failed_count": self.failed_count,
            "permanently_failed_count": self.permanently_failed_count,
            "total_count": self.total_count,
            "avg_attempts": round(self.avg_attempts, 2),
            "avg_latency_seconds": round(self.avg_latency_seconds, 2)
            if self.avg_latency_seconds is not None
            else None,
            "max_latency_seconds": round(self.max_latency_seconds, 2)
            if self.max_latency_seconds is not None
            else None,
            "last_error": self.last_error,
        }


def get_notification_metrics(db: Session, user_id: uuid.UUID | None = None) -> NotificationMetrics:
    """Compute aggregate observability metrics for the notification outbox."""
    scope = [Notification.user_id == user_id] if user_id else []
    row = db.execute(
        select(
            func.count().label("total"),
            func.coalesce(func.sum(case((Notification.status == "pending", 1), else_=0)), 0).label(
                "pending"
            ),
            func.coalesce(
                func.sum(case((Notification.status == "processing", 1), else_=0)), 0
            ).label("processing"),
            func.coalesce(func.sum(case((Notification.status == "sent", 1), else_=0)), 0).label(
                "sent"
            ),
            func.coalesce(func.sum(case((Notification.status == "failed", 1), else_=0)), 0).label(
                "failed"
            ),
            func.coalesce(
                func.sum(case((Notification.status == "permanently_failed", 1), else_=0)), 0
            ).label("permanently_failed"),
            func.coalesce(func.avg(cast(Notification.attempts, Float)), 0.0).label("avg_attempts"),
        ).where(*scope)
    ).one()

    # Latency: difference between sent_at and created_at in seconds
    latency_row = db.execute(
        select(
            func.avg(
                func.extract("epoch", Notification.sent_at)
                - func.extract("epoch", Notification.created_at)
            ).label("avg_latency"),
            func.max(
                func.extract("epoch", Notification.sent_at)
                - func.extract("epoch", Notification.created_at)
            ).label("max_latency"),
        ).where(*scope, Notification.status == "sent", Notification.sent_at.is_not(None))
    ).one()

    last_err = db.scalar(
        select(Notification.last_error)
        .where(*scope, Notification.last_error.is_not(None))
        .order_by(Notification.updated_at.desc())
        .limit(1)
    )

    avg_lat = float(latency_row.avg_latency) if latency_row.avg_latency is not None else None
    max_lat = float(latency_row.max_latency) if latency_row.max_latency is not None else None

    return NotificationMetrics(
        pending_count=int(row.pending),
        processing_count=int(row.processing),
        sent_count=int(row.sent),
        failed_count=int(row.failed),
        permanently_failed_count=int(row.permanently_failed),
        total_count=int(row.total),
        avg_attempts=float(row.avg_attempts),
        avg_latency_seconds=avg_lat,
        max_latency_seconds=max_lat,
        last_error=last_err,
    )
