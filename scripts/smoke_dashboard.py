"""Authenticated browser smoke against Compose using persisted FakeSource data.
Run: docker compose cp scripts/smoke_dashboard.py backend:/tmp/smoke_dashboard.py
     docker compose exec -e PYTHONPATH=/app backend python /tmp/smoke_dashboard.py
No live career site or email provider is contacted. Created records are removed.
"""

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from sqlalchemy import delete, select, text

from app.db.session import SessionLocal
from app.models.auth import User
from app.models.catalog import Company, JobSource
from app.models.job import Job
from app.monitoring.runner import run_source
from app.schemas.catalog import CompanyCreate, SourceCreate
from app.services import catalog
from app.sources.base import RawJob
from app.sources.fake import FakeSource


def main():
    token = uuid.uuid4().hex
    users = []
    cid = None
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        a = browser.new_context(
            base_url="http://frontend:3000",
            timezone_id="Asia/Kolkata",
            extra_http_headers={"Origin": "http://localhost:3000"},
        )
        b = browser.new_context(
            base_url="http://frontend:3000",
            timezone_id="Asia/Kolkata",
            extra_http_headers={"Origin": "http://localhost:3000"},
        )
        try:
            for context, name in [(a, "alice"), (b, "bob")]:
                response = context.request.post(
                    "/api/auth/signup",
                    data={
                        "email": f"phase8-{name}-{token}@example.com",
                        "password": "SmokePassword123!",
                    },
                )
                assert response.status == 201, response.text()
                users.append(uuid.UUID(response.json()["id"]))
            with SessionLocal.begin() as db:
                company = catalog.create_company(
                    db,
                    CompanyCreate(
                        name=f"Smoke Company {token[:8]}", slug=f"smoke-{token}", enabled=True
                    ),
                )
                cid = company.id
                source = catalog.create_source(
                    db,
                    SourceCreate(
                        company_id=cid,
                        source_type="greenhouse",
                        config={"board_token": "fixture"},
                        active=True,
                        poll_interval_sec=60,
                    ),
                )
                sid = source.id
            for context, names in [(a, ["Engineer", "Backend"]), (b, ["Engineer"])]:
                for name in names:
                    r = context.request.post(
                        "/api/profiles",
                        data={
                            "name": name,
                            "active": True,
                            "roles": [{"name": "Software Engineer"}],
                            "skills": [{"name": "Python", "kind": "required"}],
                        },
                    )
                    assert r.status == 201, r.text()
                r = context.request.post(
                    "/api/subscriptions", data={"company_id": str(cid), "subscribed": True}
                )
                assert r.status == 200, r.text()
            fake = FakeSource(
                [
                    [
                        RawJob(
                            external_id="smoke-job",
                            title="Software Engineer",
                            description="Python developer",
                            location="Remote",
                            url="https://example.com/careers/smoke",
                        )
                    ]
                ]
            )
            with ThreadPoolExecutor(max_workers=1) as executor:
                result = executor.submit(
                    lambda: asyncio.run(run_source(SessionLocal, sid, adapter=fake))
                ).result()
                assert result.status == "success", result
            feed = a.request.get("/api/jobs").json()
            assert feed["total"] == 1
            item = feed["items"][0]
            assert len(item["matched_profiles"]) == 2
            jid = item["id"]
            with SessionLocal() as db:
                before = dict(
                    db.execute(select(Job.__table__).where(Job.id == uuid.UUID(jid)))
                    .mappings()
                    .one()
                )
            with SessionLocal() as db:
                plans = []
                for sql in [
                    "SELECT id FROM notifications WHERE user_id = :uid ORDER BY created_at DESC, id DESC LIMIT 20",
                    "SELECT j.id FROM jobs j WHERE j.id IN (SELECT m.job_id FROM job_matches m JOIN profiles p ON p.id = m.profile_id WHERE p.user_id = :uid AND p.active AND m.matched AND m.status = 'evaluated') AND j.status = 'open' ORDER BY coalesce(j.posted_at, j.first_seen_at) DESC, j.id DESC LIMIT 20",
                ]:
                    rows = db.execute(
                        text("EXPLAIN (ANALYZE, BUFFERS) " + sql), {"uid": users[0]}
                    ).all()
                    plans.append(sql + "\n" + "\n".join(row[0] for row in rows))
                Path("/tmp/phase8-query-plans.txt").write_text("\n\n".join(plans))
            page = a.new_page()
            # Internal Compose hostname differs from the configured public origin.
            page.route(
                "**/api/**",
                lambda route: route.fulfill(
                    response=route.fetch(
                        headers={**route.request.headers, "origin": "http://localhost:3000"}
                    )
                ),
            )
            page.goto("/dashboard")
            expect(page.get_by_role("heading", name="Dashboard", exact=True)).to_be_visible()
            expect(page.get_by_text("Software Engineer", exact=True)).to_be_visible()
            expect(page.locator(".dashboard-stats .card")).to_have_count(7)
            assert page.locator(".dashboard-stats").evaluate(
                "el => getComputedStyle(el).display === 'grid'"
            )
            page.screenshot(path="/tmp/phase8-dashboard.png", full_page=True)
            page.goto("/jobs")
            expect(page.get_by_role("heading", name="Software Engineer", exact=True)).to_have_count(
                1
            )
            expect(page.get_by_text("Engineer |", exact=False).first).to_be_visible()
            page.get_by_role("button", name="Save", exact=True).click()
            expect(page.get_by_role("status").filter(has_text="Change saved")).to_be_visible()
            page.goto("/saved")
            expect(
                page.get_by_role("heading", name="Software Engineer", exact=True)
            ).to_be_visible()
            assert (
                b.request.patch(f"/api/jobs/{jid}/status", data={"status": "applied"}).status == 200
            )
            assert a.request.get(f"/api/jobs/{jid}/status").json()["status"] == "saved"
            page.get_by_role("button", name="Mark applied", exact=True).click()
            expect(page.get_by_role("status").filter(has_text="Change saved")).to_be_visible()
            page.goto("/applied")
            expect(
                page.get_by_role("heading", name="Software Engineer", exact=True)
            ).to_be_visible()
            page.goto("/notifications")
            expect(page.get_by_role("heading", name="Notifications", exact=True)).to_be_visible()
            notice = a.request.get("/api/notifications").json()[0]
            delivery = notice["delivery_status"]
            page.get_by_role("button", name="Mark read", exact=True).click()
            expect(page.get_by_role("button", name="Mark read", exact=True)).to_have_count(0)
            notice_after = a.request.get("/api/notifications").json()[0]
            assert notice_after["is_read"] and notice_after["delivery_status"] == delivery
            page.get_by_role("link", name="Open job", exact=True).click()
            expect(
                page.get_by_role("heading", name="Software Engineer", exact=True)
            ).to_be_visible()
            for path, heading in [
                ("/companies", "Companies"),
                ("/profiles", "Job profiles"),
                ("/account", "Account"),
            ]:
                page.goto(path)
                if path == "/profiles":
                    expect(
                        page.get_by_role("link", name="Create profile", exact=True)
                    ).to_be_visible()
                else:
                    expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible()
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto("/jobs")
            expect(page.get_by_role("heading", name="Jobs", exact=True)).to_be_visible()
            page.screenshot(path="/tmp/phase8-mobile.png", full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            with SessionLocal() as db:
                after = dict(
                    db.execute(select(Job.__table__).where(Job.id == uuid.UUID(jid)))
                    .mappings()
                    .one()
                )
            assert before == after
            print(
                "PASS: 9 authenticated pages; monitoring -> match -> notification -> dashboard -> save -> apply; 2 profiles / 1 card; 2 user states; read independent of delivery; canonical unchanged; mobile layout"
            )
        finally:
            browser.close()
            with SessionLocal.begin() as db:
                db.execute(delete(User).where(User.id.in_(users)))
                if cid:
                    db.execute(delete(Job).where(Job.company_id == cid))
                    db.execute(delete(JobSource).where(JobSource.company_id == cid))
                    db.execute(delete(Company).where(Company.id == cid))


if __name__ == "__main__":
    main()
