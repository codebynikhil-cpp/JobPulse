from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends

from app.api.auth import check_origin
from app.api.dependencies import DB, CurrentUser
from app.schemas.subscription import SubscriptionCompanyOut, SubscriptionToggle
from app.services import subscriptions

router = APIRouter(tags=["subscriptions"])


@router.get("/api/subscriptions", response_model=list[SubscriptionCompanyOut])
def list_subscriptions(
    db: DB,
    user: CurrentUser,
) -> list[SubscriptionCompanyOut]:
    """List career companies with the user's active monitoring status and source health."""
    return subscriptions.list_user_company_subscriptions(db, user.id)


@router.post("/api/subscriptions/toggle", dependencies=[Depends(check_origin)])
def toggle_subscription(
    body: SubscriptionToggle,
    db: DB,
    user: CurrentUser,
) -> dict[str, Any]:
    """Toggle user monitoring subscription for a company."""
    subscriptions.toggle_company_subscription(
        db,
        user_id=user.id,
        company_id=body.company_id,
        subscribed=body.subscribed,
        profile_id=body.profile_id,
    )
    return {"ok": True, "company_id": str(body.company_id), "subscribed": body.subscribed}


@router.patch("/api/subscriptions/{company_id}", dependencies=[Depends(check_origin)])
def update_subscription(
    company_id: uuid.UUID,
    body: SubscriptionToggle,
    db: DB,
    user: CurrentUser,
) -> dict[str, Any]:
    """Update subscription for a specific company."""
    subscriptions.toggle_company_subscription(
        db,
        user_id=user.id,
        company_id=company_id,
        subscribed=body.subscribed,
        profile_id=body.profile_id,
    )
    return {"ok": True, "company_id": str(company_id), "subscribed": body.subscribed}


@router.get("/api/sources/{source_id}/health")
def get_source_health(
    source_id: uuid.UUID,
    db: DB,
    user: CurrentUser,
) -> dict[str, Any]:
    """Retrieve source health. Strictly authorized to sources the user monitors."""
    return subscriptions.get_source_health_for_user(db, user.id, source_id)
