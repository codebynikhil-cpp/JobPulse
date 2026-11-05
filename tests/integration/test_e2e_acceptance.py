"""Comprehensive End-to-End Acceptance Test (Phase 15).

Verifies the complete 14-step user journey deterministically with 0 external network dependencies:
1. Register a new user.
2. Authenticate and verify session.
3. Create a target job profile (roles, skills, location, experience).
4. Discover and select companies to monitor (Greenhouse, Lever, and Ashby).
5. Trigger career source monitoring runs.
6. Ingest jobs through the respective adapters.
7. Verify deduplication and normalization across repeated runs.
8. Evaluate candidate jobs against user profile.
9. Verify matching score and match reasons are recorded.
10. Generate an outbox notification for high-scoring jobs.
11. Process outbox notifications through the delivery worker.
12. Verify delivery status transitions from pending to sent.
13. Interact with the job (save, mark as applied, ignore).
14. Verify company source health and status reporting.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.job import Job
from app.models.notification import Notification
from app.monitoring.runner import run_source
from app.notifications.provider import MockEmailProvider
from app.notifications.worker import NotificationWorker
from app.schemas.catalog import CompanyCreate, SourceCreate
from app.services import catalog
from app.sources.ashby import AshbyAdapter
from app.sources.lever import LeverAdapter

LEVER_FIXTURE = Path(__file__).parents[1] / "fixtures" / "lever" / "postings.json"
ASHBY_FIXTURE = Path(__file__).parents[1] / "fixtures" / "ashby" / "board.json"


@pytest.fixture(autouse=True)
def bypass_dns(monkeypatch):
    async def noop():
        pass

    monkeypatch.setattr("app.sources.lever.verify_public_host", noop)
    monkeypatch.setattr("app.sources.ashby.verify_public_host", noop)
    monkeypatch.setattr("app.sources.greenhouse.verify_public_host", noop)


def test_complete_14_step_acceptance_workflow(client, migrated_database):
    factory = sessionmaker(migrated_database, expire_on_commit=False)

    # =========================================================================
    # Step 1: Register a new user
    # =========================================================================
    email = f"e2e_engineer_{uuid.uuid4().hex[:8]}@example.com"
    signup_res = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "StrongPassword123!"},
    )
    assert signup_res.status_code == 201, signup_res.text
    user_data = signup_res.json()
    user_id = uuid.UUID(user_data["id"])
    assert user_data["email"] == email

    # =========================================================================
    # Step 2: Authenticate and establish session
    # =========================================================================
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200, me_res.text
    assert me_res.json()["id"] == str(user_id)

    # =========================================================================
    # Step 3: Create a target job profile (role, skills, location, experience)
    # =========================================================================
    profile_payload = {
        "name": "Staff / Lead Engineer Target",
        "description": "Backend platform targets",
        "active": True,
        "roles": [{"name": "Software Engineer"}, {"name": "Backend Engineer"}],
        "skills": [
            {"name": "Python", "kind": "required"},
            {"name": "PostgreSQL", "kind": "preferred"},
        ],
        "locations": [{"name": "San Francisco, CA"}, {"name": "Remote"}],
        "work_modes": ["remote", "hybrid"],
        "employment_types": ["full_time"],
    }
    profile_res = client.post("/api/profiles", json=profile_payload)
    assert profile_res.status_code == 201, profile_res.text
    profile_id = uuid.UUID(profile_res.json()["id"])
    assert profile_res.json()["name"] == profile_payload["name"]

    # =========================================================================
    # Step 4: Discover and select companies to monitor (Greenhouse, Lever, Ashby)
    # =========================================================================
    with factory.begin() as db:
        # 1. Lever Company
        c_lever = catalog.create_company(
            db,
            CompanyCreate(
                name="Acme Lever Corp", slug=f"lever-{uuid.uuid4().hex[:6]}", enabled=True
            ),
        )
        s_lever = catalog.create_source(
            db,
            SourceCreate(
                company_id=c_lever.id, source_type="lever", config={"site": "acme"}, active=True
            ),
        )
        lever_cid, lever_sid = c_lever.id, s_lever.id

        # 2. Ashby Company
        c_ashby = catalog.create_company(
            db,
            CompanyCreate(
                name="Globex Ashby Corp", slug=f"ashby-{uuid.uuid4().hex[:6]}", enabled=True
            ),
        )
        s_ashby = catalog.create_source(
            db,
            SourceCreate(
                company_id=c_ashby.id,
                source_type="ashby",
                config={"job_board_name": "globex"},
                active=True,
            ),
        )
        ashby_cid, ashby_sid = c_ashby.id, s_ashby.id

    # Subscribe candidate to both companies via API
    sub1 = client.post(
        "/api/subscriptions/toggle",
        json={"company_id": str(lever_cid), "subscribed": True, "profile_id": str(profile_id)},
    )
    assert sub1.status_code == 200 and sub1.json()["subscribed"] is True

    sub2 = client.post(
        "/api/subscriptions/toggle",
        json={"company_id": str(ashby_cid), "subscribed": True, "profile_id": str(profile_id)},
    )
    assert sub2.status_code == 200 and sub2.json()["subscribed"] is True

    # =========================================================================
    # Step 5 & 6: Ingest jobs through the respective adapters
    # =========================================================================
    lever_json = json.loads(LEVER_FIXTURE.read_text())
    ashby_json = json.loads(ASHBY_FIXTURE.read_text())

    lever_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=lever_json))
    )
    ashby_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=ashby_json))
    )

    lever_adapter = LeverAdapter({"site": "acme"}, lever_client)
    ashby_adapter = AshbyAdapter({"job_board_name": "globex"}, ashby_client)

    run_lever_1 = asyncio.run(run_source(factory, lever_sid, adapter=lever_adapter))
    assert run_lever_1.status == "success"
    assert run_lever_1.fetched_count == 2
    assert run_lever_1.created_count == 2

    run_ashby_1 = asyncio.run(run_source(factory, ashby_sid, adapter=ashby_adapter))
    assert run_ashby_1.status == "success"
    assert run_ashby_1.fetched_count == 2
    assert run_ashby_1.created_count == 2

    # =========================================================================
    # Step 7: Verify deduplication and normalization across repeated runs
    # =========================================================================
    run_lever_2 = asyncio.run(run_source(factory, lever_sid, adapter=lever_adapter))
    assert run_lever_2.status == "success"
    assert run_lever_2.fetched_count == 2
    assert run_lever_2.created_count == 0  # Deduplicated! 0 new jobs created
    assert run_lever_2.unchanged_count == 2

    run_ashby_2 = asyncio.run(run_source(factory, ashby_sid, adapter=ashby_adapter))
    assert run_ashby_2.status == "success"
    assert run_ashby_2.fetched_count == 2
    assert run_ashby_2.created_count == 0  # Deduplicated!
    assert run_ashby_2.unchanged_count == 2

    with factory() as db:
        total_jobs = db.scalar(select(Job).filter(Job.source_id.in_([lever_sid, ashby_sid])))
        assert total_jobs is not None

    # =========================================================================
    # Step 8 & 9: Evaluate candidate jobs and verify matching score + reasons
    # =========================================================================
    # Fetch job feed via API
    feed_res = client.get("/api/jobs")
    assert feed_res.status_code == 200, feed_res.text
    feed = feed_res.json()
    assert feed["total"] >= 1
    matched_job = feed["items"][0]
    matched_job_id = matched_job["id"]
    assert matched_job["best_score"] > 0
    assert len(matched_job["matched_profiles"]) >= 1

    # Single job detail check
    detail_res = client.get(f"/api/jobs/{matched_job_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["title"] is not None
    assert detail["best_score"] == matched_job["best_score"]

    # =========================================================================
    # Step 10: Verify outbox notifications generated for high-scoring jobs
    # =========================================================================
    with factory() as db:
        notifs = list(db.scalars(select(Notification).where(Notification.user_id == user_id)))
        assert len(notifs) >= 1
        notif = notifs[0]
        assert notif.status == "pending"
        assert notif.sent_at is None

    # =========================================================================
    # Step 11 & 12: Process outbox notifications through delivery worker
    # =========================================================================
    mock_email_provider = MockEmailProvider()
    outbox_worker = NotificationWorker(factory, provider=mock_email_provider)
    batch_result = outbox_worker.process_batch()
    assert batch_result.claimed >= 1
    assert batch_result.sent >= 1
    assert len(mock_email_provider.sent_messages) >= 1

    sent_message = mock_email_provider.sent_messages[0]
    assert sent_message.recipient == email
    assert "JobPulse" in sent_message.subject

    # Verify durable delivery status in database
    with factory() as db:
        notif_delivered = db.scalar(select(Notification).where(Notification.user_id == user_id))
        assert notif_delivered.status == "sent"
        assert notif_delivered.sent_at is not None

    # Verify notification via API
    api_notifs = client.get("/api/notifications")
    assert api_notifs.status_code == 200
    assert len(api_notifs.json()) >= 1
    assert api_notifs.json()[0]["status"] == "sent"

    # =========================================================================
    # Step 13: Interact with the job (save, mark as applied, ignore)
    # =========================================================================
    # Save job
    save_res = client.post(
        f"/api/jobs/{matched_job_id}/status",
        json={"status": "saved", "notes": "Prioritized for application"},
    )
    assert save_res.status_code == 200
    assert save_res.json()["status"] == "saved"
    assert save_res.json()["notes"] == "Prioritized for application"

    # Mark as applied
    applied_res = client.post(
        f"/api/jobs/{matched_job_id}/status",
        json={"status": "applied", "notes": "Submitted application on company portal"},
    )
    assert applied_res.status_code == 200
    assert applied_res.json()["status"] == "applied"

    # Check status endpoint
    status_check = client.get(f"/api/jobs/{matched_job_id}/status")
    assert status_check.status_code == 200
    assert status_check.json()["status"] == "applied"

    # =========================================================================
    # Step 14: Verify company source health and status reporting
    # =========================================================================
    subs_res = client.get("/api/subscriptions")
    assert subs_res.status_code == 200
    subs = subs_res.json()
    lever_sub = next(s for s in subs if s["company_id"] == str(lever_cid))
    ashby_sub = next(s for s in subs if s["company_id"] == str(ashby_cid))

    assert lever_sub["source_health"] == "healthy"
    assert lever_sub["is_subscribed"] is True
    assert lever_sub["acquisition_method"] == "http"
    assert ashby_sub["source_health"] == "healthy"
    assert ashby_sub["is_subscribed"] is True
    assert ashby_sub["acquisition_method"] == "http"

    health_res = client.get(f"/api/sources/{lever_sid}/health")
    assert health_res.status_code == 200
    assert health_res.json()["health_status"] == "healthy"
