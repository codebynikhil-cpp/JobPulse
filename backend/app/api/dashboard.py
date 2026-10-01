from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import DB, CurrentUser
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard import get_user_dashboard

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def get_dashboard(
    db: DB,
    user: CurrentUser,
) -> DashboardResponse:
    """Retrieve authenticated user dashboard overview metrics, recent items, and source health."""
    return get_user_dashboard(db, user.id)
