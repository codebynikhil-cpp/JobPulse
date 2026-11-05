from __future__ import annotations

import asyncio
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models.auth import User
from app.models.job import Job
from app.models.monitoring import JobMatch, JobMonitorState
from app.models.notification import Notification
from app.monitoring.runner import run_source
from app.monitoring.subscriptions import subscribe_company
from app.notifications.config import NotificationConfig
from app.notifications.metrics import get_notification_metrics
from app.notifications.outbox import (
    enqueue_matches,
    previous_relevant_users,
)
from app.notifications.provider import (
    DisabledEmailProvider,
    MockEmailProvider,
)
from app.notifications.worker import (
    NotificationWorker,
    claim_due_records,
)
from app.schemas.catalog import CompanyCreate, SourceCreate
from app.schemas.profile import ProfileCreate
from app.services import catalog, profiles
from app.sources.base import RawJob
from app.sources.fake import FakeSource


@pytest.fixture
def factory(migrated_database):
    return sessionmaker(migrated_database, expire_on_commit=False)


def setup_source_and_company(factory):
    with factory.begin() as db:
        company = catalog.create_company(
            db, CompanyCreate(name="Acme Corp", slug=uuid.uuid4().hex, enabled=True)
        )
        source = catalog.create_source(
            db,
            SourceCreate(
                company_id=company.id,
                source_type="greenhouse",
                active=True,
                config={"board_token": "acme"},
                poll_interval_sec=60,
            ),
        )
        return company.id, source.id


def create_user_profile(
    factory,
    company_id: uuid.UUID,
    *,
    email: str | None = None,
    name: str = "Backend Profile",
    role: str = "Software Engineer",
    skill: str = "Python",
    owner: uuid.UUID | None = None,
    active: bool = True,
):
    with factory.begin() as db:
        if owner is None:
            user = User(
                email=email or f"user-{uuid.uuid4().hex[:8]}@example.com",
                password_hash="test-hash",
            )
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
                roles=[{"name": role}],
                skills=[{"name": skill, "kind": "required"}],
            ),
        )
        pid = p.id

    with factory.begin() as db:
        subscribe_company(db, owner, pid, company_id)

    return pid, owner


def make_raw_job(identity: str = "job-1", **overrides):
    job = RawJob(
        external_id=identity,
        title="Software Engineer",
        description="We are hiring a Python Software Engineer with experience.",
        location="Bengaluru",
        url=f"https://example.com/apply/{identity}",
    )
    return replace(job, **overrides)


# ==============================================================================
# 1. OUTBOX TESTS
# ==============================================================================


def test_positive_match_creates_notification_and_non_match_creates_none(factory):
    cid, sid = setup_source_and_company(factory)
    pid, owner = create_user_profile(factory, cid, role="Software Engineer", skill="Python")

    # Matching job
    matching_raw = make_raw_job("job-match", title="Software Engineer", description="Python dev")
    # Non-matching job
    non_matching_raw = make_raw_job("job-nomatch", title="Chef", description="Culinary Arts")

    asyncio.run(run_source(factory, sid, adapter=FakeSource([[matching_raw, non_matching_raw]])))

    with factory() as db:
        matches = list(db.scalars(select(JobMatch).order_by(JobMatch.job_id)))
        assert len(matches) == 2
        matched_flags = {m.job_id: m.matched for m in matches}

        notifs = list(db.scalars(select(Notification)))
        # Exactly one notification for the matching job, zero for the non-matching job
        assert len(notifs) == 1
        notif = notifs[0]
        assert notif.user_id == owner
        assert matched_flags[notif.job_id] is True
        assert notif.kind == "new_job"
        assert notif.status == "pending"
        assert notif.attempts == 0
        assert notif.payload["company"] == "Acme Corp"
        assert len(notif.payload["profiles"]) == 1
        assert notif.payload["profiles"][0]["id"] == str(pid)


def test_transaction_rollback_creates_neither_partial_match_nor_notification(factory):
    cid, sid = setup_source_and_company(factory)
    pid, owner = create_user_profile(factory, cid, role="Software Engineer", skill="Python")

    # Manually run an evaluation transaction that simulates a rollback midway
    matching_raw = make_raw_job("job-1")
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[matching_raw]])))

    with factory() as db:
        job = db.scalar(select(Job).where(Job.external_job_id == "job-1"))
        assert job is not None
        assert db.get(JobMonitorState, job.id) is not None

    # Now verify atomic rollback semantics in enqueue_matches
    with pytest.raises(RuntimeError):
        with factory.begin() as db:
            j = db.get(Job, job.id)
            w = db.get(JobMonitorState, job.id)
            # Enqueue notification
            created = enqueue_matches(db, j, w, set(), NotificationConfig())
            assert created >= 0
            # Force transaction failure
            raise RuntimeError("Database transaction aborted unexpectedly")

    # Verify no partial or leaked state persisted
    with factory() as db:
        # If we query notifications created with uncommitted revision, none exists beyond the initial run
        notif_count = db.scalar(select(func.count()).select_from(Notification))
        assert notif_count == 1  # only from the initial run


def test_duplicate_match_evaluation_does_not_create_duplicate_notification(factory):
    cid, sid = setup_source_and_company(factory)
    create_user_profile(factory, cid, role="Software Engineer", skill="Python")

    raw_job = make_raw_job("job-dup")

    # First run: creates job, match, outbox notification
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[raw_job]])))

    with factory() as db:
        count_1 = db.scalar(select(func.count()).select_from(Notification))
        assert count_1 == 1

    # Second run with identical job: evaluation detects duplicate, creates no new notification
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[raw_job]])))

    with factory() as db:
        count_2 = db.scalar(select(func.count()).select_from(Notification))
        assert count_2 == 1


def test_same_job_matching_multiple_profiles_for_one_user_creates_one_notification(factory):
    cid, sid = setup_source_and_company(factory)

    # User has two matching profiles
    p1, owner = create_user_profile(
        factory, cid, name="Profile 1 Backend", role="Software Engineer", skill="Python"
    )
    p2, _ = create_user_profile(
        factory,
        cid,
        name="Profile 2 Fullstack",
        role="Software Engineer",
        skill="Python",
        owner=owner,
    )

    raw_job = make_raw_job("job-multi-prof")
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[raw_job]])))

    with factory() as db:
        # Both profiles have JobMatch records
        matches = list(db.scalars(select(JobMatch).where(JobMatch.matched.is_(True))))
        assert len(matches) == 2
        matched_pids = {m.profile_id for m in matches}
        assert matched_pids == {p1, p2}

        # Exactly ONE notification was created for this user
        notifs = list(db.scalars(select(Notification).where(Notification.user_id == owner)))
        assert len(notifs) == 1
        notif = notifs[0]
        assert notif.kind == "new_job"

        # The single notification aggregates both matching profiles with their scores and evidence
        payload_profiles = notif.payload["profiles"]
        assert len(payload_profiles) == 2
        payload_pids = {p["id"] for p in payload_profiles}
        assert payload_pids == {str(p1), str(p2)}


def test_same_job_matching_profiles_of_different_users_creates_one_notification_per_user(factory):
    cid, sid = setup_source_and_company(factory)

    p1, user_1 = create_user_profile(
        factory,
        cid,
        email="alice@example.com",
        name="Alice Dev",
        role="Software Engineer",
        skill="Python",
    )
    p2, user_2 = create_user_profile(
        factory,
        cid,
        email="bob@example.com",
        name="Bob Dev",
        role="Software Engineer",
        skill="Python",
    )

    raw_job = make_raw_job("job-multi-user")
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[raw_job]])))

    with factory() as db:
        notifs = list(db.scalars(select(Notification).order_by(Notification.user_id)))
        assert len(notifs) == 2

        users_notified = {n.user_id for n in notifs}
        assert users_notified == {user_1, user_2}

        for n in notifs:
            assert n.kind == "new_job"
            if n.user_id == user_1:
                assert n.payload["recipient"] == "alice@example.com"
                assert len(n.payload["profiles"]) == 1
                assert n.payload["profiles"][0]["id"] == str(p1)
            else:
                assert n.payload["recipient"] == "bob@example.com"
                assert len(n.payload["profiles"]) == 1
                assert n.payload["profiles"][0]["id"] == str(p2)


# ==============================================================================
# 2. CHANGED-JOB ALERT POLICY TESTS
# ==============================================================================


def test_changed_job_alert_policy_lifecycle(factory):
    """Verifies all states of the changed-job alert policy:
    - new job -> notification
    - unchanged job -> no notification
    - materially changed still-matching job -> notification according to policy
    - changed job that becomes relevant -> notification
    - changed job that stops matching -> no new notification
    """
    cid, sid = setup_source_and_company(factory)
    pid, owner = create_user_profile(factory, cid, role="Software Engineer", skill="Python")

    # 1. New matching job -> notification
    job_1 = make_raw_job("lifecycle-1", title="Software Engineer", description="Python developer")
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[job_1]])))

    with factory() as db:
        notifs = list(db.scalars(select(Notification).where(Notification.user_id == owner)))
        assert len(notifs) == 1
        assert notifs[0].kind == "new_job"
        assert notifs[0].revision == "initial"

    # 2. Unchanged job -> no new notification
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[job_1]])))
    with factory() as db:
        notifs = list(db.scalars(select(Notification).where(Notification.user_id == owner)))
        assert len(notifs) == 1

    # 3. Materially changed still-matching job -> notification according to policy ("material")
    job_1_material = replace(
        job_1,
        title="Senior Software Engineer",  # Still matches
        description="Senior Python backend engineer with distributed systems",
    )
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[job_1_material]])))

    with factory() as db:
        notifs = list(
            db.scalars(
                select(Notification)
                .where(Notification.user_id == owner)
                .order_by(Notification.created_at)
            )
        )
        assert len(notifs) == 2
        assert notifs[1].kind == "changed_job"
        assert notifs[1].revision != "initial"

    # 4. Changed job that stops matching -> no new notification
    job_1_no_match = replace(
        job_1_material,
        title="Head Chef",
        description="Cooking and restaurant management",
    )
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[job_1_no_match]])))

    with factory() as db:
        notifs = list(db.scalars(select(Notification).where(Notification.user_id == owner)))
        assert len(notifs) == 2  # Still 2, no notification for irrelevant change

    # 5. Changed job that becomes newly relevant -> notification
    job_2 = make_raw_job("lifecycle-2", title="Office Manager", description="Office duties")
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[job_2]])))

    with factory() as db:
        # Job 2 did not match initially
        job2_notifs = list(
            db.scalars(select(Notification).join(Job).where(Job.external_job_id == "lifecycle-2"))
        )
        assert len(job2_notifs) == 0

    # Job 2 changes to match
    job_2_relevant = replace(
        job_2,
        title="Software Engineer",
        description="Python development team",
    )
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[job_2_relevant]])))

    with factory() as db:
        job2_notifs = list(
            db.scalars(select(Notification).join(Job).where(Job.external_job_id == "lifecycle-2"))
        )
        assert len(job2_notifs) == 1
        assert job2_notifs[0].kind == "changed_job"


def test_changed_job_policy_newly_relevant_and_off(factory):
    cid, sid = setup_source_and_company(factory)
    pid, owner = create_user_profile(factory, cid, role="Software Engineer", skill="Python")

    # Run 1: new matching job
    raw_job = make_raw_job("policy-job", title="Software Engineer", description="Python")
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[raw_job]])))

    # Material change
    raw_changed = replace(raw_job, title="Lead Software Engineer", description="Python team lead")
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[raw_changed]])))

    # With changed_policy = "newly_relevant", already-relevant user does NOT get alerted on material change
    with factory() as db:
        job = db.scalar(select(Job).where(Job.external_job_id == "policy-job"))
        work = db.get(JobMonitorState, job.id)
        prev_users = previous_relevant_users(db, job.id)
        assert owner in prev_users

        cfg_newly = NotificationConfig(changed_policy="newly_relevant")
        created = enqueue_matches(db, job, work, prev_users, cfg_newly)
        assert created == 0

        # With changed_policy = "off", no changed alerts
        cfg_off = NotificationConfig(changed_policy="off")
        created_off = enqueue_matches(db, job, work, prev_users, cfg_off)
        assert created_off == 0


# ==============================================================================
# 3. RETRY & DELIVERY TESTS
# ==============================================================================


def test_transient_failure_schedules_bounded_retry(factory):
    cid, sid = setup_source_and_company(factory)
    create_user_profile(
        factory, cid, email="user-retry@example.com", role="Software Engineer", skill="Python"
    )

    raw_job = make_raw_job("job-retry-1")
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[raw_job]])))

    mock_provider = MockEmailProvider()
    mock_provider.fail_transiently_for("user-retry@example.com", count=2)

    config = NotificationConfig(
        max_attempts=3,
        retry_base_seconds=10,
        retry_cap_seconds=60,
    )

    worker = NotificationWorker(factory, provider=mock_provider, config=config)

    # First attempt: transient failure -> status becomes "failed", attempts=1
    summary1 = worker.process_batch()
    assert summary1.claimed == 1
    assert summary1.retried == 1
    assert summary1.sent == 0

    with factory() as db:
        notif = db.scalar(select(Notification))
        assert notif.status == "failed"
        assert notif.attempts == 1
        assert notif.claim_token is None
        assert notif.lease_until is None
        assert notif.available_at > datetime.now(UTC)
        assert notif.last_error is not None
        # Reset available_at to now for testing next retry attempt
        notif.available_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    # Second attempt: transient failure -> status becomes "failed", attempts=2
    summary2 = worker.process_batch()
    assert summary2.claimed == 1
    assert summary2.retried == 1

    with factory() as db:
        notif = db.scalar(select(Notification))
        assert notif.status == "failed"
        assert notif.attempts == 2
        notif.available_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    # Third attempt: mock transient failure ends, succeeds! -> status becomes "sent"
    summary3 = worker.process_batch()
    assert summary3.claimed == 1
    assert summary3.sent == 1

    with factory() as db:
        notif = db.scalar(select(Notification))
        assert notif.status == "sent"
        assert notif.attempts == 3
        assert notif.sent_at is not None
        assert notif.provider_id.startswith("mock-")
        assert notif.claim_token is None
        assert notif.lease_until is None


def test_repeated_transient_failure_exceeds_max_attempts(factory):
    cid, sid = setup_source_and_company(factory)
    create_user_profile(
        factory, cid, email="user-bound@example.com", role="Software Engineer", skill="Python"
    )

    raw_job = make_raw_job("job-bounded-fail")
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[raw_job]])))

    mock_provider = MockEmailProvider()
    mock_provider.fail_transiently_for("user-bound@example.com", count=10)

    config = NotificationConfig(max_attempts=2, retry_base_seconds=5)
    worker = NotificationWorker(factory, provider=mock_provider, config=config)

    # Attempt 1
    worker.process_batch()
    with factory() as db:
        notif = db.scalar(select(Notification))
        assert notif.status == "failed"
        assert notif.attempts == 1
        notif.available_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    # Attempt 2 -> hits max_attempts=2 -> transitions to permanently_failed
    summary = worker.process_batch()
    assert summary.permanently_failed == 1

    with factory() as db:
        notif = db.scalar(select(Notification))
        assert notif.status == "permanently_failed"
        assert notif.attempts == 2
        assert "Max attempts" in notif.last_error


def test_permanent_failure_transitions_immediately_without_retry_loop(factory):
    cid, sid = setup_source_and_company(factory)
    create_user_profile(
        factory, cid, email="rejected@example.com", role="Software Engineer", skill="Python"
    )

    raw_job = make_raw_job("job-perm-fail")
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[raw_job]])))

    mock_provider = MockEmailProvider()
    mock_provider.fail_permanently_for("rejected@example.com")

    worker = NotificationWorker(factory, provider=mock_provider, config=NotificationConfig())

    summary = worker.process_batch()
    assert summary.claimed == 1
    assert summary.permanently_failed == 1
    assert summary.retried == 0

    with factory() as db:
        notif = db.scalar(select(Notification))
        assert notif.status == "permanently_failed"
        assert notif.attempts == 1
        assert "Permanent rejection" in notif.last_error

    # Ensure running worker again does not pick up permanently_failed record
    summary2 = worker.process_batch()
    assert summary2.claimed == 0


# ==============================================================================
# 4. CONCURRENCY & LOCKING TESTS
# ==============================================================================


def test_concurrent_worker_claim_locking_semantics(factory):
    """Verifies that two workers attempting the same pending notification cannot both claim it.
    Database FOR UPDATE SKIP LOCKED guarantees mutually exclusive claims.
    """
    cid, sid = setup_source_and_company(factory)
    create_user_profile(factory, cid, role="Software Engineer", skill="Python")

    raw_job = make_raw_job("job-concurrency")
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[raw_job]])))

    config = NotificationConfig(batch_size=10, lease_seconds=120)

    # Worker 1 claims
    with factory() as db1:
        token1, claimed_1 = claim_due_records(db1, config)
        assert len(claimed_1) == 1

    # Worker 2 attempts to claim concurrently while Worker 1 holds the lease
    with factory() as db2:
        token2, claimed_2 = claim_due_records(db2, config)
        # Because Worker 1 claimed it (status='processing' and lease_until in future),
        # Worker 2 claims 0 records!
        assert len(claimed_2) == 0

    # Verify state in DB
    with factory() as db:
        notif = db.scalar(select(Notification))
        assert notif.status == "processing"
        assert notif.claim_token == token1


# ==============================================================================
# 5. END-TO-END NOTIFICATION TEST
# ==============================================================================


def test_end_to_end_monitoring_outbox_email_flow(factory):
    """End-to-end test mandated by Section 15:
    Run 1:
      new matching job -> matcher -> match state -> one outbox row per user -> email provider mock -> sent
    Run 2:
      identical source -> no new job -> no new notification
    Run 3:
      one materially changed matching job -> updated match -> one new changed-job notification according to policy
    For a user with two matching profiles:
      -> exactly one email notification
    """
    cid, sid = setup_source_and_company(factory)

    # User has TWO matching profiles
    p1, user = create_user_profile(
        factory,
        cid,
        email="candidate@example.com",
        name="Backend Profile",
        role="Software Engineer",
        skill="Python",
    )
    p2, _ = create_user_profile(
        factory,
        cid,
        email="candidate@example.com",
        name="Data Profile",
        role="Software Engineer",
        skill="Python",
        owner=user,
    )

    mock_provider = MockEmailProvider()
    worker = NotificationWorker(factory, provider=mock_provider)

    # -------------------------------------------------------------------------
    # RUN 1: New matching job
    # -------------------------------------------------------------------------
    job_v1 = make_raw_job(
        "e2e-job-1", title="Software Engineer", description="Python and databases"
    )
    res1 = asyncio.run(run_source(factory, sid, adapter=FakeSource([[job_v1]])))
    assert res1.matched_count == 2  # matched both profiles

    with factory() as db:
        notifs = list(db.scalars(select(Notification)))
        # Exactly ONE outbox row for the user despite 2 matching profiles
        assert len(notifs) == 1
        notif1 = notifs[0]
        assert notif1.user_id == user
        assert notif1.kind == "new_job"
        assert notif1.status == "pending"
        # Aggregated profiles
        p_ids = {p["id"] for p in notif1.payload["profiles"]}
        assert p_ids == {str(p1), str(p2)}

    # Worker delivers notification
    batch1 = worker.run_once()
    assert batch1.claimed == 1
    assert batch1.sent == 1
    assert len(mock_provider.sent_messages) == 1
    sent_msg = mock_provider.sent_messages[0]
    assert sent_msg.recipient == "candidate@example.com"
    assert "Software Engineer" in sent_msg.subject
    assert "Backend Profile" in sent_msg.body
    assert "Data Profile" in sent_msg.body

    with factory() as db:
        notif1 = db.scalar(select(Notification))
        assert notif1.status == "sent"
        assert notif1.sent_at is not None

    # -------------------------------------------------------------------------
    # RUN 2: Identical source
    # -------------------------------------------------------------------------
    mock_provider.reset()
    res2 = asyncio.run(run_source(factory, sid, adapter=FakeSource([[job_v1]])))
    assert res2.unchanged_count == 1

    with factory() as db:
        notifs = list(db.scalars(select(Notification)))
        assert len(notifs) == 1  # No new notification created

    batch2 = worker.run_once()
    assert batch2.claimed == 0
    assert len(mock_provider.sent_messages) == 0

    # -------------------------------------------------------------------------
    # RUN 3: One materially changed matching job
    # -------------------------------------------------------------------------
    mock_provider.reset()
    job_v2 = replace(
        job_v1,
        title="Senior Software Engineer",
        description="Senior Python developer with distributed backend skills",
    )
    res3 = asyncio.run(run_source(factory, sid, adapter=FakeSource([[job_v2]])))
    assert res3.updated_count == 1

    with factory() as db:
        notifs = list(db.scalars(select(Notification).order_by(Notification.created_at)))
        # Exactly ONE new notification for the material change
        assert len(notifs) == 2
        notif2 = notifs[1]
        assert notif2.kind == "changed_job"
        assert notif2.status == "pending"

    # Worker delivers changed-job notification
    batch3 = worker.run_once()
    assert batch3.claimed == 1
    assert batch3.sent == 1
    assert len(mock_provider.sent_messages) == 1
    changed_msg = mock_provider.sent_messages[0]
    assert "Senior Software Engineer" in changed_msg.subject
    assert "Updated Job Match" in changed_msg.subject

    # Overall: for the user with 2 matching profiles, exactly 1 notification per distinct event
    with factory() as db:
        all_sent = list(db.scalars(select(Notification).where(Notification.status == "sent")))
        assert len(all_sent) == 2  # 1 for initial creation, 1 for material change


# ==============================================================================
# 6. OBSERVABILITY & API ENDPOINTS
# ==============================================================================


def test_notification_observability_metrics(factory):
    cid, sid = setup_source_and_company(factory)
    create_user_profile(factory, cid, role="Software Engineer", skill="Python")

    raw_job = make_raw_job("job-metrics")
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[raw_job]])))

    with factory() as db:
        metrics_initial = get_notification_metrics(db)
        assert metrics_initial.total_count == 1
        assert metrics_initial.pending_count == 1
        assert metrics_initial.sent_count == 0
        assert metrics_initial.failed_count == 0

    worker = NotificationWorker(factory, provider=MockEmailProvider())
    worker.run_once()

    with factory() as db:
        metrics_after = get_notification_metrics(db)
        assert metrics_after.total_count == 1
        assert metrics_after.pending_count == 0
        assert metrics_after.sent_count == 1
        assert metrics_after.avg_attempts == 1.0
        assert metrics_after.avg_latency_seconds is not None
        assert metrics_after.avg_latency_seconds >= 0.0


def test_notifications_api_endpoints(client, factory):
    cid, sid = setup_source_and_company(factory)

    # Signup user via client
    email = f"api-user-{uuid.uuid4().hex[:6]}@example.com"
    pwd = "a strong password 123"
    resp = client.post("/api/auth/signup", json={"email": email, "password": pwd})
    assert resp.status_code == 201

    # User creates profile and subscribes
    prof = client.post(
        "/api/profiles",
        json={
            "name": "API Profile",
            "active": True,
            "roles": [{"name": "Software Engineer"}],
            "skills": [{"name": "Python", "kind": "required"}],
        },
    ).json()

    with factory.begin() as db:
        user = db.scalar(select(User).where(User.email == email))
        user_id = user.id
        subscribe_company(db, user_id, uuid.UUID(prof["id"]), cid)

    # Monitoring generates notification
    raw_job = make_raw_job("job-api-1")
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[raw_job]])))

    # List notifications via API
    list_resp = client.get("/api/notifications")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["kind"] == "new_job"
    assert items[0]["status"] == "pending"
    notif_id = items[0]["id"]

    # Filter by status
    sent_filter = client.get("/api/notifications?status=sent")
    assert sent_filter.status_code == 200
    assert len(sent_filter.json()) == 0

    pending_filter = client.get("/api/notifications?status=pending")
    assert pending_filter.status_code == 200
    assert len(pending_filter.json()) == 1

    # Get single notification
    get_resp = client.get(f"/api/notifications/{notif_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == notif_id

    # Observability metrics via API
    metrics_resp = client.get("/api/notifications/metrics")
    assert metrics_resp.status_code == 200
    metrics_data = metrics_resp.json()
    assert metrics_data["total_count"] >= 1
    assert metrics_data["pending_count"] >= 1


def test_disabled_delivery_is_cancelled_not_sent_after_real_worker_claim(factory):
    cid, sid = setup_source_and_company(factory)
    create_user_profile(factory, cid)
    asyncio.run(run_source(factory, sid, adapter=FakeSource([[make_raw_job()]])))
    worker = NotificationWorker(factory, provider=DisabledEmailProvider())
    summary = worker.run_once()
    assert summary.claimed == summary.cancelled == 1
    assert summary.sent == summary.retried == summary.permanently_failed == 0
    with factory() as db:
        record = db.scalar(select(Notification))
        assert record.status == "cancelled"
        assert record.sent_at is None
        assert record.read_at is None
        assert record.claim_token is None and record.lease_until is None
        assert record.attempts == 1
        assert get_notification_metrics(db).sent_count == 0
    assert worker.run_once().claimed == 0
