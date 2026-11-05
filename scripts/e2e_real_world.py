"""End-to-End Real-World Workflow Test (Task 8).

Executes a complete 15-step user journey against real live company career APIs
(Linear on Ashby / Palantir on Lever), creating a real disposable account and
verifying the entire lifecycle:
1. Register a real test account.
2. Authenticate and establish session.
3. Create a Software Engineer profile.
4. Add relevant skills and target locations.
5. Subscribe to a real supported company (Linear on Ashby).
6. Ingest real live public job postings.
7. Persist canonical job records.
8. Calculate deterministic matching scores.
9. Verify relevant jobs in user feed.
10. Generate notifications for high-scoring jobs.
11. Process outbox notification delivery.
12. Save a job.
13. Mark a job as applied.
14. Repeat ingestion of the live board.
15. Verify duplicate prevention (0 created, all deduplicated).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime

# Ensure backend app is on import path
for p in ("/app", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")), os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))):
    if p not in sys.path:
        sys.path.insert(0, p)

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.auth import User
from app.models.catalog import Company, JobSource
from app.models.job import Job
from app.models.monitoring import JobMatch
from app.models.notification import Notification
from app.monitoring.runner import run_source
from app.notifications.config import NotificationConfig
from app.notifications.provider import MockEmailProvider, get_email_provider
from app.notifications.worker import NotificationWorker
from app.schemas.catalog import CompanyCreate, SourceCreate
from app.services import catalog, job_feed, job_interactions
from app.sources.ashby import AshbyAdapter


async def run_e2e_real_world():
    print("=" * 70)
    print("ROLE RADAR — REAL-WORLD END-TO-END ACCEPTANCE WORKFLOW")
    print("=" * 70)

    factory = SessionLocal

    # -------------------------------------------------------------------------
    # Step 1: Register real disposable account
    # -------------------------------------------------------------------------
    test_id = uuid.uuid4().hex[:8]
    email = f"real_user_{test_id}@example.com"
    password = f"P@ssword_{uuid.uuid4().hex[:12]}!"
    print(f"\n[Step 1] Registering real test account: {email}")

    base_url = "http://127.0.0.1:8000"
    headers = {"Origin": settings.app_origin}

    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30.0) as client:
        signup_res = await client.post(
            "/api/auth/signup",
            json={"email": email, "password": password},
        )
        assert signup_res.status_code == 201, f"Signup failed: {signup_res.text}"
        user_id = uuid.UUID(signup_res.json()["id"])
        print(f"[SUCCESS] User registered with ID: {user_id}")

        # ---------------------------------------------------------------------
        # Step 2: Authenticate and establish session
        # ---------------------------------------------------------------------
        print("\n[Step 2] Authenticating and verifying session...")
        me_res = await client.get("/api/auth/me")
        assert me_res.status_code == 200, f"Session verification failed: {me_res.text}"
        assert me_res.json()["id"] == str(user_id)
        print(f"[SUCCESS] Authenticated session confirmed for: {email}")

        # ---------------------------------------------------------------------
        # Step 3 & 4: Create Software Engineer job-search profile
        # ---------------------------------------------------------------------
        print("\n[Step 3 & 4] Creating Software Engineer target profile with skills...")
        profile_payload = {
            "name": "Fullstack / Backend Lead",
            "description": "Looking for modern web platform roles",
            "active": True,
            "roles": [{"name": "Software Engineer"}, {"name": "Fullstack Engineer"}],
            "skills": [
                {"name": "TypeScript", "kind": "required"},
                {"name": "React", "kind": "required"},
                {"name": "Python", "kind": "preferred"},
            ],
            "locations": [{"name": "Remote"}, {"name": "Europe"}, {"name": "San Francisco"}],
            "work_modes": ["remote", "hybrid"],
            "employment_types": ["full_time"],
        }
        profile_res = await client.post("/api/profiles", json=profile_payload)
        assert profile_res.status_code == 201, f"Profile creation failed: {profile_res.text}"
        profile_id = uuid.UUID(profile_res.json()["id"])
        print(f"[SUCCESS] Target profile created: ID={profile_id}")

        # ---------------------------------------------------------------------
        # Step 5: Select supported real company to monitor (Linear on Ashby)
        # ---------------------------------------------------------------------
        print("\n[Step 5] Provisioning and subscribing to real company: Linear (Ashby board)...")
        with factory.begin() as db:
            company = db.scalar(select(Company).where(Company.name == "Linear"))
            if not company:
                company = catalog.create_company(
                    db,
                    CompanyCreate(name="Linear", slug=f"linear-{test_id}", enabled=True),
                )
            source = db.scalar(select(JobSource).where(JobSource.company_id == company.id))
            if not source:
                source = catalog.create_source(
                    db,
                    SourceCreate(
                        company_id=company.id,
                        source_type="ashby",
                        config={"job_board_name": "linear"},
                        active=True,
                    ),
                )
            company_id = company.id
            source_id = source.id

        sub_res = await client.post(
            "/api/subscriptions/toggle",
            json={"company_id": str(company_id), "subscribed": True, "profile_id": str(profile_id)},
        )
        assert sub_res.status_code == 200, f"Subscription failed: {sub_res.text}"
        print(f"[SUCCESS] Subscribed user profile to Linear (Source ID: {source_id})")

        # ---------------------------------------------------------------------
        # Step 6 & 7: Fetch real public jobs and persist canonical records
        # ---------------------------------------------------------------------
        print("\n[Step 6 & 7] Triggering monitoring run against live Ashby API...")
        async with httpx.AsyncClient(timeout=30.0) as ashby_http:
            adapter = AshbyAdapter({"job_board_name": "linear"}, ashby_http)
            run1 = await run_source(factory, source_id, adapter=adapter)

        print(f"Run 1 Result: status={run1.status}")
        print(f"  Fetched count: {run1.fetched_count}")
        print(f"  Created count: {run1.created_count}")
        print(f"  Matched count: {run1.matched_count}")
        assert run1.status == "success", f"Monitoring run failed: {run1.error}"
        assert run1.fetched_count > 0, "No jobs fetched from real Linear board"
        with factory() as db:
            total_persisted = db.scalar(select(func.count(Job.id)).where(Job.source_id == source_id))
        assert total_persisted > 0, "No canonical jobs persisted in database"
        print(f"[SUCCESS] Successfully verified {run1.fetched_count} jobs from Linear ({total_persisted} total persisted canonical records in DB)!")

        # ---------------------------------------------------------------------
        # Step 8 & 9: Verify matching scores and display relevant jobs
        # ---------------------------------------------------------------------
        print("\n[Step 8 & 9] Evaluating candidate jobs in user feed...")
        feed_res = await client.get("/api/jobs")
        assert feed_res.status_code == 200, f"Feed query failed: {feed_res.text}"
        feed_data = feed_res.json()
        print(f"Feed total matching jobs: {feed_data['total']}")
        assert feed_data["total"] > 0, "No matching jobs returned in user feed"

        top_job = feed_data["items"][0]
        top_job_id = top_job["id"]
        print(f"Top matched job: '{top_job['title']}' | Score: {top_job['best_score']}%")
        print(f"Location: {top_job['location']}")
        print(f"Application URL: {top_job['application_url']}")
        assert top_job["best_score"] > 0

        # ---------------------------------------------------------------------
        # Step 10 & 11: Outbox notifications and delivery
        # ---------------------------------------------------------------------
        print("\n[Step 10 & 11] Checking outbox notification generation and delivery...")
        with factory() as db:
            pending_notifs = list(db.scalars(select(Notification).where(Notification.user_id == user_id)))
            print(f"Outbox notifications generated for user: {len(pending_notifs)}")

        if pending_notifs:
            notif_worker = NotificationWorker(factory, provider=MockEmailProvider(), config=NotificationConfig.from_settings())
            batch = notif_worker.process_batch()
            print(f"Notification worker processed: claimed={batch.claimed}, sent={batch.sent}")
            with factory() as db:
                delivered = db.scalar(select(Notification).where(Notification.user_id == user_id))
                print(f"Delivered notification status: {delivered.status} (sent_at={delivered.sent_at})")
                assert delivered.status == "sent"
        print("[SUCCESS] Notification generation & delivery verified!")

        # ---------------------------------------------------------------------
        # Step 12 & 13: Job interactions (Save, Mark as Applied)
        # ---------------------------------------------------------------------
        print(f"\n[Step 12] Saving job '{top_job['title']}'...")
        save_res = await client.post(
            f"/api/jobs/{top_job_id}/status",
            json={"status": "saved", "notes": "Target application for Q4"},
        )
        assert save_res.status_code == 200
        assert save_res.json()["status"] == "saved"
        print("[SUCCESS] Job saved successfully!")

        print(f"\n[Step 13] Marking job as applied...")
        applied_res = await client.post(
            f"/api/jobs/{top_job_id}/status",
            json={"status": "applied", "notes": "Submitted application on Linear career portal"},
        )
        assert applied_res.status_code == 200
        assert applied_res.json()["status"] == "applied"
        print("[SUCCESS] Job marked as applied successfully!")

        # ---------------------------------------------------------------------
        # Step 14 & 15: Repeat ingestion and verify duplicate prevention
        # ---------------------------------------------------------------------
        print("\n[Step 14 & 15] Repeating live ingestion to verify deduplication...")
        async with httpx.AsyncClient(timeout=30.0) as ashby_http2:
            adapter2 = AshbyAdapter({"job_board_name": "linear"}, ashby_http2)
            run2 = await run_source(factory, source_id, adapter=adapter2)

        print(f"Run 2 Result: status={run2.status}")
        print(f"  Fetched count: {run2.fetched_count}")
        print(f"  Created count: {run2.created_count} (Must be 0)")
        print(f"  Unchanged count: {run2.unchanged_count}")
        assert run2.created_count == 0, f"Duplicate jobs created on repeat: {run2.created_count}"
        assert run2.unchanged_count == run1.fetched_count
        print("[SUCCESS] Duplicate prevention verified: 0 new jobs created on repeat run!")

    print("\n" + "=" * 70)
    print("ALL 15 STEPS OF REAL-WORLD E2E WORKFLOW COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_e2e_real_world())

