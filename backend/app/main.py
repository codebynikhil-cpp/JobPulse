from fastapi import FastAPI
from sqlalchemy import text

from app.api.auth import router
from app.db.session import SessionLocal

app = FastAPI(title="JobPulse")
app.include_router(router)


@app.get("/api/health")
def health():
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok"}
