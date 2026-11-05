from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.jobs import router as jobs_router
from app.api.notifications import router as notifications_router
from app.api.profiles import router as profiles_router
from app.api.subscriptions import router as subscriptions_router
from app.core.config import settings
from app.db.session import SessionLocal

app = FastAPI(title="JobPulse")

if settings.app_origin:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.app_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

app.include_router(auth_router)
app.include_router(profiles_router)
app.include_router(notifications_router)
app.include_router(jobs_router)
app.include_router(subscriptions_router)
app.include_router(dashboard_router)


@app.get("/api/health")
def health():
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok"}
