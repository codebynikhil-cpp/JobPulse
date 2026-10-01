from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.auth import check_origin
from app.api.dependencies import DB, CurrentUser
from app.models.notification import Notification
from app.notifications.metrics import get_notification_metrics
from app.schemas.notification import (
    NotificationOut,
    NotificationReadAllResponse,
    NotificationReadResponse,
)
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
    is_read: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Notification]:
    return notifications.list_user_notifications(
        db, user.id, status=status, is_read=is_read, limit=limit, offset=offset
    )


@router.get("/metrics")
def get_metrics(
    db: DB,
    user: CurrentUser,
) -> dict:
    metrics = get_notification_metrics(db, user.id)
    result = metrics.to_dict()
    result.pop("last_error", None)
    return result


@router.patch(
    "/read-all", response_model=NotificationReadAllResponse, dependencies=[Depends(check_origin)]
)
@router.post(
    "/read-all", response_model=NotificationReadAllResponse, dependencies=[Depends(check_origin)]
)
def mark_all_read(
    db: DB,
    user: CurrentUser,
) -> NotificationReadAllResponse:
    count = notifications.mark_all_notifications_read(db, user.id)
    return NotificationReadAllResponse(marked_count=count)


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationReadResponse,
    dependencies=[Depends(check_origin)],
)
@router.post(
    "/{notification_id}/read",
    response_model=NotificationReadResponse,
    dependencies=[Depends(check_origin)],
)
def mark_notification_read(
    notification_id: uuid.UUID,
    db: DB,
    user: CurrentUser,
) -> NotificationReadResponse:
    notif = notifications.mark_notification_read(db, user.id, notification_id)
    assert notif.read_at is not None
    return NotificationReadResponse(id=notif.id, read_at=notif.read_at, is_read=True)


@router.get("/{notification_id}", response_model=NotificationOut)
def get_notification(
    notification_id: uuid.UUID,
    db: DB,
    user: CurrentUser,
) -> Notification:
    return notifications.get_user_notification(db, user.id, notification_id)
