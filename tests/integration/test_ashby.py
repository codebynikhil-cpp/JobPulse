import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.catalog import SourceType
from app.models.job import Job
from app.schemas.catalog import CompanyCreate, SourceCreate
from app.services import catalog
from app.services.ingestion import ingest_source
from app.services.normalization import normalize_job
from app.sources.ashby import AshbyAdapter
from app.sources.base import RawJob, SourceError
from app.sources.registry import AVAILABLE_ADAPTERS, build_adapter

FIXTURE = Path(__file__).parents[1] / "fixtures" / "ashby" / "board.json"


@pytest.fixture(autouse=True)
def no_live_dns(monkeypatch):
    async def verified():
        pass

    monkeypatch.setattr("app.sources.ashby.verify_public_host", verified)


def board():
    return json.loads(FIXTURE.read_text())


def fetch(payload=None, status=200, headers=None):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(status, json=payload, headers=headers)
            )
        ) as client:
            return await AshbyAdapter({"job_board_name": "globex"}, client).fetch_jobs()

    return asyncio.run(run())


def setup_source(engine):
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as db:
        company = catalog.create_company(
            db, CompanyCreate(name="Ashby Globex", slug=uuid.uuid4().hex)
        )
        source = catalog.create_source(
            db,
            SourceCreate(
                company_id=company.id,
                source_type="ashby",
                config={"job_board_name": "globex"},
            ),
        )
        source_id = source.id
    return factory, source_id


def test_registry_supports_ashby():
    assert SourceType.ASHBY in AVAILABLE_ADAPTERS
    client = httpx.AsyncClient()
    adapter = build_adapter(SourceType.ASHBY, {"job_board_name": "globex"}, client)
    assert isinstance(adapter, AshbyAdapter)


def test_ashby_fetch_success():
    raws = fetch(board())
    assert len(raws) == 2
    first = raws[0]
    assert isinstance(first, RawJob)
    assert first.external_id == "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"
    assert first.title == "Lead Backend Engineer"
    assert "data pipelines" in first.description
    assert first.location == "San Francisco, CA"
    assert first.url == "https://jobs.ashbyhq.com/globex/a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"
    assert first.employment_type == "full_time"
    assert first.posted_at == datetime.fromisoformat("2026-09-30T12:00:00+00:00")


def test_ashby_normalization():
    raw = fetch(board())[0]
    cid = uuid.uuid4()
    sid = uuid.uuid4()
    seen = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    norm = normalize_job(raw, company_id=cid, source_id=sid, seen_at=seen)
    assert norm.company_id == cid
    assert norm.source_id == sid
    assert norm.external_job_id == raw.external_id
    assert norm.title == "Lead Backend Engineer"
    assert norm.location == "San Francisco, CA"
    assert norm.content_hash is not None


def test_ashby_duplicate_external_ids():
    data = board()
    dupe_data = {"apiVersion": "1", "jobs": [data["jobs"][0], dict(data["jobs"][0])]}
    with pytest.raises(SourceError, match="duplicate job ids"):
        fetch(dupe_data)


def test_ashby_missing_required_fields():
    data = board()
    bad_data = {"apiVersion": "1", "jobs": [dict(data["jobs"][0], title="")]}
    with pytest.raises(SourceError, match="missing required title"):
        fetch(bad_data)

    bad_url = {"apiVersion": "1", "jobs": [dict(data["jobs"][0], jobUrl="", applyUrl="")]}
    with pytest.raises(SourceError, match="missing jobUrl or applyUrl"):
        fetch(bad_url)


def test_ashby_malformed_response():
    with pytest.raises(SourceError, match="JSON object"):
        fetch(["not", "an", "object"])

    with pytest.raises(SourceError, match="missing jobs list"):
        fetch({"apiVersion": "1"})


def test_ashby_retry_transient_and_succeed():
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(500, json={"error": "server error"})
        return httpx.Response(200, json=board())

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = AshbyAdapter(
                {"job_board_name": "globex"}, client, sleep=lambda s: asyncio.sleep(0.001)
            )
            return await adapter.fetch_jobs()

    jobs = asyncio.run(run())
    assert len(jobs) == 2
    assert attempts == 3


def test_ashby_retry_exhausted():
    def handler(request):
        return httpx.Response(503, json={"error": "unavailable"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = AshbyAdapter(
                {"job_board_name": "globex"}, client, sleep=lambda s: asyncio.sleep(0.001)
            )
            return await adapter.fetch_jobs()

    with pytest.raises(SourceError, match="retry budget exhausted|HTTP status 503"):
        asyncio.run(run())


def test_ashby_health_check():
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json=board()))
        ) as client:
            adapter = AshbyAdapter({"job_board_name": "globex"}, client)
            return await adapter.health_check()

    health = asyncio.run(run())
    assert health.healthy is True

    async def run_fail():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: httpx.Response(404, text="Not Found"))
        ) as client:
            adapter = AshbyAdapter(
                {"job_board_name": "globex"}, client, sleep=lambda s: asyncio.sleep(0.001)
            )
            return await adapter.health_check()

    health_fail = asyncio.run(run_fail())
    assert health_fail.healthy is False


def test_ashby_ingest_source_integration(migrated_database):
    factory, source_id = setup_source(migrated_database)

    def transport_handler(request):
        return httpx.Response(200, json=board())

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport_handler)) as client:
            adapter = AshbyAdapter({"job_board_name": "globex"}, client)
            return await ingest_source(factory, source_id, adapter=adapter)

    summary = asyncio.run(run())
    assert summary.fetched_count == 2
    assert summary.created_count == 2

    # Verify idempotency: running again creates no duplicates
    summary2 = asyncio.run(run())
    assert summary2.fetched_count == 2
    assert summary2.created_count == 0  # already exists

    with factory() as db:
        jobs = list(db.scalars(select(Job).where(Job.source_id == source_id)))
        assert len(jobs) == 2
        assert all(j.status == "open" for j in jobs)
