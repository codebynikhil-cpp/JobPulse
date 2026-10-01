from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.dependencies import DB, CurrentUser
from app.models.notification import Notification
from app.notifications.metrics import get_notification_metrics
from app.schemas.notification import NotificationOut
from app.services import notifications

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    db: DB,
    user: CurrentUser,
    status: Annotated[
        Literal["pending", "processing", "sent", "failed", "permanently_failed", "cancelled"]
        | None,
        Query(),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Notification]:
    return notifications.list_user_notifications(
        db, user.id, status=status, limit=limit, offset=offset
    )


@router.get("/metrics")
def get_metrics(
    db: DB,
    user: CurrentUser,
) -> dict:
    metrics = get_notification_metrics(db)
    return metrics.to_dict()


@router.get("/{notification_id}", response_model=NotificationOut)
def get_notification(
    notification_id: uuid.UUID,
    db: DB,
    user: CurrentUser,
) -> Notification:
    return notifications.get_user_notification(db, user.id, notification_id)
