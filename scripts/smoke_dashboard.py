"""Authenticated browser smoke against Compose using persisted FakeSource data.
Run: docker compose cp scripts/smoke_dashboard.py backend:/tmp/smoke_dashboard.py
     docker compose exec -e PYTHONPATH=/app backend python /tmp/smoke_dashboard.py
No live career site or email provider is contacted. Created records are removed.
"""

import asyncio
import os
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
    expect.set_options(timeout=15000)
    token = uuid.uuid4().hex
    users = []
    cid = None
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        a = browser.new_context(
            base_url=os.environ.get("FRONTEND_BASE_URL", "http://frontend:3000"),
            timezone_id="Asia/Kolkata",
            extra_http_headers={"Origin": "http://localhost:3000"},
        )
        b = browser.new_context(
            base_url=os.environ.get("FRONTEND_BASE_URL", "http://frontend:3000"),
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
                        career_url="https://example.com/careers/fixture",
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
            expect(
                page.locator(".job-list").get_by_role(
                    "heading", name="Software Engineer", exact=True
                )
            ).to_be_visible()
            expect(page.locator(".dashboard-summary")).to_be_visible()
            expect(page.locator(".monitoring-panel")).to_be_visible()
            expect(page.locator(".job-row")).to_have_count(1)
            assert page.locator(".dashboard-grid").evaluate(
                "el => getComputedStyle(el).display === 'grid'"
            )
            page.screenshot(path="/tmp/phase8-dashboard.png", full_page=True)
            page.goto("/jobs")
            expect(page.get_by_role("heading", name="Software Engineer", exact=True)).to_have_count(
                1
            )
            expect(
                page.locator(".profile-badges").get_by_text("Engineer", exact=False).first
            ).to_be_visible()
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
            expect(
                page.get_by_role("status").filter(has_text="Notification marked read.")
            ).to_be_visible()
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
            # Jobs filter URL survives refresh; empty results are actionable.
            page.goto("/jobs")
            page.get_by_role("textbox", name="Title or keyword").fill("no-such-role")
            page.get_by_role("button", name="Apply filters", exact=True).click()
            expect(page.get_by_role("heading", name="No matching jobs", exact=True)).to_be_visible()
            assert "search=no-such-role" in page.url
            page.reload()
            expect(page.get_by_role("textbox", name="Title or keyword")).to_have_value(
                "no-such-role"
            )
            page.get_by_role("link", name="Clear filters", exact=True).click()
            page.wait_for_url("**/jobs")
            expect(
                page.get_by_role("heading", name="Software Engineer", exact=True)
            ).to_be_visible()
            page.get_by_role("button", name="Ignore", exact=True).click()
            expect(page.get_by_role("heading", name="No matching jobs", exact=True)).to_be_visible()
            page.goto("/jobs?user_status=ignored")
            page.get_by_role("button", name="Restore", exact=True).click()
            expect(page.get_by_role("heading", name="No matching jobs", exact=True)).to_be_visible()
            page.goto("/jobs")
            expect(page.locator(".job-row")).to_have_count(1)
            # Structured profile creation, editing, activation and modal deletion.
            page.goto("/profiles/new")
            page.get_by_role("textbox", name="Name", exact=True).fill("UI verification")
            page.get_by_role("textbox", name="Target roles", exact=True).fill("Software Engineer")
            page.get_by_role("textbox", name="Target roles", exact=True).press("Enter")
            page.get_by_role("button", name="Create profile", exact=True).click()
            expect(page.get_by_role("heading", name="UI verification", exact=True)).to_be_visible()
            page.get_by_role("button", name="Activate", exact=True).click()
            expect(page.get_by_role("button", name="Deactivate", exact=True)).to_be_visible()
            page.get_by_role("link", name="Edit profile", exact=True).click()
            page.get_by_role("textbox", name="Name", exact=True).fill("UI verification edited")
            page.get_by_role("button", name="Save changes", exact=True).click()
            expect(
                page.get_by_role("heading", name="UI verification edited", exact=True)
            ).to_be_visible()
            page.get_by_role("button", name="Deactivate", exact=True).click()
            expect(page.get_by_role("button", name="Activate", exact=True)).to_be_visible()
            page.get_by_role("button", name="Delete", exact=True).click()
            dialog = page.get_by_role("dialog")
            expect(dialog).to_be_visible()
            assert page.evaluate(
                "document.querySelector('[role=dialog]').contains(document.activeElement)"
            )
            page.keyboard.press("Escape")
            expect(dialog).not_to_be_visible()
            page.get_by_role("button", name="Delete", exact=True).click()
            page.get_by_role("button", name="Delete profile", exact=True).click()
            expect(
                page.get_by_role("heading", name="Job search profiles", exact=True)
            ).to_be_visible()
            # Monitoring changes only affect the selected user/profile.
            page.goto("/companies")
            row = page.locator(".company-row").filter(has_text=f"Smoke Company {token[:8]}")
            expect(row.get_by_text("Healthy", exact=True)).to_be_visible()
            expect(row.get_by_role("link", name="Official career site")).to_have_attribute(
                "href", "https://example.com/careers/fixture"
            )
            row.get_by_role("button", name="Stop monitoring", exact=True).click()
            expect(row.get_by_role("button", name="Monitor company", exact=True)).to_be_visible()
            assert row.get_by_text("Healthy", exact=True).count() == 0
            row.get_by_role("button", name="Monitor company", exact=True).click()
            expect(row.get_by_text("Healthy", exact=True)).to_be_visible()
            # Health labels reflect current source state, without raw diagnostics.
            for state, failures, expected in [
                ("healthy", 0, "Healthy"),
                ("degraded", 1, "Degraded"),
                ("failing", 3, "Issue"),
                ("unsupported", 0, "Unsupported"),
            ]:
                with SessionLocal.begin() as db:
                    source = db.get(JobSource, sid)
                    source.health_status = state
                    source.consecutive_failures = failures
                page.goto("/companies")
                health_row = page.locator(".company-row").filter(
                    has_text=f"Smoke Company {token[:8]}"
                )
                expect(health_row.get_by_text(expected, exact=True)).to_be_visible()
            with SessionLocal.begin() as db:
                source = db.get(JobSource, sid)
                source.health_status = "healthy"
                source.consecutive_failures = 0
            page.goto("/notifications?is_read=false")
            expect(
                page.get_by_role("heading", name="You're all caught up", exact=True)
            ).to_be_visible()
            page.goto("/notifications?is_read=true")
            expect(page.locator(".notice-row")).to_have_count(1)
            # Test every major screen at four viewport sizes.
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            for width, height in [(390, 844), (768, 1024), (1280, 800), (1920, 1080)]:
                page.set_viewport_size({"width": width, "height": height})
                for path in [
                    "/dashboard",
                    "/jobs",
                    "/saved",
                    "/applied",
                    "/notifications",
                    "/companies",
                    "/profiles",
                    "/profiles/new",
                    f"/jobs/{jid}",
                    "/account",
                ]:
                    page.goto(path)
                    expect(page.locator("main h1")).to_be_visible()
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth"
                    ), (width, path)
                    if width == 1280:
                        filename = path.strip("/").replace("/", "-")
                        if path.startswith("/jobs/"):
                            filename = "job-detail"
                        page.screenshot(path=f"/tmp/redesign-{filename}.png", full_page=True)
                page.goto("/dashboard")
                expect(page.get_by_role("heading", name="Dashboard", exact=True)).to_be_visible()
                page.screenshot(path=f"/tmp/redesign-dashboard-{width}.png", full_page=True)
            assert not errors, errors
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto("/jobs")
            page.get_by_role("button", name="Open navigation").click()
            expect(page.get_by_role("dialog")).to_be_visible()
            assert page.evaluate(
                "document.querySelector('[role=dialog]').contains(document.activeElement)"
            )
            page.keyboard.press("Escape")
            expect(page.get_by_role("dialog")).not_to_be_visible()
            expect(page.get_by_role("button", name="Open navigation")).to_be_focused()
            page.goto("/jobs")
            expect(page.get_by_role("heading", name="Jobs", exact=True)).to_be_visible()
            page.screenshot(path="/tmp/phase8-mobile.png", full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            # Authentication runs through the real forms and account dropdown.
            c = browser.new_context(
                base_url=os.environ.get("FRONTEND_BASE_URL", "http://frontend:3000"),
                extra_http_headers={"Origin": "http://localhost:3000"},
            )
            auth_page = c.new_page()
            auth_page.route(
                "**/api/**",
                lambda route: route.fulfill(
                    response=route.fetch(
                        headers={**route.request.headers, "origin": "http://localhost:3000"}
                    )
                ),
            )
            email = f"redesign-ui-{token}@example.com"
            auth_page.goto("/signup")
            auth_page.get_by_role("textbox", name="Email", exact=True).fill(email)
            auth_page.get_by_label("Password", exact=True).fill("SmokePassword123!")
            with auth_page.expect_response("**/api/auth/signup") as signup_response:
                auth_page.get_by_role("button", name="Sign up", exact=True).click()
            users.append(uuid.UUID(signup_response.value.json()["id"]))
            expect(auth_page.get_by_role("heading", name="Dashboard", exact=True)).to_be_visible()
            auth_page.locator(".user-trigger").click()
            auth_page.get_by_role("menuitem", name="Log out", exact=True).click()
            expect(
                auth_page.get_by_role("heading", name="Welcome back", exact=True)
            ).to_be_visible()
            auth_page.get_by_role("textbox", name="Email", exact=True).fill(email)
            auth_page.get_by_label("Password", exact=True).fill("IncorrectPassword123!")
            auth_page.get_by_role("button", name="Log in", exact=True).click()
            expect(auth_page.locator(".error-state")).to_be_visible()
            auth_page.get_by_label("Password", exact=True).fill("SmokePassword123!")
            auth_page.get_by_role("button", name="Log in", exact=True).click()
            expect(auth_page.get_by_role("heading", name="Dashboard", exact=True)).to_be_visible()
            c.close()
            with SessionLocal() as db:
                after = dict(
                    db.execute(select(Job.__table__).where(Job.id == uuid.UUID(jid)))
                    .mappings()
                    .one()
                )
            assert before == after
            # More than one page exercises real server pagination, not mocked data.
            extra_jobs = FakeSource(
                [
                    [
                        RawJob(
                            external_id=f"pagination-{i}",
                            title=f"Software Engineer {i:02}",
                            description="Python developer",
                            location="Remote",
                            url=f"https://example.com/careers/pagination-{i}",
                        )
                        for i in range(22)
                    ]
                ]
            )
            with ThreadPoolExecutor(max_workers=1) as executor:
                result = executor.submit(
                    lambda: asyncio.run(run_source(SessionLocal, sid, adapter=extra_jobs))
                ).result()
                assert result.status == "success"
            page.goto("/jobs")
            expect(page.locator(".job-row")).to_have_count(20)
            page.get_by_role("link", name="Next", exact=True).click()
            page.wait_for_url("**page=2")
            assert len(a.request.get("/api/jobs?page=2").json()["items"]) == 3
            expect(page.locator(".job-row")).to_have_count(3, timeout=15000)
            assert "page=2" in page.url
            page.goto("/notifications")
            expect(page.locator(".notice-row")).to_have_count(20)
            page.get_by_role("link", name="Next", exact=True).click()
            expect(page.locator(".notice-row")).to_have_count(3, timeout=15000)
            page.get_by_role("button", name="Mark all read", exact=True).click()
            expect(
                page.get_by_role("status").filter(has_text="All notifications marked read.")
            ).to_be_visible()
            assert all(n["is_read"] for n in a.request.get("/api/notifications?limit=100").json())
            for i in range(21):
                response = a.request.post(
                    "/api/profiles", data={"name": f"Pagination profile {i:02}"}
                )
                assert response.status == 201
            page.goto("/profiles")
            expect(page.locator(".profile-row")).to_have_count(20)
            page.get_by_role("link", name="Next", exact=True).click()
            expect(page.locator(".profile-row")).to_have_count(3, timeout=15000)
            print(
                "PASS: 10 authenticated screens at 4 sizes; browser signup/login/logout; real jobs/notifications/profiles pagination; all 4 health states; profile CRUD and dialogs; company toggles; filter persistence; ignore/restore; monitoring -> match -> notification -> dashboard -> save -> apply; 2 profiles / 1 card; 2 user states; read independent of delivery; canonical unchanged; mobile layout"
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
