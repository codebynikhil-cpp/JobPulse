import os
import subprocess
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.catalog import SourceType
from app.models.catalog import Company, JobSource
from app.models.job import Job
from app.schemas.catalog import CompanyCreate, CompanyOut, SourceCreate, SourceOut
from app.schemas.job import JobCreate, JobOut
from app.services import catalog, jobs


@pytest.fixture
def db(migrated_database):
    with Session(migrated_database) as session:
        yield session
        session.rollback()


def graph(db, source_type="greenhouse", slug="acme"):
    company = catalog.create_company(db, CompanyCreate(name="Acme", slug=slug))
    source = catalog.create_source(
        db,
        SourceCreate(
            company_id=company.id, source_type=source_type, config={"board": "public-board"}
        ),
    )
    return company, source


def job_data(company, source, **overrides):
    return JobCreate(
        company_id=company.id,
        source_id=source.id,
        external_job_id="job-123",
        title="Software Engineer",
        application_url="https://example.com/jobs/123",
        **overrides,
    )


@pytest.mark.parametrize(
    "source_type", ["greenhouse", "lever", "ashby", "workday", "api", "custom"]
)
def test_source_classification_persists_without_adapters(db, source_type):
    company, source = graph(db, source_type)
    source.active = True
    source_id, company_id = source.id, company.id
    db.commit()
    db.expire_all()
    stored = catalog.get_source(db, source_id)
    result = SourceOut.model_validate(stored).model_dump(mode="json")
    assert result["source_type"] == source_type
    assert result["health_status"] == "unknown"
    assert result["active"] is True
    assert result["last_checked_at"] is None
    assert "supported" not in result and "adapter_available" not in result
    assert result["config"] == {"board": "public-board"}
    assert len(catalog.list_sources(db, company_id)) == 1
    assert CompanyOut.model_validate(catalog.get_company(db, company_id)).slug == "acme"


@pytest.mark.parametrize("bad", ["fake", "unsupported", "Greenhouse", "other", "", "scraper"])
def test_source_type_rejected_in_schema_and_database(db, bad):
    company, source = graph(db)
    with pytest.raises(ValidationError):
        SourceCreate(company_id=company.id, source_type=bad)
    with pytest.raises(IntegrityError) as error:
        db.execute(
            text("UPDATE job_sources SET source_type = :value WHERE id = :id"),
            {"value": bad, "id": source.id},
        )
    assert error.value.orig.sqlstate == "23514"
    db.rollback()


def test_exact_classification_set():
    assert {item.value for item in SourceType} == {
        "greenhouse",
        "lever",
        "ashby",
        "workday",
        "api",
        "custom",
    }


def test_job_round_trip_and_lookup(db):
    company, source = graph(db)
    job = jobs.create_job(
        db,
        job_data(
            company,
            source,
            description="A role",
            location="India",
            employment_type="full_time",
            experience_text="0-2 years",
            min_exp_years=0,
            max_exp_years=2,
            source_url="https://example.com/careers",
            raw_data={"departments": ["Engineering"], "extra": {"public": True}},
            content_hash="a" * 64,
        ),
    )
    job_id, company_id, source_id = job.id, company.id, source.id
    db.commit()
    db.expire_all()
    stored = jobs.get_job(db, job_id)
    output = JobOut.model_validate(stored)
    assert output.title == "Software Engineer"
    assert output.raw_data["departments"] == ["Engineering"]
    assert output.min_exp_years == 0 and output.max_exp_years == 2
    assert output.status == "open" and output.closed_at is None
    assert output.first_seen_at == output.last_seen_at
    assert output.content_hash == "a" * 64
    assert output.created_at.tzinfo is not None
    assert jobs.get_by_external_id(db, source_id, "job-123").id == job_id
    assert jobs.get_by_external_id(db, source_id, "missing") is None
    assert [item.id for item in jobs.list_jobs(db, company_id)] == [job_id]


def test_unique_job_identity_is_source_scoped(db):
    company, source = graph(db)
    other = catalog.create_source(db, SourceCreate(company_id=company.id, source_type="workday"))
    jobs.create_job(db, job_data(company, source))
    jobs.create_job(db, job_data(company, other))
    db.commit()
    with pytest.raises(IntegrityError) as error:
        jobs.create_job(db, job_data(company, source))
    assert error.value.orig.sqlstate == "23505"
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Job)) == 2


def test_unique_company_slug(db):
    graph(db)
    db.commit()
    with pytest.raises(IntegrityError) as error:
        catalog.create_company(db, CompanyCreate(name="Another", slug="acme"))
    assert error.value.orig.sqlstate == "23505"
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Company)) == 1


def test_source_company_consistency_service_and_database(db):
    company, source = graph(db)
    other = catalog.create_company(db, CompanyCreate(name="Other", slug="other"))
    with pytest.raises(ValueError, match="match its source company"):
        jobs.create_job(db, job_data(other, source))
    stored = jobs.create_job(db, job_data(company, source))
    job_id, other_id = stored.id, other.id
    db.commit()
    with pytest.raises(IntegrityError) as error:
        db.execute(
            text("UPDATE jobs SET company_id = :company WHERE id = :job"),
            {"company": other_id, "job": job_id},
        )
    assert error.value.orig.sqlstate == "23503"
    db.rollback()


@pytest.mark.parametrize("model", [Company, JobSource])
def test_restrict_deletion_preserves_history(db, model):
    company, source = graph(db)
    jobs.create_job(db, job_data(company, source))
    target = company.id if model is Company else source.id
    db.commit()
    with pytest.raises(IntegrityError) as error:
        db.execute(delete(model).where(model.id == target))
    assert error.value.orig.sqlstate == "23503"
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Job)) == 1


def test_explicit_leaf_deletion(db):
    company, source = graph(db)
    job = jobs.create_job(db, job_data(company, source))
    db.flush()
    db.execute(delete(Job).where(Job.id == job.id))
    db.execute(delete(JobSource).where(JobSource.id == source.id))
    db.execute(delete(Company).where(Company.id == company.id))
    db.commit()
    assert db.scalar(select(func.count()).select_from(Company)) == 0


def test_missing_references(db):
    with pytest.raises(LookupError):
        catalog.create_source(db, SourceCreate(company_id=uuid.uuid4(), source_type="api"))
    with pytest.raises(LookupError):
        jobs.get_job(db, uuid.uuid4())
    company, source = graph(db)
    source.company_id = uuid.uuid4()
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


@pytest.mark.parametrize(
    "bad",
    [
        {"title": " "},
        {"external_job_id": ""},
        {"title": "x" * 301},
        {"application_url": "file:///secret"},
        {"employment_type": "other"},
        {"min_exp_years": -1},
        {"min_exp_years": 0.01},
        {"min_exp_years": 5, "max_exp_years": 2},
        {"content_hash": "invalid"},
        {"status": "new"},
        {"status": "closed"},
        {"first_seen_at": "2026-01-01T00:00:00"},
        {"first_seen_at": "2026-01-02T00:00:00Z", "last_seen_at": "2026-01-01T00:00:00Z"},
        {"closed_at": "2026-01-01T00:00:00Z"},
        {"raw_data": {"nested": ["bad" + chr(0)]}},
        {"description": "bad" + chr(0)},
        {"raw_data": {"bad": float("inf")}},
    ],
)
def test_job_schema_validation(bad):
    payload = {
        "company_id": uuid.uuid4(),
        "source_id": uuid.uuid4(),
        "external_job_id": "x",
        "title": "Engineer",
        "application_url": "https://example.com/job",
    }
    with pytest.raises(ValidationError):
        JobCreate.model_validate({**payload, **bad})


@pytest.mark.parametrize(
    "bad", [{"name": " "}, {"slug": "UPPER"}, {"slug": "../bad"}, {"name": "bad" + chr(0)}]
)
def test_company_schema_validation(bad):
    with pytest.raises(ValidationError):
        CompanyCreate.model_validate({"name": "Acme", "slug": "acme", **bad})


@pytest.mark.parametrize(
    "bad", [{"poll_interval_sec": 0}, {"config": []}, {"config": {"nested": {"x": "bad" + chr(0)}}}]
)
def test_source_schema_validation(bad):
    with pytest.raises(ValidationError):
        SourceCreate.model_validate({"company_id": uuid.uuid4(), "source_type": "custom", **bad})


@pytest.mark.parametrize(
    "sql,value",
    [
        ("UPDATE job_sources SET poll_interval_sec = :value", 0),
        ("UPDATE job_sources SET consecutive_failures = :value", -1),
        ("UPDATE job_sources SET health_status = :value", "available"),
        ("UPDATE jobs SET min_exp_years = :value", -1),
        ("UPDATE jobs SET max_exp_years = :value", -1),
        ("UPDATE jobs SET status = :value", "closed"),
        ("UPDATE jobs SET content_hash = :value", "invalid"),
    ],
)
def test_database_checks(db, sql, value):
    company, source = graph(db)
    jobs.create_job(db, job_data(company, source))
    with pytest.raises(IntegrityError) as error:
        db.execute(text(sql), {"value": value})
    assert error.value.orig.sqlstate == "23514"
    db.rollback()


def test_closed_job_storage_does_not_run_monitoring(db):
    company, source = graph(db, "workday")
    seen = datetime.now(UTC) - timedelta(days=1)
    record = jobs.create_job(
        db,
        job_data(
            company,
            source,
            first_seen_at=seen,
            last_seen_at=seen,
            closed_at=datetime.now(UTC),
            status="closed",
        ),
    )
    assert JobOut.model_validate(record).status == "closed"
    assert source.last_checked_at is None


def test_transaction_failure_rolls_back_complete_graph(db):
    with pytest.raises(IntegrityError):
        with db.begin():
            company, source = graph(db)
            jobs.create_job(db, job_data(company, source))
            jobs.create_job(db, job_data(company, source))
    for model in (Company, JobSource, Job):
        assert db.scalar(select(func.count()).select_from(model)) == 0


def test_schema_inventory_and_indexes(migrated_database):
    inspector = inspect(migrated_database)
    assert set(inspector.get_table_names()) == {
        "alembic_version",
        "users",
        "auth_sessions",
        "auth_rate_limits",
        "profiles",
        "profile_roles",
        "profile_skills",
        "profile_locations",
        "profile_exclusions",
        "companies",
        "job_sources",
        "jobs",
    }
    indexes = {tuple(item["column_names"]) for item in inspector.get_indexes("jobs")}
    assert {
        ("content_hash",),
        ("company_id", "closed_at"),
        ("first_seen_at",),
        ("source_id",),
    } <= indexes
    unique = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("jobs")}
    assert ("source_id", "external_job_id") in unique
    assert all(
        item["options"]["ondelete"] == "RESTRICT" for item in inspector.get_foreign_keys("jobs")
    )


def test_migration_round_trip_preserves_profiles_and_auth(client, migrated_database):
    assert (
        client.post(
            "/api/auth/signup",
            json={"email": "migration@example.com", "password": "a strong password 123"},
        ).status_code
        == 201
    )
    profile = client.post("/api/profiles", json={"name": "Keep this profile"}).json()
    env = dict(os.environ, DATABASE_URL=migrated_database.url.render_as_string(hide_password=False))
    subprocess.run(["alembic", "downgrade", "0003"], env=env, check=True)
    try:
        assert "companies" not in inspect(migrated_database).get_table_names()
        assert client.get("/api/auth/me").status_code == 200
        assert client.get(f"/api/profiles/{profile['id']}").status_code == 200
    finally:
        subprocess.run(["alembic", "upgrade", "head"], env=env, check=True)
    assert client.get("/api/auth/me").status_code == 200
    assert client.get(f"/api/profiles/{profile['id']}").status_code == 200
