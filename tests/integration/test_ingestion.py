import asyncio
import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.catalog import SourceType
from app.models.catalog import JobSource
from app.models.job import Job
from app.schemas.catalog import CompanyCreate, SourceCreate
from app.services import catalog
from app.services.ingestion import IngestionError, ingest_source
from app.services.normalization import description_text, normalize_job, normalize_url
from app.sources.base import RawJob, SourceError
from app.sources.fake import FakeSource
from app.sources.greenhouse import HOST, GreenhouseAdapter
from app.sources.registry import AVAILABLE_ADAPTERS, build_adapter

FIXTURE = Path(__file__).parents[1] / "fixtures" / "greenhouse" / "board.json"


@pytest.fixture(autouse=True)
def no_live_dns(monkeypatch):
    async def verified():
        pass

    monkeypatch.setattr("app.sources.greenhouse.verify_public_host", verified)


def board():
    return json.loads(FIXTURE.read_text())


def fetch(payload=None, status=200, headers=None):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(status, json=payload, headers=headers)
            )
        ) as client:
            return await GreenhouseAdapter({"board_token": "acme"}, client).fetch_jobs()

    return asyncio.run(run())


def raws():
    return fetch(board())


def canonical(raw=None):
    return normalize_job(
        raw or raws()[0],
        company_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        seen_at=datetime(2026, 10, 1, tzinfo=UTC),
    )


def setup_source(engine, source_type="greenhouse"):
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as db:
        company = catalog.create_company(db, CompanyCreate(name="Acme", slug=uuid.uuid4().hex))
        source = catalog.create_source(
            db,
            SourceCreate(
                company_id=company.id,
                source_type=source_type,
                config={"board_token": "acme"},
            ),
        )
        source_id = source.id
    return factory, source_id


def run(factory, source_id, adapter):
    return asyncio.run(ingest_source(factory, source_id, adapter=adapter))


def test_request_and_complete_board_contract():
    seen = []

    async def scenario():
        def handler(request):
            seen.append(request)
            return httpx.Response(200, json=board())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await GreenhouseAdapter({"board_token": "acme"}, client).fetch_jobs()
            assert len(result) == 5
            assert result[2].external_id == "103"  # null internal id is legitimate
            assert all(job.posted_at is None and job.employment_type is None for job in result)
            assert result[0].raw == board()["jobs"][0]

    asyncio.run(scenario())
    assert len(seen) == 1  # documented endpoint returns entire board, no fake pagination
    assert str(seen[0].url) == f"{HOST}/v1/boards/acme/jobs?content=true"
    assert seen[0].extensions["timeout"]["connect"] == 5


@pytest.mark.parametrize(
    "config",
    [
        {"board_token": "../evil"},
        {"board_token": "https://evil"},
        {"board_token": "x?redirect=evil"},
        {"board_token": ""},
        {"board_token": "x", "url": "http://127.0.0.1"},
    ],
)
def test_config_cannot_change_destination(config):
    async def scenario():
        async with httpx.AsyncClient() as client:
            with pytest.raises(SourceError):
                GreenhouseAdapter(config, client)

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [301, 302, 400, 401, 403, 404, 422])
def test_normal_errors_and_redirects_not_retried(status):
    calls = []

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: (
                    calls.append(request)
                    or httpx.Response(status, headers={"Location": "http://127.0.0.1"})
                )
            )
        ) as client:
            with pytest.raises(SourceError):
                await GreenhouseAdapter({"board_token": "acme"}, client).fetch_jobs()

    asyncio.run(scenario())
    assert len(calls) == 1


@pytest.mark.parametrize("failure", [429, 500, 503, "timeout", "connection"])
def test_transient_failure_retry_then_success(failure):
    calls, sleeps = [], []

    async def sleep(delay):
        sleeps.append(delay)

    async def scenario():
        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                if failure == "timeout":
                    raise httpx.ReadTimeout("timeout", request=request)
                if failure == "connection":
                    raise httpx.ConnectError("connection", request=request)
                return httpx.Response(failure, headers={"Retry-After": "2"})
            return httpx.Response(200, json=board())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert (
                len(
                    await GreenhouseAdapter(
                        {"board_token": "acme"}, client, sleep=sleep
                    ).fetch_jobs()
                )
                == 5
            )

    asyncio.run(scenario())
    assert len(calls) == 2
    assert sleeps == ([0.5] if isinstance(failure, str) else [2])


def test_retry_exhaustion():
    calls = []

    async def sleep(delay):
        pass

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: calls.append(request) or httpx.Response(503)
            )
        ) as client:
            with pytest.raises(SourceError, match="503"):
                await GreenhouseAdapter({"board_token": "acme"}, client, sleep=sleep).fetch_jobs()

    asyncio.run(scenario())
    assert len(calls) == 3


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"jobs": [], "meta": {"total": 1}},
        {"jobs": [], "meta": {"total": True}},
        {"jobs": [{"id": True}], "meta": {"total": 1}},
        {"jobs": [{"id": 1}], "meta": {"total": 1}},
        {"jobs": [board()["jobs"][0]] * 2, "meta": {"total": 2}},
    ],
)
def test_malformed_or_incomplete_payload(payload):
    with pytest.raises(SourceError):
        fetch(payload)


def test_invalid_json_and_response_limit():
    async def scenario(content):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=content))
        ) as client:
            with pytest.raises(SourceError):
                await GreenhouseAdapter({"board_token": "acme"}, client).fetch_jobs()

    asyncio.run(scenario(b"not json"))
    asyncio.run(scenario(b"x" * 20_000_001))


def test_retry_guidance_budget():
    assert GreenhouseAdapter._retry_delay("3", 0) == 3
    assert GreenhouseAdapter._retry_delay("invalid", 0) == 0.5
    assert GreenhouseAdapter._retry_delay("-1", 0) == 0.5
    with pytest.raises(SourceError):
        GreenhouseAdapter._retry_delay("60", 0)


def test_available_adapters_registered_other_types_remain_valid():
    assert AVAILABLE_ADAPTERS == {SourceType.GREENHOUSE, SourceType.LEVER, SourceType.ASHBY}

    async def scenario():
        async with httpx.AsyncClient() as client:
            for kind in SourceType:
                if kind not in AVAILABLE_ADAPTERS:
                    with pytest.raises(SourceError, match="No adapter"):
                        build_adapter(kind, {}, client)

    asyncio.run(scenario())


def test_normalized_required_fields_and_nulls():
    job = canonical()
    assert job.external_job_id == "101"
    assert job.title == "Software Engineer"
    assert job.location == "New York"
    assert job.description == "Build reliable services."
    assert job.employment_type is None and job.experience_text is None
    assert job.min_exp_years is None and job.max_exp_years is None and job.posted_at is None
    assert job.raw_data == board()["jobs"][0]
    assert job.first_seen_at == job.last_seen_at
    assert str(job.application_url) == str(job.source_url)


def test_explicit_raw_publication_and_employment_supported():
    at = datetime(2026, 9, 1, tzinfo=UTC)
    job = canonical(replace(raws()[0], posted_at=at, employment_type="full_time"))
    assert job.posted_at == at and job.employment_type == "full_time"


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "Changed title"),
        ("location", "Berlin"),
        ("description", "Changed responsibilities"),
        ("url", "https://example.com/job/2"),
        ("employment_type", "contract"),
    ],
)
def test_material_changes_change_hash(field, value):
    assert canonical().content_hash != canonical(replace(raws()[0], **{field: value})).content_hash


def test_hash_stable_for_unstable_fields_and_equivalent_markup():
    raw = raws()[0]
    changed = replace(
        raw,
        title="  Software   Engineer ",
        description="<p>Build reliable services.</p>",
        raw={"updated_at": "new"},
        posted_at=datetime.now(UTC),
        url=raw.url + "/?utm_source=test#fragment",
    )
    assert canonical(raw).content_hash == canonical(changed).content_hash


@pytest.mark.parametrize(
    "raw",
    [
        RawJob("", "title", "", "", "https://example.com"),
        RawJob("1", " ", "", "", "https://example.com"),
        RawJob("1", "title", "", "", "javascript:alert(1)"),
        RawJob("1", "title", "", "", "https://example.com", employment_type="invented"),
    ],
)
def test_invalid_canonical_record(raw):
    with pytest.raises((ValidationError, ValueError)):
        canonical(raw)


def test_url_identity_preserved_and_text_extraction():
    assert (
        normalize_url("https://EXAMPLE.com/jobs/?gh_jid=123&utm_source=x#top")
        == "https://example.com/jobs?gh_jid=123"
    )
    assert (
        description_text("&amp;lt;p&amp;gt;Hello&amp;lt;/p&amp;gt;<script>bad()</script>")
        == "Hello"
    )


def test_mandatory_fake_source_three_run_acceptance(migrated_database):
    factory, source_id = setup_source(migrated_database)
    records = raws()
    fake = FakeSource([records[:2], records[2:]])
    first = run(factory, source_id, fake)
    assert (first.fetched_count, first.normalized_count, first.created_count) == (
        5,
        5,
        5,
    )
    with factory() as db:
        originals = {j.external_job_id: (j.id, j.first_seen_at) for j in db.scalars(select(Job))}
    second = run(factory, source_id, fake)
    assert (second.created_count, second.updated_count, second.unchanged_count) == (
        0,
        0,
        5,
    )
    fake.batches[0][0] = replace(records[0], title="Updated Software Engineer")
    third = run(factory, source_id, fake)
    assert (third.created_count, third.updated_count, third.unchanged_count) == (
        0,
        1,
        4,
    )
    assert third.failed_count == 0 and third.duration_seconds >= 0
    with factory() as db:
        stored = list(db.scalars(select(Job)))
        assert len(stored) == 5
        assert {j.external_job_id: (j.id, j.first_seen_at) for j in stored} == originals
        assert (
            next(j for j in stored if j.external_job_id == "101").title
            == "Updated Software Engineer"
        )
        assert all(j.last_seen_at >= j.first_seen_at and j.posted_at is None for j in stored)
        source = db.get(JobSource, source_id)
        assert source.last_success_at == source.last_checked_at and source.last_error_at is None


def test_same_external_ids_different_sources(migrated_database):
    factory, first = setup_source(migrated_database)
    _, second = setup_source(migrated_database)
    assert run(factory, first, FakeSource([raws()])).created_count == 5
    assert run(factory, second, FakeSource([raws()])).created_count == 5
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 10


@pytest.mark.parametrize("mode", ["fetch", "normalize", "duplicates"])
def test_failed_run_never_closes_or_partially_writes(migrated_database, mode):
    factory, source_id = setup_source(migrated_database)
    run(factory, source_id, FakeSource([raws()]))
    with factory() as db:
        last_success = db.get(JobSource, source_id).last_success_at
    if mode == "fetch":
        fake = FakeSource([], error=SourceError("controlled failure"))
    elif mode == "normalize":
        fake = FakeSource(
            [[replace(raws()[0], title="would update"), replace(raws()[1], url="bad")]]
        )
    else:
        fake = FakeSource([[raws()[0], raws()[0]]])
    with pytest.raises(IngestionError) as caught:
        run(factory, source_id, fake)
    assert caught.value.result.created_count == caught.value.result.updated_count == 0
    assert caught.value.result.failed_count > 0
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 5
        assert all(j.status == "open" and j.closed_at is None for j in db.scalars(select(Job)))
        assert (
            db.scalar(select(Job).where(Job.external_job_id == "101")).title == "Software Engineer"
        )
        source = db.get(JobSource, source_id)
        assert source.last_error_at and source.last_success_at == last_success
    run(factory, source_id, FakeSource([raws()]))
    with factory() as db:
        source = db.get(JobSource, source_id)
        assert source.consecutive_failures == 0 and source.last_error_at is not None


def test_successful_empty_does_not_close_jobs(migrated_database):
    factory, source_id = setup_source(migrated_database)
    run(factory, source_id, FakeSource([raws()]))
    result = run(factory, source_id, FakeSource([]))
    assert result.fetched_count == result.created_count == result.failed_count == 0
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 5
        assert all(j.status == "open" for j in db.scalars(select(Job)))


def test_greenhouse_mock_to_database(migrated_database):
    factory, source_id = setup_source(migrated_database)

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=board()))
        ) as client:
            adapter = GreenhouseAdapter({"board_token": "acme"}, client)
            assert (await ingest_source(factory, source_id, adapter=adapter)).created_count == 5
            assert (await ingest_source(factory, source_id, adapter=adapter)).created_count == 0

    asyncio.run(scenario())
