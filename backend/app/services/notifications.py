from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification import Notification


def list_user_notifications(
    db: Session,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Notification]:
    """Retrieve owner-scoped notifications ordered by most recent."""
    query = select(Notification).where(Notification.user_id == user_id)
    if status:
        query = query.where(Notification.status == status)
    return list(
        db.scalars(
            query.order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


def get_user_notification(
    db: Session, user_id: uuid.UUID, notification_id: uuid.UUID
) -> Notification:
    """Retrieve a single notification ensuring owner authorization."""
    notif = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    if notif is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notif
