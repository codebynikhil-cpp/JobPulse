import asyncio
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.models.catalog import JobSource
from app.models.job import Job
from app.services import ingestion
from app.services.normalization import normalize_job
from app.sources.base import SourceError
from app.sources.fake import FakeSource
from app.sources.greenhouse import GreenhouseAdapter, verify_public_host
from tests.integration.test_ingestion import raws, run, setup_source


@pytest.fixture(autouse=True)
def no_live_dns(monkeypatch):
    async def verified():
        pass

    monkeypatch.setattr("app.sources.greenhouse.verify_public_host", verified)


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "192.168.0.2"])
def test_private_dns_addresses_blocked(monkeypatch, ip):
    async def scenario():
        async def resolve(*args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
        with pytest.raises(SourceError, match="non-public"):
            await verify_public_host()

    asyncio.run(scenario())


def test_public_dns_and_dns_failure(monkeypatch):
    async def scenario():
        async def resolve(*args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]

        loop = asyncio.get_running_loop()
        monkeypatch.setattr(loop, "getaddrinfo", resolve)
        await verify_public_host()

        async def fail(*args, **kwargs):
            raise OSError("controlled DNS failure")

        monkeypatch.setattr(loop, "getaddrinfo", fail)
        with pytest.raises(SourceError, match="DNS"):
            await verify_public_host()

    asyncio.run(scenario())


def test_database_failure_rolls_back_entire_batch(migrated_database, monkeypatch):
    factory, source_id = setup_source(migrated_database)
    records = [replace(raws()[0], title="A"), replace(raws()[1], title="B")]
    original = ingestion.upsert_job
    calls = 0

    def fail_second(db, data):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("controlled persistence failure")
        return original(db, data)

    monkeypatch.setattr(ingestion, "upsert_job", fail_second)
    with pytest.raises(ingestion.IngestionError):
        run(factory, source_id, FakeSource([records]))
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 0
        assert db.get(JobSource, source_id).last_error_at is not None


@pytest.mark.parametrize("newer_failed", [False, True])
def test_superseded_run_cannot_overwrite_newer_data(migrated_database, newer_failed):
    factory, source_id = setup_source(migrated_database)
    with factory.begin() as db:
        source = db.get(JobSource, source_id)
        future = datetime.now(UTC) + timedelta(days=1)
        source.last_checked_at = future
        if newer_failed:
            source.last_error_at = future
        else:
            source.last_success_at = future
    with pytest.raises(ingestion.IngestionError, match="superseded"):
        run(factory, source_id, FakeSource([raws()]))
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 0
        assert db.get(JobSource, source_id).last_error_at == (future if newer_failed else None)


def test_health_check_and_retry_http_date(monkeypatch):
    async def verified():
        pass

    monkeypatch.setattr("app.sources.greenhouse.verify_public_host", verified)

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(404))
        ) as client:
            health = await GreenhouseAdapter({"board_token": "acme"}, client).health_check()
            assert not health.healthy and "404" in health.detail

    asyncio.run(scenario())
    assert GreenhouseAdapter._retry_delay("Wed, 01 Jan 2020 00:00:00 GMT", 0) == 0.5


def test_database_upsert_safe_for_concurrent_insert(migrated_database):
    factory, source_id = setup_source(migrated_database)
    with factory() as db:
        company_id = db.get(JobSource, source_id).company_id
    data = normalize_job(
        raws()[0], company_id=company_id, source_id=source_id, seen_at=datetime.now(UTC)
    )

    def write():
        with factory.begin() as db:
            return ingestion.upsert_job(db, data)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(write) for _ in range(2)]
        assert sorted(f.result(timeout=10) for f in futures) == ["created", "unchanged"]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 1


def test_returned_closed_job_reopens_with_stable_identity(migrated_database):
    factory, source_id = setup_source(migrated_database)
    run(factory, source_id, FakeSource([raws()[:1]]))
    with factory.begin() as db:
        job = db.scalar(select(Job))
        identity = job.id
        job.status = "closed"
        job.closed_at = job.last_seen_at
    result = run(factory, source_id, FakeSource([raws()[:1]]))
    assert result.created_count == 0
    with factory() as db:
        job = db.scalar(select(Job))
        assert job.id == identity and job.status == "open" and job.closed_at is None
