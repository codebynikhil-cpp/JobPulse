import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.schemas.job import JobCreate
from app.services.catalog import get_source


def create_job(db: Session, data: JobCreate) -> Job:
    source = get_source(db, data.source_id)
    if source.company_id != data.company_id:
        raise ValueError("Job company must match its source company")
    values = data.model_dump()
    values["application_url"] = str(data.application_url)
    values["source_url"] = str(data.source_url) if data.source_url else None
    job = Job(**values)
    db.add(job)
    db.flush()
    return job


def get_job(db: Session, job_id: uuid.UUID) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise LookupError("Job not found")
    return job


def get_by_external_id(db: Session, source_id: uuid.UUID, external_job_id: str) -> Job | None:
    return db.scalar(
        select(Job).where(Job.source_id == source_id, Job.external_job_id == external_job_id)
    )


def list_jobs(db: Session, company_id: uuid.UUID, *, limit: int = 100) -> list[Job]:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    return list(
        db.scalars(
            select(Job)
            .where(Job.company_id == company_id)
            .order_by(Job.first_seen_at.desc(), Job.id)
            .limit(limit)
        )
    )
