from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.notification import Notification


def list_user_notifications(
    db: Session,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
    is_read: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Notification]:
    """Retrieve owner-scoped notifications ordered by most recent."""
    query = select(Notification).where(Notification.user_id == user_id)
    if status:
        query = query.where(Notification.status == status)
    if is_read is True:
        query = query.where(Notification.read_at.is_not(None))
    elif is_read is False:
        query = query.where(Notification.read_at.is_(None))

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


def mark_notification_read(
    db: Session, user_id: uuid.UUID, notification_id: uuid.UUID
) -> Notification:
    """Mark a single user notification as read."""
    notif = db.scalar(
        select(Notification)
        .where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
        .with_for_update()
    )
    if notif is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    if notif.read_at is None:
        notif.read_at = datetime.now(UTC)
        db.commit()
        db.refresh(notif)
    return notif


def mark_all_notifications_read(db: Session, user_id: uuid.UUID) -> int:
    """Mark all unread notifications for a user as read."""
    now = datetime.now(UTC)
    result = db.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=now)
    )
    db.commit()
    return result.rowcount or 0
