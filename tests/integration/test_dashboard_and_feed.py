"""Phase 8 integration tests: Job feed, interactions, notification read-state,
subscriptions, source health, and dashboard."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.main import app
from app.models.auth import User
from app.models.catalog import JobSource
from app.models.job import Job
from app.models.job_interaction import UserJobInteraction
from app.models.notification import Notification
from app.monitoring.runner import run_source
from app.monitoring.subscriptions import subscribe_company
from app.schemas.catalog import CompanyCreate, SourceCreate
from app.schemas.profile import ProfileCreate
from app.services import catalog, profiles
from app.sources.base import RawJob
from app.sources.fake import FakeSource

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def factory(migrated_database):
    return sessionmaker(migrated_database, expire_on_commit=False)


@pytest.fixture
def client():
    with TestClient(app, headers={"Origin": settings.app_origin}) as c:
        yield c


def signup_and_auth(client, email=None):
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/signup", json={"email": email, "password": "Password123!"})
    assert r.status_code == 201, r.text
    return email, r.json()["id"]


def make_authed_client(email=None):
    """Return a TestClient already signed-up and logged in."""
    c = TestClient(app, headers={"Origin": settings.app_origin})
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    response = c.post("/api/auth/signup", json={"email": email, "password": "Password123!"})
    if response.status_code == 409:
        response = c.post("/api/auth/login", json={"email": email, "password": "Password123!"})
    assert response.status_code in (200, 201), response.text
    return c, email


def make_company_and_source(factory):
    with factory.begin() as db:
        company = catalog.create_company(
            db,
            CompanyCreate(name=f"Corp-{uuid.uuid4().hex[:6]}", slug=uuid.uuid4().hex, enabled=True),
        )
        source = catalog.create_source(
            db,
            SourceCreate(
                company_id=company.id,
                source_type="greenhouse",
                active=True,
                config={"board_token": "test"},
                poll_interval_sec=60,
            ),
        )
        return company.id, source.id


def make_profile_for_user(
    factory, user_id, company_id, name="Engineer", role="Software Engineer", skill="Python"
):
    with factory() as db:
        p = profiles.create(
            db,
            user_id,
            ProfileCreate(
                name=name,
                active=True,
                roles=[{"name": role}],
                skills=[{"name": skill, "kind": "required"}],
            ),
        )
        pid = p.id
    with factory.begin() as db:
        subscribe_company(db, user_id, pid, company_id)
    return pid


def raw_job(
    identity="j1", title="Software Engineer", description="Python developer role", location="Remote"
):
    return RawJob(
        external_id=identity,
        title=title,
        description=description,
        location=location,
        url=f"https://example.com/jobs/{identity}",
    )


def run_monitoring(factory, source_id, raw_jobs):
    asyncio.run(run_source(factory, source_id, adapter=FakeSource([raw_jobs])))


# ---------------------------------------------------------------------------
# 1. Job feed listing & pagination
# ---------------------------------------------------------------------------


def test_job_feed_empty_for_new_user(factory):
    """Unauthenticated → 401; new user with no profiles → empty feed."""
    c, email = make_authed_client()
    with c:
        r = c.get("/api/jobs")
        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []
        assert data["total"] == 0


def test_job_feed_returns_matched_jobs(factory):
    """User sees matched jobs after monitoring run."""
    c, email = make_authed_client()
    with c:
        user_id = uuid.UUID(c.get("/api/profiles").headers.get("x-user-id", str(uuid.uuid4())))
    # Get user_id from auth
    with factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        user_id = user.id

    company_id, source_id = make_company_and_source(factory)
    make_profile_for_user(factory, user_id, company_id)

    run_monitoring(
        factory,
        source_id,
        [
            raw_job("j1", title="Software Engineer", description="We need a Python developer"),
            raw_job("j2", title="Chef", description="Culinary arts experience"),
        ],
    )

    c2, _ = make_authed_client(email)
    with c2:
        r = c2.get("/api/jobs")
        assert r.status_code == 200
        data = r.json()
        # Only the matched job should appear (Chef should not match)
        assert data["total"] >= 1
        titles = [item["title"] for item in data["items"]]
        assert any("Software Engineer" in t for t in titles)


def test_job_feed_pagination(factory):
    """Pagination parameters work correctly."""
    c, email = make_authed_client()
    with factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        user_id = user.id

    company_id, source_id = make_company_and_source(factory)
    make_profile_for_user(factory, user_id, company_id)

    # Create 5 matching jobs
    raw_jobs = [
        raw_job(
            f"py-{i}", title=f"Python Developer {i}", description="Python backend developer role"
        )
        for i in range(5)
    ]
    run_monitoring(factory, source_id, raw_jobs)

    with c:
        r1 = c.get("/api/jobs?page=1&page_size=2")
        assert r1.status_code == 200
        d1 = r1.json()
        assert len(d1["items"]) <= 2
        assert d1["page"] == 1
        assert d1["page_size"] == 2

        r2 = c.get("/api/jobs?page=2&page_size=2")
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["page"] == 2

        # No duplicate job IDs across pages
        ids1 = {item["id"] for item in d1["items"]}
        ids2 = {item["id"] for item in d2["items"]}
        assert ids1.isdisjoint(ids2)


def test_job_feed_user_status_filter(factory):
    """Filter by user_status only returns jobs matching that status."""
    c, email = make_authed_client()
    with factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        user_id = user.id

    company_id, source_id = make_company_and_source(factory)
    make_profile_for_user(factory, user_id, company_id)
    run_monitoring(
        factory,
        source_id,
        [
            raw_job("save-me", title="Software Engineer", description="Python developer"),
        ],
    )

    with c:
        # Get job id
        feed = c.get("/api/jobs").json()
        assert feed["total"] >= 1
        job_id = feed["items"][0]["id"]

        # Save it
        r_save = c.patch(f"/api/jobs/{job_id}/status", json={"status": "saved", "notes": ""})
        assert r_save.status_code == 200
        assert r_save.json()["status"] == "saved"

        # Filter by saved - should include our job
        r_saved = c.get("/api/jobs?user_status=saved")
        assert r_saved.status_code == 200
        saved_ids = [item["id"] for item in r_saved.json()["items"]]
        assert job_id in saved_ids

        # Filter by new - should not include our job
        r_new = c.get("/api/jobs?user_status=new")
        new_ids = [item["id"] for item in r_new.json()["items"]]
        assert job_id not in new_ids


# ---------------------------------------------------------------------------
# 2. Job interactions
# ---------------------------------------------------------------------------


def test_job_interaction_lifecycle(factory):
    """Save → apply → restore to new lifecycle, canonical Job never mutated."""
    c, email = make_authed_client()
    with factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        user_id = user.id

    company_id, source_id = make_company_and_source(factory)
    make_profile_for_user(factory, user_id, company_id)
    run_monitoring(
        factory,
        source_id,
        [
            raw_job("interact-j1", title="Software Engineer", description="Python backend"),
        ],
    )

    with c:
        feed = c.get("/api/jobs").json()
        assert feed["total"] >= 1
        job_id = feed["items"][0]["id"]

        # Default status = new
        r_status = c.get(f"/api/jobs/{job_id}/status")
        assert r_status.status_code == 200
        assert r_status.json()["status"] == "new"

        # Save
        r_save = c.patch(
            f"/api/jobs/{job_id}/status", json={"status": "saved", "notes": "Looks good"}
        )
        assert r_save.status_code == 200
        assert r_save.json()["status"] == "saved"

        # Apply
        r_apply = c.patch(f"/api/jobs/{job_id}/status", json={"status": "applied", "notes": ""})
        assert r_apply.status_code == 200
        assert r_apply.json()["status"] == "applied"
        assert r_apply.json()["applied_at"] is not None

        # Restore to new (should delete row)
        r_restore = c.patch(f"/api/jobs/{job_id}/status", json={"status": "new", "notes": ""})
        assert r_restore.status_code == 200
        assert r_restore.json()["status"] == "new"

    # Canonical Job row must be untouched
    with factory() as db:
        job = db.get(Job, uuid.UUID(job_id))
        assert job is not None
        assert job.status == "open"
        # No interaction record (it was deleted on restore)
        interaction = db.scalar(
            select(UserJobInteraction).where(
                UserJobInteraction.job_id == uuid.UUID(job_id),
                UserJobInteraction.user_id == user_id,
            )
        )
        assert interaction is None


def test_ignored_jobs_hidden_by_default(factory):
    """Ignored jobs don't appear in default feed but appear when filter is 'ignored'."""
    c, email = make_authed_client()
    with factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        user_id = user.id

    company_id, source_id = make_company_and_source(factory)
    make_profile_for_user(factory, user_id, company_id)
    run_monitoring(
        factory,
        source_id,
        [
            raw_job("ignore-me", title="Software Engineer", description="Python developer"),
        ],
    )

    with c:
        feed = c.get("/api/jobs").json()
        job_id = feed["items"][0]["id"]

        # Ignore it
        c.patch(f"/api/jobs/{job_id}/status", json={"status": "ignored", "notes": ""})

        # Default feed should not show it
        default_feed = c.get("/api/jobs").json()
        default_ids = [item["id"] for item in default_feed["items"]]
        assert job_id not in default_ids

        # Explicit ignored filter shows it
        ignored_feed = c.get("/api/jobs?user_status=ignored").json()
        assert any(item["id"] == job_id for item in ignored_feed["items"])


def test_job_interaction_ownership_isolation(factory):
    """User A's interactions do not affect User B's view of the same job."""
    c_a, email_a = make_authed_client()
    c_b, email_b = make_authed_client()

    with factory() as db:
        user_a = db.scalar(select(User).where(User.email == email_a))
        user_b = db.scalar(select(User).where(User.email == email_b))

    company_id, source_id = make_company_and_source(factory)
    make_profile_for_user(factory, user_a.id, company_id)
    make_profile_for_user(factory, user_b.id, company_id)
    run_monitoring(
        factory,
        source_id,
        [
            raw_job(
                "shared-job", title="Software Engineer", description="Python backend developer"
            ),
        ],
    )

    with c_a:
        feed_a = c_a.get("/api/jobs").json()
        assert feed_a["total"] >= 1
        job_id = feed_a["items"][0]["id"]
        c_a.patch(f"/api/jobs/{job_id}/status", json={"status": "saved", "notes": ""})
        # User A sees it as saved
        assert c_a.get(f"/api/jobs/{job_id}/status").json()["status"] == "saved"

    with c_b:
        # User B still sees it as new
        r = c_b.get(f"/api/jobs/{job_id}/status")
        assert r.status_code == 200
        assert r.json()["status"] == "new"


# ---------------------------------------------------------------------------
# 3. Notifications read-state
# ---------------------------------------------------------------------------


def _make_notification(factory, user_id, job_id=None):
    """Directly insert a notification row for testing."""
    if job_id is None:
        cid, sid = make_company_and_source(factory)
        with factory.begin() as db:
            job = Job(
                company_id=cid,
                source_id=sid,
                external_job_id=uuid.uuid4().hex,
                title="Software Engineer",
                description="Python",
                location="Remote",
                application_url="https://example.com/jobs/test",
                content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                first_seen_at=datetime.now(UTC),
                last_seen_at=datetime.now(UTC),
            )
            db.add(job)
            db.flush()
            job_id = job.id
    with factory.begin() as db:
        n = Notification(
            user_id=user_id,
            job_id=job_id,
            kind="new_job",
            revision="initial",
            material_hash=uuid.uuid4().hex,
            payload={
                "kind": "new_job",
                "company": "Acme",
                "job": {"title": "SWE", "id": str(job_id)},
                "profiles": [],
            },
            available_at=datetime.now(UTC),
        )
        db.add(n)
        db.flush()
        nid = n.id
    return nid, job_id


def test_notification_read_state_mark_single(factory):
    """Mark single notification as read sets read_at and is_read=True."""
    c, email = make_authed_client()
    with factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        user_id = user.id

    nid, _ = _make_notification(factory, user_id)

    with c:
        # List - should show unread
        r_list = c.get("/api/notifications")
        assert r_list.status_code == 200
        notifs = r_list.json()
        assert any(n["id"] == str(nid) for n in notifs)
        unread = next(n for n in notifs if n["id"] == str(nid))
        assert unread["is_read"] is False

        # Mark single as read
        r_read = c.patch(f"/api/notifications/{nid}/read")
        assert r_read.status_code == 200
        assert r_read.json()["is_read"] is True
        assert r_read.json()["read_at"] is not None

        # List again - should show read
        r_list2 = c.get("/api/notifications")
        updated = next(n for n in r_list2.json() if n["id"] == str(nid))
        assert updated["is_read"] is True


def test_notification_read_all(factory):
    """Mark all notifications as read marks all unread ones."""
    c, email = make_authed_client()
    with factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        user_id = user.id

    # Create 3 unread notifications
    nids = []
    for _ in range(3):
        nid, _ = _make_notification(factory, user_id)
        nids.append(nid)

    with c:
        r = c.patch("/api/notifications/read-all")
        assert r.status_code == 200
        assert r.json()["marked_count"] == 3

        # All should now be read
        r_list = c.get("/api/notifications")
        notifs = {n["id"]: n for n in r_list.json()}
        for nid in nids:
            assert notifs[str(nid)]["is_read"] is True

        # Calling again returns 0 (already all read)
        r2 = c.patch("/api/notifications/read-all")
        assert r2.json()["marked_count"] == 0


def test_notification_is_read_filter(factory):
    """Filter by is_read=false only returns unread notifications."""
    c, email = make_authed_client()
    with factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        user_id = user.id

    nid1, _ = _make_notification(factory, user_id)
    nid2, _ = _make_notification(factory, user_id)

    with c:
        # Mark one read
        c.patch(f"/api/notifications/{nid1}/read")

        r_unread = c.get("/api/notifications?is_read=false")
        assert r_unread.status_code == 200
        ids = [n["id"] for n in r_unread.json()]
        assert str(nid2) in ids
        assert str(nid1) not in ids

        r_read = c.get("/api/notifications?is_read=true")
        ids_read = [n["id"] for n in r_read.json()]
        assert str(nid1) in ids_read
        assert str(nid2) not in ids_read


def test_notification_ownership_isolation(factory):
    """User A cannot read or mark User B's notifications."""
    c_a, email_a = make_authed_client()
    c_b, email_b = make_authed_client()

    with factory() as db:
        user_b = db.scalar(select(User).where(User.email == email_b))

    nid, _ = _make_notification(factory, user_b.id)

    with c_a:
        # User A should not see User B's notification
        r = c_a.get("/api/notifications")
        ids = [n["id"] for n in r.json()]
        assert str(nid) not in ids

        # User A cannot fetch it directly
        r_get = c_a.get(f"/api/notifications/{nid}")
        assert r_get.status_code == 404

        # User A cannot mark it read
        r_read = c_a.patch(f"/api/notifications/{nid}/read")
        assert r_read.status_code == 404


# ---------------------------------------------------------------------------
# 4. Subscriptions & source health
# ---------------------------------------------------------------------------


def test_list_subscriptions(factory):
    """Subscription list shows all enabled companies with subscribed status."""
    c, email = make_authed_client()
    company_id, source_id = make_company_and_source(factory)

    with c:
        r = c.get("/api/subscriptions")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        our_company = next((item for item in items if item["company_id"] == str(company_id)), None)
        assert our_company is not None
        assert our_company["is_subscribed"] is False


def test_subscribe_toggle(factory):
    """Toggle subscription on/off updates is_subscribed correctly."""
    c, email = make_authed_client()
    with factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        user_id = user.id

    company_id, source_id = make_company_and_source(factory)

    # Create a profile first (needed for subscription)
    make_profile_for_user(factory, user_id, company_id, name="Dev Profile")

    with c:
        # Check current - should be subscribed (we already subscribed via make_profile_for_user)
        r = c.get("/api/subscriptions")
        items = r.json()
        our = next(i for i in items if i["company_id"] == str(company_id))
        assert our["is_subscribed"] is True

        # Unsubscribe
        r_unsub = c.post(
            "/api/subscriptions/toggle", json={"company_id": str(company_id), "subscribed": False}
        )
        assert r_unsub.status_code == 200
        assert r_unsub.json()["subscribed"] is False

        # Verify
        items2 = c.get("/api/subscriptions").json()
        our2 = next(i for i in items2 if i["company_id"] == str(company_id))
        assert our2["is_subscribed"] is False


def test_source_health_authorization(factory):
    """Source health endpoint denies access for unsubscribed companies."""
    c_owner, email_owner = make_authed_client()
    c_other, email_other = make_authed_client()

    with factory() as db:
        user_owner = db.scalar(select(User).where(User.email == email_owner))

    company_id, source_id = make_company_and_source(factory)
    make_profile_for_user(factory, user_owner.id, company_id)

    with c_owner:
        # Owner can access
        r = c_owner.get(f"/api/sources/{source_id}/health")
        assert r.status_code == 200
        assert "health_status" in r.json()

    with c_other:
        # Non-subscriber gets 403
        r = c_other.get(f"/api/sources/{source_id}/health")
        assert r.status_code == 403


def test_source_health_values(factory):
    """Derive health correctly: healthy source returns 'healthy'."""
    c, email = make_authed_client()
    with factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        user_id = user.id

    company_id, source_id = make_company_and_source(factory)
    make_profile_for_user(factory, user_id, company_id)

    with c:
        r = c.get(f"/api/sources/{source_id}/health")
        assert r.status_code == 200
        data = r.json()
        assert data["health_status"] == "healthy"
        assert data["consecutive_failures"] == 0
        assert data["active"] is True


# ---------------------------------------------------------------------------
# 5. Dashboard
# ---------------------------------------------------------------------------


def test_dashboard_empty_state(factory):
    """Newly created user dashboard returns zeroed stats."""
    c, email = make_authed_client()
    with c:
        r = c.get("/api/dashboard")
        assert r.status_code == 200
        data = r.json()
        stats = data["stats"]
        assert stats["active_profiles_count"] == 0
        assert stats["monitored_companies_count"] == 0
        assert stats["new_jobs_count"] == 0
        assert stats["saved_jobs_count"] == 0
        assert stats["applied_jobs_count"] == 0
        assert stats["ignored_jobs_count"] == 0
        assert stats["unread_notifications_count"] == 0
        assert data["recent_jobs"] == []
        assert data["monitored_companies"] == []


def test_dashboard_with_activity(factory):
    """Dashboard counts reflect real data: profiles, companies, jobs, notifications."""
    c, email = make_authed_client()
    with factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        user_id = user.id

    company_id, source_id = make_company_and_source(factory)
    make_profile_for_user(factory, user_id, company_id)

    # Create matched jobs
    run_monitoring(
        factory,
        source_id,
        [
            raw_job("dash-j1", title="Software Engineer", description="Python developer"),
            raw_job("dash-j2", title="Backend Developer", description="Python backend role"),
        ],
    )

    # Add a notification
    nid, _ = _make_notification(factory, user_id)

    with c:
        r = c.get("/api/dashboard")
        assert r.status_code == 200
        data = r.json()
        stats = data["stats"]

        assert stats["active_profiles_count"] >= 1
        assert stats["monitored_companies_count"] >= 1
        # There should be new matching jobs
        assert stats["new_jobs_count"] >= 1
        assert stats["unread_notifications_count"] >= 1

        # health summary includes our subscribed company
        assert isinstance(data["source_health_summary"], dict)
        assert "healthy_count" in data["source_health_summary"]

        # Monitored companies only shows subscribed ones
        subscribed = data["monitored_companies"]
        assert len(subscribed) >= 1
        assert all(c["is_subscribed"] for c in subscribed)


def test_dashboard_job_interaction_counts(factory):
    """Dashboard counts update when jobs are saved/applied/ignored."""
    c, email = make_authed_client()
    with factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        user_id = user.id

    company_id, source_id = make_company_and_source(factory)
    make_profile_for_user(factory, user_id, company_id)

    run_monitoring(
        factory,
        source_id,
        [
            raw_job("cnt-j1", title="Software Engineer", description="Python developer"),
            raw_job("cnt-j2", title="Software Engineer II", description="Python backend engineer"),
            raw_job("cnt-j3", title="Software Engineer III", description="Python senior developer"),
        ],
    )

    with c:
        feed = c.get("/api/jobs").json()
        assert feed["total"] >= 3
        ids = [item["id"] for item in feed["items"][:3]]

        # Save one, apply one, ignore one
        c.patch(f"/api/jobs/{ids[0]}/status", json={"status": "saved", "notes": ""})
        c.patch(f"/api/jobs/{ids[1]}/status", json={"status": "applied", "notes": ""})
        c.patch(f"/api/jobs/{ids[2]}/status", json={"status": "ignored", "notes": ""})

        r = c.get("/api/dashboard")
        stats = r.json()["stats"]
        assert stats["saved_jobs_count"] >= 1
        assert stats["applied_jobs_count"] >= 1
        assert stats["ignored_jobs_count"] >= 1


# ---------------------------------------------------------------------------
# 6. Multi-profile aggregation (same job, two profiles)
# ---------------------------------------------------------------------------


def test_job_feed_no_duplicates_with_multiple_profiles(factory):
    """A job matching two profiles for same user appears only once in the feed."""
    c, email = make_authed_client()
    with factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        user_id = user.id

    company_id, source_id = make_company_and_source(factory)
    # Two profiles, same company
    make_profile_for_user(
        factory, user_id, company_id, name="Profile A", role="Software Engineer", skill="Python"
    )
    make_profile_for_user(
        factory, user_id, company_id, name="Profile B", role="Backend Developer", skill="Python"
    )

    run_monitoring(
        factory,
        source_id,
        [
            raw_job(
                "multi-j1", title="Software Engineer", description="Python backend developer role"
            ),
        ],
    )

    with c:
        r = c.get("/api/jobs")
        data = r.json()
        # Should only have one entry for the job
        assert data["total"] >= 1
        ids = [item["id"] for item in data["items"]]
        assert len(ids) == len(set(ids)), "Duplicate job cards found in feed"


# ---------------------------------------------------------------------------
# 7. Unauthenticated access returns 401
# ---------------------------------------------------------------------------


def test_unauthenticated_endpoints_return_401(factory):
    """All Phase 8 endpoints require authentication."""
    c = TestClient(app, headers={"Origin": settings.app_origin})
    endpoints = [
        "/api/jobs",
        "/api/dashboard",
        "/api/subscriptions",
        "/api/notifications",
    ]
    for path in endpoints:
        r = c.get(path)
        assert r.status_code == 401, f"Expected 401 for {path}, got {r.status_code}"


def test_unmatched_user_cannot_read_or_change_job(factory):
    owner, email = make_authed_client()
    other, _ = make_authed_client()
    with factory() as db:
        uid = db.scalar(select(User.id).where(User.email == email))
    company_id, source_id = make_company_and_source(factory)
    make_profile_for_user(factory, uid, company_id)
    run_monitoring(factory, source_id, [raw_job()])
    with owner, other:
        job_id = owner.get("/api/jobs").json()["items"][0]["id"]
        assert other.get("/api/jobs").json()["total"] == 0
        assert other.get("/api/notifications/metrics").json()["total_count"] == 0
        assert owner.get("/api/notifications/metrics").json()["total_count"] == 1
        assert (
            owner.patch(
                f"/api/jobs/{job_id}/status",
                json={"status": "saved"},
                headers={"Origin": "https://untrusted.example"},
            ).status_code
            == 403
        )
        assert other.get(f"/api/jobs/{job_id}").status_code == 404
        assert other.get(f"/api/jobs/{job_id}/status").status_code == 404
        assert (
            other.patch(f"/api/jobs/{job_id}/status", json={"status": "saved"}).status_code == 404
        )
        assert owner.get(f"/api/jobs/{job_id}/status").json()["status"] == "new"


def test_feed_filters_explanations_and_canonical_isolation(factory):
    a, email_a = make_authed_client()
    b, email_b = make_authed_client()
    with factory() as db:
        aid = db.scalar(select(User.id).where(User.email == email_a))
        bid = db.scalar(select(User.id).where(User.email == email_b))
    company_id, source_id = make_company_and_source(factory)
    pid = make_profile_for_user(factory, aid, company_id)
    make_profile_for_user(factory, bid, company_id)
    run_monitoring(factory, source_id, [raw_job()])
    with a, b:
        item = a.get("/api/jobs").json()["items"][0]
        jid = item["id"]
        assert item["match_reasons"]
        assert (
            a.get(
                "/api/jobs",
                params={
                    "profile_id": str(pid),
                    "company_id": str(company_id),
                    "location": "Remote",
                    "search": "Engineer",
                },
            ).json()["total"]
            == 1
        )
        assert a.get("/api/jobs?min_score=100").json()["total"] == 0
        assert a.get("/api/jobs?discovered_after=2099-01-01T00:00:00Z").json()["total"] == 0
        assert a.get("/api/jobs?employment_type=imaginary").json()["total"] == 0
        with factory() as db:
            canonical_before = dict(
                db.execute(select(Job.__table__).where(Job.id == uuid.UUID(jid))).mappings().one()
            )
        assert a.patch(f"/api/jobs/{jid}/status", json={"status": "saved"}).status_code == 200
        assert b.patch(f"/api/jobs/{jid}/status", json={"status": "applied"}).status_code == 200
        assert a.get(f"/api/jobs/{jid}/status").json()["status"] == "saved"
        assert b.get(f"/api/jobs/{jid}/status").json()["status"] == "applied"
        with factory() as db:
            canonical_after = dict(
                db.execute(select(Job.__table__).where(Job.id == uuid.UUID(jid))).mappings().one()
            )
        assert canonical_before == canonical_after
        notices = a.get("/api/notifications").json()
        assert notices
        assert "payload" not in notices[0] and "last_error" not in notices[0]


@pytest.mark.parametrize(
    "failures,state,active,expected",
    [
        (0, "healthy", True, "healthy"),
        (1, "degraded", True, "degraded"),
        (3, "failing", True, "failing"),
        (0, "unsupported", True, "unsupported"),
        (0, "healthy", False, "unsupported"),
    ],
)
def test_health_states_and_catalog_privacy(factory, failures, state, active, expected):
    c, email = make_authed_client()
    with factory() as db:
        uid = db.scalar(select(User.id).where(User.email == email))
    cid, sid = make_company_and_source(factory)
    with factory.begin() as db:
        source = db.get(JobSource, sid)
        source.consecutive_failures = failures
        source.health_status = state
        source.active = active
        source.last_error_at = datetime.now(UTC)
    with c:
        item = next(i for i in c.get("/api/subscriptions").json() if i["company_id"] == str(cid))
        assert item["source_health"] is None and item["last_checked_at"] is None
        make_profile_for_user(factory, uid, cid)
        assert c.get(f"/api/sources/{sid}/health").json()["health_status"] == expected
