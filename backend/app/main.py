from fastapi import FastAPI
from sqlalchemy import text

from app.api.auth import router
from app.api.notifications import router as notifications_router
from app.api.profiles import router as profiles_router
from app.db.session import SessionLocal

app = FastAPI(title="JobPulse")
app.include_router(router)
app.include_router(profiles_router)
app.include_router(notifications_router)


@app.get("/api/health")
def health():
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok"}
