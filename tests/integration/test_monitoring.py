import asyncio
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.matching.matcher import DeterministicMatcher
from app.models.auth import User
from app.models.catalog import JobSource
from app.models.job import Job
from app.models.monitoring import JobMatch, JobMonitorState, MonitorRun, ProfileCompany
from app.monitoring import runner
from app.monitoring.config import MonitoringConfig
from app.monitoring.evaluation import list_current_matches
from app.monitoring.runner import run_source
from app.monitoring.scheduler import due_sources, run_due, worker
from app.monitoring.subscriptions import subscribe_company
from app.schemas.catalog import CompanyCreate, SourceCreate
from app.schemas.profile import ProfileCreate
from app.services import catalog, profiles
from app.services.source_lock import source_lock
from app.sources.base import RawJob, SourceError
from app.sources.fake import FakeSource


@pytest.fixture
def factory(migrated_database):
    return sessionmaker(migrated_database, expire_on_commit=False)


def source(factory, *, kind="greenhouse", active=True, enabled=True):
    with factory.begin() as db:
        company = catalog.create_company(
            db, CompanyCreate(name="Acme", slug=uuid.uuid4().hex, enabled=enabled)
        )
        item = catalog.create_source(
            db,
            SourceCreate(
                company_id=company.id,
                source_type=kind,
                active=active,
                config={"board_token": "acme"},
                poll_interval_sec=60,
            ),
        )
        return item.id, company.id


def profile(factory, company_id=None, *, active=True, name="Engineer", owner=None):
    with factory.begin() as db:
        if owner is None:
            user = User(email=uuid.uuid4().hex + "@example.com", password_hash="test-only")
            db.add(user)
            db.flush()
            owner = user.id
    with factory() as db:
        p = profiles.create(
            db,
            owner,
            ProfileCreate(
                name=name,
                active=active,
                roles=[{"name": "Software Engineer"}],
                skills=[{"name": "Python", "kind": "required"}],
            ),
        )
        pid = p.id
    if company_id:
        with factory.begin() as db:
            subscribe_company(db, owner, pid, company_id)
    return pid, owner


def raw(identity="1", **changes):
    item = RawJob(
        identity, "Software Engineer", "Python", "Bengaluru", "https://example.com/jobs/" + identity
    )
    return replace(item, **changes)


def run(factory, source_id, records=None, **kwargs):
    return asyncio.run(
        run_source(factory, source_id, adapter=FakeSource([records or []]), **kwargs)
    )


def test_new_repeat_update_acceptance(factory):
    sid, company = source(factory)
    pid, owner = profile(factory, company)
    records = [raw(str(i)) for i in range(5)]
    first = run(factory, sid, records)
    assert (first.status, first.created_count, first.evaluated_count, first.matched_count) == (
        "success",
        5,
        5,
        5,
    )
    with factory() as db:
        originals = {m.job_id: (m.created_at, m.updated_at) for m in db.scalars(select(JobMatch))}
        assert len(list_current_matches(db, owner)) == 5
        assert list_current_matches(db, uuid.uuid4()) == []
    repeat = run(factory, sid, records)
    assert (
        repeat.created_count,
        repeat.unchanged_count,
        repeat.evaluated_count,
        repeat.matched_count,
    ) == (0, 5, 0, 0)
    with factory() as db:
        assert {
            m.job_id: (m.created_at, m.updated_at) for m in db.scalars(select(JobMatch))
        } == originals
    records[0] = replace(records[0], description="Java")
    changed = run(factory, sid, records)
    assert (changed.updated_count, changed.evaluated_count, changed.matched_count) == (1, 1, 0)
    with factory() as db:
        matches = list(db.scalars(select(JobMatch)))
        assert len(matches) == 5
        rejected = next(m for m in matches if not m.matched)
        assert rejected.score == 0 and rejected.evidence["hard_filters"]
        assert rejected.evidence["parsed_experience"] is None
        assert len(list_current_matches(db, owner)) == 4
        assert db.scalar(select(func.count()).select_from(MonitorRun)) == 3


def test_only_active_subscribed_profiles_and_owner_scope(factory):
    sid, company = source(factory)
    _, other_company = source(factory)
    correct, owner = profile(factory, company)
    profile(factory, company, active=False)
    profile(factory, other_company)
    profile(factory)
    second, second_owner = profile(factory, company)
    result = run(factory, sid, [raw()])
    assert result.evaluated_count == 2
    with factory() as db:
        assert {m.profile_id for m in db.scalars(select(JobMatch))} == {correct, second}
        assert [m.profile_id for m in list_current_matches(db, owner)] == [correct]
        assert [m.profile_id for m in list_current_matches(db, second_owner)] == [second]


def test_subscription_owner_check_and_idempotency(factory):
    _, company = source(factory)
    pid, owner = profile(factory)
    with factory.begin() as db:
        with pytest.raises(LookupError):
            subscribe_company(db, uuid.uuid4(), pid, company)
        subscribe_company(db, owner, pid, company)
        subscribe_company(db, owner, pid, company)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ProfileCompany)) == 1


@pytest.mark.parametrize("kind", ["lever", "ashby", "workday", "api", "custom"])
def test_unsupported_classification_not_runnable(factory, kind):
    sid, _ = source(factory, kind=kind)
    assert sid not in due_sources(factory, MonitoringConfig())
    result = run(factory, sid, [raw()])
    assert result.status == "unsupported" and result.fetched_count == 0
    with factory() as db:
        assert db.get(JobSource, sid).health_status == "unsupported"
        assert db.get(JobSource, sid).last_checked_at is None


@pytest.mark.parametrize("active,enabled", [(False, True), (True, False)])
def test_disabled_source_or_company(factory, active, enabled):
    sid, _ = source(factory, active=active, enabled=enabled)
    assert not due_sources(factory, MonitoringConfig())
    assert run(factory, sid, [raw()]).status == "disabled"


def test_due_poll_boundary_and_manual_override(factory):
    sid, company = source(factory)
    profile(factory, company)
    now = datetime.now(UTC)
    with factory.begin() as db:
        db.get(JobSource, sid).last_checked_at = now
    config = MonitoringConfig()
    assert due_sources(factory, config, now=now + timedelta(seconds=59)) == []
    assert due_sources(factory, config, now=now + timedelta(seconds=60)) == [sid]
    assert run(factory, sid, [raw()], due_only=True).status == "not_due"
    assert run(factory, sid, [raw()]).status == "success"


def test_clean_missing_twice_closes_and_reappearance_reopens(factory):
    sid, company = source(factory)
    profile(factory, company)
    records = [raw(str(i)) for i in range(4)]
    run(factory, sid, records)
    assert run(factory, sid, records[:-1]).closed_count == 0
    assert run(factory, sid, records[:-1]).closed_count == 1
    with factory() as db:
        item = db.scalar(select(Job).where(Job.external_job_id == "3"))
        identity = item.id
        assert item.status == "closed" and item.closed_at >= item.last_seen_at
    result = run(factory, sid, records)
    assert result.updated_count == 1
    with factory() as db:
        item = db.get(Job, identity)
        assert item.status == "open" and item.closed_at is None
        assert db.get(JobMonitorState, identity).missing_count == 0


@pytest.mark.parametrize("mode", ["fetch", "malformed", "duplicates"])
def test_failure_never_closes_or_advances_missing(factory, mode):
    sid, _ = source(factory)
    records = [raw(str(i)) for i in range(4)]
    run(factory, sid, records)
    run(factory, sid, records[:-1])
    with factory() as db:
        previous_success = db.get(JobSource, sid).last_success_at
        missing_id = db.scalar(select(Job.id).where(Job.external_job_id == "3"))
    adapter = (
        FakeSource([], error=SourceError("controlled"))
        if mode == "fetch"
        else FakeSource([[raw(url="bad")] if mode == "malformed" else [raw(), raw()]])
    )
    result = asyncio.run(run_source(factory, sid, adapter=adapter))
    assert result.status == "failed" and result.failed_count > 0
    with factory() as db:
        assert all(j.status == "open" for j in db.scalars(select(Job)))
        assert db.get(JobMonitorState, missing_id).missing_count == 1
        item = db.get(JobSource, sid)
        assert item.last_success_at == previous_success
        assert item.last_error_at and item.last_checked_at


@pytest.mark.parametrize("remaining", [0, 1])
def test_zero_and_large_drop_anomaly_no_closure(factory, remaining):
    sid, _ = source(factory)
    records = [raw(str(i)) for i in range(5)]
    run(factory, sid, records)
    for _ in range(2):
        result = run(factory, sid, records[:remaining])
        assert result.status == "anomaly" and result.closed_count == 0
    with factory() as db:
        assert all(j.status == "open" for j in db.scalars(select(Job)))
        assert all(s.missing_count == 0 for s in db.scalars(select(JobMonitorState)))
        assert db.get(JobSource, sid).health_status == "degraded"


def test_empty_first_board_is_success(factory):
    sid, _ = source(factory)
    assert run(factory, sid).status == "success"


def test_failure_escalation_pause_and_recovery(factory):
    sid, _ = source(factory)
    failure = FakeSource([], error=SourceError("controlled"))
    for expected in ("degraded", "degraded", "failing", "failing", "failing"):
        result = asyncio.run(run_source(factory, sid, adapter=failure))
        assert result.status == "failed"
        with factory() as db:
            assert db.get(JobSource, sid).health_status == expected
    assert run(factory, sid, [raw()]).status == "disabled"
    with factory.begin() as db:
        db.get(JobSource, sid).active = True
    assert run(factory, sid, [raw()]).status == "success"
    with factory() as db:
        item = db.get(JobSource, sid)
        assert item.consecutive_failures == 0 and item.last_error_at is not None


def test_timeout_isolated_and_health_recorded(factory):
    sid, _ = source(factory)

    class Hanging:
        async def fetch_jobs(self):
            await asyncio.sleep(1)

    result = asyncio.run(
        run_source(
            factory, sid, adapter=Hanging(), config=MonitoringConfig(source_timeout_seconds=0.01)
        )
    )
    assert result.status == "failed" and result.failed_count == 1
    assert result.error["error_type"] == "TimeoutError"
    with factory() as db:
        assert db.get(JobSource, sid).last_error_at


def test_one_source_failure_does_not_stop_cycle(factory):
    bad, bad_company = source(factory)
    profile(factory, bad_company)
    good, company = source(factory)
    profile(factory, company)
    result = asyncio.run(
        run_due(
            factory,
            adapter_factory=lambda sid: (
                FakeSource([], error=SourceError("controlled"))
                if sid == bad
                else FakeSource([[raw()]])
            ),
        )
    )
    assert {r.source_id: r.status for r in result} == {bad: "failed", good: "success"}
    assert next(r for r in result if r.source_id == good).matched_count == 1


def test_matcher_profile_failure_isolated_and_retry_skips_success(factory):
    sid, company = source(factory)
    profile(factory, company)
    profile(factory, company)

    class Sometimes:
        calls = 0

        def match(self, job, profile):
            self.calls += 1
            if self.calls == 1:
                raise ValueError("private content must not be logged or persisted")
            return DeterministicMatcher().match(job, profile)

    result = run(factory, sid, [raw()], matcher=Sometimes())
    assert result.status == "partial" and result.evaluation_failed_count == 1
    assert result.evaluated_count == 1 and result.matched_count == 1
    with factory() as db:
        error = db.scalar(select(JobMatch).where(JobMatch.status == "error"))
        assert error.matched is None and error.score is None
        assert "private" not in str(error.evidence)
        assert db.scalar(select(JobMonitorState)).pending
    recovered = run(factory, sid, [raw()])
    assert recovered.evaluated_count == 1 and recovered.matched_count == 1
    with factory() as db:
        assert len(list(db.scalars(select(JobMatch)))) == 2
        assert not db.scalar(select(JobMonitorState)).pending


def test_durable_work_survives_failure_after_ingestion(factory, monkeypatch):
    sid, company = source(factory)
    profile(factory, company)
    original = runner.evaluate_pending

    def fail(*args):
        raise RuntimeError("controlled worker error")

    monkeypatch.setattr(runner, "evaluate_pending", fail)
    first = run(factory, sid, [raw()])
    assert first.status == "failed" and first.created_count == 1
    with factory() as db:
        assert db.scalar(select(JobMonitorState)).pending
        assert db.scalar(select(func.count()).select_from(JobMatch)) == 0
    monkeypatch.setattr(runner, "evaluate_pending", original)
    second = run(factory, sid, [raw()])
    assert second.unchanged_count == 1 and second.evaluated_count == 1


def test_source_lock_prevents_overlap_and_releases(factory):
    sid, _ = source(factory)
    with source_lock(factory, sid) as acquired:
        assert acquired
        assert run(factory, sid, [raw()]).status == "busy"
    assert run(factory, sid, [raw()]).status == "success"


def test_abandoned_run_is_recorded_on_restart(factory):
    sid, _ = source(factory)
    with factory.begin() as db:
        previous = MonitorRun(
            source_id=sid, started_at=datetime.now(UTC), status="running", result={}
        )
        db.add(previous)
        db.flush()
        rid = previous.id
    run(factory, sid, [raw()])
    with factory() as db:
        assert db.get(MonitorRun, rid).status == "abandoned"


def test_small_batches_cover_all_profiles_and_jobs(factory):
    sid, company = source(factory)
    for _ in range(5):
        profile(factory, company)
    result = run(
        factory,
        sid,
        [raw(str(i)) for i in range(3)],
        config=MonitoringConfig(profile_batch_size=2, job_batch_size=1),
    )
    assert result.evaluated_count == result.matched_count == 15


def test_worker_can_stop_without_cycle(factory):
    async def scenario():
        stop = asyncio.Event()
        stop.set()
        await worker(factory, MonitoringConfig(), stop=stop)

    asyncio.run(scenario())


def test_real_overlapping_async_runs_fetch_once(factory):
    sid, _ = source(factory)

    class Blocking:
        calls = 0
        entered = None
        release = None

        async def fetch_jobs(self):
            self.calls += 1
            self.entered.set()
            await self.release.wait()
            return [raw()]

    async def scenario():
        adapter = Blocking()
        adapter.entered, adapter.release = asyncio.Event(), asyncio.Event()
        first = asyncio.create_task(run_source(factory, sid, adapter=adapter))
        await adapter.entered.wait()
        second = await run_source(factory, sid, adapter=adapter)
        assert second.status == "busy" and adapter.calls == 1
        adapter.release.set()
        assert (await first).status == "success"

    asyncio.run(scenario())


def test_legacy_ingestion_shares_monitor_lock(factory):
    from app.services.ingestion import IngestionError, ingest_source

    sid, _ = source(factory)
    with source_lock(factory, sid) as acquired:
        assert acquired
        with pytest.raises(IngestionError, match="already active"):
            asyncio.run(ingest_source(factory, sid, adapter=FakeSource([[raw()]])))


def test_ingestion_hook_failure_rolls_back_jobs_and_recovery_work(factory, monkeypatch):
    sid, _ = source(factory)
    original = runner.record_observation

    def fail(*args):
        original(*args)
        raise RuntimeError("controlled callback failure")

    monkeypatch.setattr(runner, "record_observation", fail)
    result = run(factory, sid, [raw()])
    assert result.status == "failed" and result.created_count == 0
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 0
        assert db.scalar(select(func.count()).select_from(JobMonitorState)) == 0


def test_cancelled_run_releases_lock_and_next_run_recovers(factory):
    sid, _ = source(factory)

    class Hanging:
        entered = None

        async def fetch_jobs(self):
            self.entered.set()
            await asyncio.Event().wait()

    async def scenario():
        adapter = Hanging()
        adapter.entered = asyncio.Event()
        task = asyncio.create_task(run_source(factory, sid, adapter=adapter))
        await adapter.entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (await run_source(factory, sid, adapter=FakeSource([[raw()]]))).status == "success"

    asyncio.run(scenario())
    with factory() as db:
        assert {r.status for r in db.scalars(select(MonitorRun))} == {"abandoned", "success"}


def test_current_matches_hide_stale_profile_state(factory):
    from app.schemas.profile import ProfilePatch

    sid, company = source(factory)
    pid, owner = profile(factory, company)
    run(factory, sid, [raw()])
    with factory() as db:
        profiles.update(db, owner, pid, ProfilePatch(skills=[{"name": "Rust", "kind": "required"}]))
    with factory() as db:
        assert list_current_matches(db, owner) == []


def test_subscription_and_match_delete_cascade(factory):
    sid, company = source(factory)
    pid, owner = profile(factory, company)
    run(factory, sid, [raw()])
    with factory() as db:
        profiles.delete(db, owner, pid)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(JobMatch)) == 0
        assert db.scalar(select(func.count()).select_from(ProfileCompany)) == 0
        assert db.scalar(select(func.count()).select_from(Job)) == 1


def test_monitoring_migration_round_trip_preserves_baseline(factory, migrated_database):
    import os
    import subprocess

    from sqlalchemy import inspect

    sid, company = source(factory)
    profile(factory, company)
    run(factory, sid, [raw()])
    env = dict(os.environ, DATABASE_URL=migrated_database.url.render_as_string(hide_password=False))
    subprocess.run(["alembic", "downgrade", "0004"], env=env, check=True)
    try:
        assert "job_matches" not in inspect(migrated_database).get_table_names()
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(Job)) == 1
            assert db.scalar(select(JobSource.id).where(JobSource.id == sid)) == sid
    finally:
        subprocess.run(["alembic", "upgrade", "head"], env=env, check=True)


def test_source_batch_limit_and_stop_after_cycle(factory, monkeypatch):
    from app.monitoring import scheduler

    for _ in range(3):
        _, company = source(factory)
        profile(factory, company)
    assert len(due_sources(factory, MonitoringConfig(source_batch_size=2))) == 2

    async def scenario():
        stop = asyncio.Event()
        calls = []

        async def cycle(*args, **kwargs):
            calls.append(1)
            stop.set()
            return []

        monkeypatch.setattr(scheduler, "run_due", cycle)
        await worker(factory, MonitoringConfig(), stop=stop)
        assert calls == [1]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"profile_batch_size": 0},
        {"source_timeout_seconds": 0},
        {"anomaly_drop_fraction": 0},
        {"anomaly_drop_fraction": 1.1},
        {"pause_after_failures": 0},
    ],
)
def test_invalid_monitor_config(kwargs):
    with pytest.raises(ValueError):
        MonitoringConfig(**kwargs)


def test_structured_run_result_and_log_context(factory):
    import json
    import logging

    from app.monitor import StructuredFormatter

    sid, company = source(factory)
    profile(factory, company)
    result = run(factory, sid, [raw()])
    value = result.to_dict()
    assert value["fetched_count"] == value["ingestion"]["fetched_count"] == 1
    assert value["matched_count"] == 1 and value["failed_count"] == 0
    assert result.completed_at >= result.started_at and result.duration_seconds >= 0
    with factory() as db:
        stored = db.get(MonitorRun, result.run_id)
        assert stored.result == value and stored.status == "success"
    record = logging.LogRecord("test", logging.ERROR, "", 0, "Source failed", (), None)
    record.source_id, record.error_type = str(sid), "SourceError"
    logged = json.loads(StructuredFormatter().format(record))
    assert logged["source_id"] == str(sid) and logged["error_type"] == "SourceError"
