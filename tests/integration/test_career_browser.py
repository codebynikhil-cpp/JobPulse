import asyncio
import socket
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.browser.security import BrowserURLPolicy
from app.models.catalog import JobSource
from app.models.job import Job
from app.models.monitoring import JobMatch
from app.monitoring.config import MonitoringConfig
from app.monitoring.runner import run_source
from app.monitoring.scheduler import due_sources, run_due
from app.schemas.catalog import CompanyCreate, SourceCreate, SourceOut
from app.services import catalog
from app.sources.base import SourceError
from app.sources.registry import DEFAULT_REGISTRY
from tests.integration.career_fixtures import (  # noqa: F401
    FixtureCompanyBrowser,
    fixture_registry,
)
from tests.integration.test_monitoring import profile


@pytest.mark.parametrize("mode", ["pages", "loadmore", "duplicate"])
def test_local_js_jobs_pagination_loadmore_and_network_observation(career_sites, mode):
    origin, _ = career_sites
    adapter = FixtureCompanyBrowser(origin, mode=mode)
    jobs = asyncio.run(adapter.fetch_jobs())
    assert [j.external_id for j in jobs] == ["1", "2", "3"]
    assert all(j.title == "Software Engineer" and j.description == "Python" for j in jobs)
    assert "/a/data" in adapter.requests  # observed XHR/fetch, never guessed static HTML


@pytest.mark.parametrize(
    "mode", ["malformed", "partial", "failure", "conflict", "badurl", "endless"]
)
def test_browser_failures_never_return_partial_batch(career_sites, mode):
    origin, _ = career_sites
    adapter = FixtureCompanyBrowser(origin, mode=mode, max_pages=2)
    with pytest.raises(SourceError):
        asyncio.run(adapter.fetch_jobs())


def test_browser_timeout_then_provider_reusable(career_sites):
    origin, _ = career_sites
    with pytest.raises(SourceError):
        asyncio.run(FixtureCompanyBrowser(origin, mode="timeout", timeout_ms=100).fetch_jobs())
    assert len(asyncio.run(FixtureCompanyBrowser(origin).fetch_jobs())) == 3


def test_browser_health_failure(career_sites):
    origin, _ = career_sites
    assert not asyncio.run(FixtureCompanyBrowser(origin, mode="failure").health_check()).healthy


def test_mandatory_two_company_two_strategy_scheduler_pipeline(migrated_database, career_sites):
    origin, state = career_sites
    factory = sessionmaker(migrated_database, expire_on_commit=False)
    registry = fixture_registry(origin)
    with factory.begin() as db:
        a = catalog.create_company(db, CompanyCreate(name="Company A", slug="company-a"))
        b = catalog.create_company(db, CompanyCreate(name="Company B", slug="company-b"))
        sa = catalog.create_source(
            db,
            SourceCreate(
                company_id=a.id,
                source_type="custom",
                career_url=origin + "/a/careers",
                acquisition_method="browser",
                adapter_key="fixture-browser",
                active=True,
            ),
        )
        sb = catalog.create_source(
            db,
            SourceCreate(
                company_id=b.id,
                source_type="custom",
                career_url=origin + "/b/jobs.json",
                acquisition_method="http",
                adapter_key="fixture-http",
                active=True,
            ),
        )
        a_id, b_id, sa_id, sb_id = a.id, b.id, sa.id, sb.id
    _, owner_a = profile(factory, a_id)
    _, owner_b = profile(factory, a_id)
    pb1, _ = profile(factory, b_id, owner=owner_a, name="Company B profile")
    pb2, _ = profile(factory, b_id, owner=owner_b, name="Company B profile")
    assert {sa_id, sb_id} == set(due_sources(factory, MonitoringConfig(), registry=registry))
    # The fixture registry is injected explicitly, never enabled by stored classifications.
    assert due_sources(factory, MonitoringConfig()) == []
    first = asyncio.run(run_due(factory, registry=registry))
    assert {r.acquisition_method for r in first} == {"http", "browser"}
    assert sum(r.created_count for r in first) == 4
    assert sum(r.evaluated_count for r in first) == sum(r.matched_count for r in first) == 8
    assert all(r.status == "success" for r in first)
    with factory() as db:
        identities = {j.id for j in db.scalars(select(Job))}
        assert len(identities) == 4
        assert db.scalar(select(func.count()).select_from(JobMatch)) == 8
        assert all(m.evidence["components"] for m in db.scalars(select(JobMatch)))

    def make_due():
        with factory.begin() as db:
            for sid in (sa_id, sb_id):
                db.get(JobSource, sid).last_checked_at = None

    make_due()
    repeat = asyncio.run(run_due(factory, registry=registry))
    assert sum(r.created_count for r in repeat) == sum(r.evaluated_count for r in repeat) == 0
    assert sum(r.unchanged_count for r in repeat) == 4
    state["1"] = "Java"
    make_due()
    changed = asyncio.run(run_due(factory, registry=registry))
    assert sum(r.updated_count for r in changed) == 1
    assert sum(r.evaluated_count for r in changed) == 2
    with factory() as db:
        assert {j.id for j in db.scalars(select(Job))} == identities
        assert db.scalar(select(func.count()).select_from(JobMatch)) == 8
        assert (
            db.scalar(select(func.count()).select_from(JobMatch).where(JobMatch.matched.is_(False)))
            == 2
        )
    with factory.begin() as db:
        db.get(JobSource, sa_id).config = {"mode": "partial"}
    make_due()
    isolated = asyncio.run(run_due(factory, registry=registry))
    assert {r.source_id: r.status for r in isolated} == {sa_id: "failed", sb_id: "success"}
    with factory() as db:
        assert {j.id for j in db.scalars(select(Job))} == identities
        assert all(j.status == "open" for j in db.scalars(select(Job)))


@pytest.mark.parametrize("method,key", [("browser", None), ("http", "unknown")])
def test_classification_does_not_imply_acquisition_capability(migrated_database, method, key):
    factory = sessionmaker(migrated_database, expire_on_commit=False)
    with factory.begin() as db:
        c = catalog.create_company(db, CompanyCreate(name="Acme", slug=uuid.uuid4().hex))
        s = catalog.create_source(
            db,
            SourceCreate(
                company_id=c.id,
                source_type="greenhouse",
                acquisition_method=method,
                adapter_key=key,
                career_url="https://example.com/careers",
                active=True,
            ),
        )
        sid = s.id
    assert not due_sources(factory, MonitoringConfig())
    assert asyncio.run(run_source(factory, sid)).status == "unsupported"


def test_company_career_metadata_roundtrip_and_legacy_http(migrated_database):
    factory = sessionmaker(migrated_database, expire_on_commit=False)
    with factory.begin() as db:
        c = catalog.create_company(db, CompanyCreate(name="Global company", slug="global-company"))
        s = catalog.create_source(
            db,
            SourceCreate(
                company_id=c.id,
                source_type="workday",
                acquisition_method="browser",
                career_url="https://example.com/careers",
            ),
        )
        value = SourceOut.model_validate(s)
        assert str(value.career_url) == "https://example.com/careers"
        assert value.source_type.value == "workday" and value.acquisition_method == "browser"
        legacy = catalog.create_source(db, SourceCreate(company_id=c.id, source_type="greenhouse"))
        assert legacy.acquisition_method == "http" and legacy.career_url is None
        assert DEFAULT_REGISTRY.supports(
            legacy.source_type, legacy.acquisition_method, legacy.adapter_key
        )
    with pytest.raises(ValidationError):
        SourceCreate(company_id=c.id, source_type="custom", acquisition_method="browser")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://169.254.169.254/",
        "http://[::1]/",
        "file:///etc/passwd",
        "http://user:pass@example.com",
        "https://other.example/jobs",
    ],
)
def test_browser_network_policy_blocks_private_credentials_and_off_allowlist(url):
    host = __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(url).hostname
    policy = BrowserURLPolicy(
        frozenset({host})
        if host not in ("other.example", "example.com")
        else frozenset({"example.com"})
    )
    with pytest.raises(SourceError):
        asyncio.run(policy.validate(url))


def test_browser_dns_all_addresses_checked(monkeypatch):
    async def scenario():
        loop = asyncio.get_running_loop()

        async def mixed(*args):
            return [
                (socket.AF_INET, 1, 6, "", ("8.8.8.8", 443)),
                (socket.AF_INET, 1, 6, "", ("127.0.0.1", 443)),
            ]

        monkeypatch.setattr(loop, "getaddrinfo", mixed)
        with pytest.raises(SourceError):
            await BrowserURLPolicy(frozenset({"example.com"})).validate("https://example.com")

        async def public(*args):
            return [(socket.AF_INET, 1, 6, "", ("8.8.8.8", 443))]

        monkeypatch.setattr(loop, "getaddrinfo", public)
        await BrowserURLPolicy(frozenset({"example.com"})).validate("https://example.com")

    asyncio.run(scenario())


def test_career_metadata_migration_roundtrip_preserves_sources(migrated_database):
    import os
    import subprocess

    from sqlalchemy import inspect

    factory = sessionmaker(migrated_database, expire_on_commit=False)
    with factory.begin() as db:
        company = catalog.create_company(db, CompanyCreate(name="Legacy", slug="legacy"))
        source = catalog.create_source(
            db,
            SourceCreate(
                company_id=company.id, source_type="greenhouse", config={"board_token": "legacy"}
            ),
        )
        sid = source.id
    env = dict(os.environ, DATABASE_URL=migrated_database.url.render_as_string(hide_password=False))
    subprocess.run(["alembic", "downgrade", "0005"], env=env, check=True)
    try:
        assert "acquisition_method" not in {
            c["name"] for c in inspect(migrated_database).get_columns("job_sources")
        }
    finally:
        subprocess.run(["alembic", "upgrade", "head"], env=env, check=True)
    with factory() as db:
        stored = db.get(JobSource, sid)
        assert stored.acquisition_method == "http" and stored.config == {"board_token": "legacy"}
        assert stored.career_url is None


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE job_sources SET acquisition_method='api'",
        "UPDATE job_sources SET acquisition_method='browser', career_url=NULL",
    ],
)
def test_acquisition_database_constraints(migrated_database, sql):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    factory = sessionmaker(migrated_database, expire_on_commit=False)
    with factory.begin() as db:
        c = catalog.create_company(db, CompanyCreate(name="Acme", slug="constraint-company"))
        catalog.create_source(db, SourceCreate(company_id=c.id, source_type="greenhouse"))
    with factory.begin() as db:
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(text(sql))


def test_scheduler_only_fetches_user_selected_company_sources(migrated_database):
    from app.schemas.profile import ProfilePatch

    factory = sessionmaker(migrated_database, expire_on_commit=False)
    with factory.begin() as db:
        c = catalog.create_company(db, CompanyCreate(name="Selected", slug="selected"))
        s = catalog.create_source(
            db, SourceCreate(company_id=c.id, source_type="greenhouse", active=True)
        )
        cid, sid = c.id, s.id
    assert due_sources(factory, MonitoringConfig()) == []
    pid, owner = profile(factory, cid)
    assert due_sources(factory, MonitoringConfig()) == [sid]
    with factory() as db:
        from app.services import profiles

        profiles.update(db, owner, pid, ProfilePatch(active=False))
    assert due_sources(factory, MonitoringConfig()) == []
    assert asyncio.run(run_source(factory, sid, due_only=True)).status == "disabled"
