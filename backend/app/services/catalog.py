import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Company, JobSource
from app.schemas.catalog import CompanyCreate, SourceCreate


def get_company(db: Session, company_id: uuid.UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise LookupError("Company not found")
    return company


def get_source(db: Session, source_id: uuid.UUID) -> JobSource:
    source = db.get(JobSource, source_id)
    if source is None:
        raise LookupError("Source not found")
    return source


def create_company(db: Session, data: CompanyCreate) -> Company:
    company = Company(**data.model_dump())
    db.add(company)
    db.flush()
    return company


def create_source(db: Session, data: SourceCreate) -> JobSource:
    get_company(db, data.company_id)
    values = data.model_dump()
    values["career_url"] = str(data.career_url) if data.career_url else None
    source = JobSource(**values)
    db.add(source)
    db.flush()
    return source


def list_sources(db: Session, company_id: uuid.UUID, *, limit: int = 100) -> list[JobSource]:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    return list(
        db.scalars(
            select(JobSource)
            .where(JobSource.company_id == company_id)
            .order_by(JobSource.created_at, JobSource.id)
            .limit(limit)
        )
    )
