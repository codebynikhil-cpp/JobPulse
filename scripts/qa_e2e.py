"""Running Compose QA; isolated fixture records, real Chromium, API and PostgreSQL.
Run from repository root:
  docker compose cp scripts/qa_e2e.py backend:/tmp/qa_e2e.py
  docker compose exec -T -e PYTHONPATH=/app:/ backend python /tmp/qa_e2e.py
No production adapter is registered or live career/email service called.
"""

import asyncio
import json
import select as socket_select
import socket
import socketserver
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from sqlalchemy import delete, func, select

from app.db.session import SessionLocal
from app.models.auth import AuthSession, User
from app.models.catalog import Company, JobSource
from app.models.job import Job
from app.models.monitoring import JobMatch
from app.models.notification import Notification
from app.monitoring.runner import run_source
from app.monitoring.scheduler import run_due
from app.notifications.config import NotificationConfig
from app.notifications.provider import DisabledEmailProvider, MockEmailProvider
from app.notifications.worker import deliver_claimed_notification
from app.schemas.catalog import CompanyCreate, SourceCreate
from app.services import catalog
from app.sources.base import RawJob, SourceError
from app.sources.fake import FakeSource
from app.sources.registry import AdapterRegistry
from tests.integration.career_fixtures import career_sites, fixture_registry


# Forward raw local TCP to Next.js, preserving the genuine localhost Origin.
# Browser requests are never intercepted or fulfilled with fabricated responses.
class Forward(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.create_connection(("frontend", 3000), timeout=30) as upstream:
            sockets = [self.request, upstream]
            while True:
                ready, _, _ = socket_select.select(sockets, [], [], 30)
                if not ready:
                    return
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    (upstream if source is self.request else self.request).sendall(data)


class Proxy(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    token = uuid.uuid4().hex
    users, companies, results = [], [], []
    artifacts = Path("/tmp/jobpulse-qa")
    artifacts.mkdir(exist_ok=True)
    expect.set_options(timeout=15000)
    proxy = Proxy(("127.0.0.1", 3000), Forward)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    pool = ThreadPoolExecutor(max_workers=1)

    def async_call(coroutine):
        return pool.submit(lambda: asyncio.run(coroutine)).result()

    def check(name, fn):
        try:
            print("RUN:", name, flush=True)
            fn()
            results.append({"name": name, "status": "PASS"})
            print("PASS:", name, flush=True)
        except Exception as error:
            results.append({"name": name, "status": "FAIL", "error": str(error)})
            print("FAIL:", name, type(error).__name__, str(error)[:1200], flush=True)

    def api(context, method, path, data=None, status=200):
        response = getattr(context.request, method)(
            "http://localhost:8000/api/auth/me" if path == "/api/auth/me" else path,
            **({"data": data} if data is not None else {}),
        )
        assert response.status == status, (path, response.status, response.text())
        return response.json() if status != 204 else None

    def create_company(name, **source_fields):
        with SessionLocal.begin() as db:
            company = catalog.create_company(
                db,
                CompanyCreate(name=f"QA {name} {token[:8]}", slug=f"qa-{name}-{token}"),
            )
            companies.append(company.id)
            source = catalog.create_source(
                db,
                SourceCreate(
                    company_id=company.id,
                    source_type="greenhouse",
                    active=True,
                    career_url="https://example.com/careers/qa",
                    **source_fields,
                ),
            )
            return str(company.id), source.id

    def batch(source_id, jobs=None, error=None):
        return async_call(
            run_source(SessionLocal, source_id, adapter=FakeSource([jobs or []], error=error))
        )

    def current_jobs(context):
        return api(context, "get", "/api/jobs")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        a = browser.new_context(
            base_url="http://localhost:3000",
            timezone_id="Asia/Kolkata",
            extra_http_headers={"Origin": "http://localhost:3000"},
        )
        b = browser.new_context(
            base_url="http://localhost:3000",
            extra_http_headers={"Origin": "http://localhost:3000"},
        )
        anon = browser.new_context(
            base_url="http://localhost:3000",
            extra_http_headers={"Origin": "http://localhost:3000"},
        )
        page = a.new_page()
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        email = f"qa-primary-{token}@long-email-domain.example.com"
        password = "QA-Password123!"
        state = {}
        try:

            def public_pages():
                public = anon.new_page()
                public.on("pageerror", lambda error: page_errors.append(str(error)))
                for width, height in [(390, 844), (768, 1024), (1280, 800), (1920, 1080)]:
                    public.set_viewport_size({"width": width, "height": height})
                    public.goto("/")
                    expect(public.locator(".landing-hero h1")).to_be_visible()
                    assert public.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    disclosure = public.locator(".landing-faq details").first
                    disclosure.locator("summary").click()
                    expect(disclosure).to_have_attribute("open", "")
                    expect(disclosure.locator("p")).to_be_visible()
                    public.evaluate("window.scrollTo(0, 0)")
                    public.screenshot(path=str(artifacts / f"landing-{width}.png"), full_page=True)
                    public.get_by_role("link", name="Build your profile").click()
                    expect(
                        public.get_by_role("heading", name="Create your account", exact=True)
                    ).to_be_visible()
                    public.goto("/")
                    public.get_by_role("link", name="Log in", exact=True).click()
                    expect(
                        public.get_by_role("heading", name="Welcome back", exact=True)
                    ).to_be_visible()
                public.close()

            check("Landing navigation, CTA and FAQ at four viewport sizes", public_pages)

            def protected():
                p = anon.new_page()
                for route in [
                    "/dashboard",
                    "/jobs",
                    "/saved",
                    "/applied",
                    "/profiles",
                    "/profiles/new",
                    "/companies",
                    "/notifications",
                    "/account",
                    f"/jobs/{uuid.uuid4()}",
                    f"/profiles/{uuid.uuid4()}",
                    f"/profiles/{uuid.uuid4()}/edit",
                ]:
                    p.goto(route)
                    expect(
                        p.get_by_role("heading", name="Welcome back", exact=True)
                    ).to_be_visible()
                    assert "/login" in p.url
                p.close()
                for path in [
                    "/api/jobs",
                    "/api/dashboard",
                    "/api/profiles",
                    "/api/subscriptions",
                    "/api/notifications",
                ]:
                    api(anon, "get", path, status=401)

            check(
                "Every protected screen and major API rejects anonymous access",
                protected,
            )

            def auth():
                page.goto("/signup")
                page.get_by_label("Email", exact=True).fill("bad-email")
                page.get_by_label("Password", exact=True).fill(password)
                page.get_by_role("button", name="Sign up", exact=True).click()
                assert page.get_by_label("Email", exact=True).evaluate("el => !el.validity.valid")
                page.get_by_label("Email", exact=True).fill(email)
                page.get_by_label("Password", exact=True).fill("short")
                page.get_by_role("button", name="Sign up", exact=True).click()
                assert page.get_by_label("Password", exact=True).evaluate(
                    "el => !el.validity.valid"
                )
                for payload in [
                    {"email": "bad", "password": password},
                    {"email": email, "password": "short"},
                ]:
                    api(anon, "post", "/api/auth/signup", payload, 422)
                page.get_by_label("Password", exact=True).fill(password)
                with page.expect_response("**/api/auth/signup") as response:
                    page.get_by_role("button", name="Sign up", exact=True).click()
                assert response.value.status == 201
                uid = uuid.UUID(response.value.json()["id"])
                users.append(uid)
                state["owner"] = uid
                expect(page.get_by_role("heading", name="Dashboard", exact=True)).to_be_visible()
                cookie = next(c for c in a.cookies() if c["name"] == "jobpulse_session")
                assert cookie["httpOnly"] and cookie["sameSite"] == "Lax"
                with SessionLocal() as db:
                    assert db.get(User, uid).email == email
                    assert (
                        db.scalar(
                            select(func.count())
                            .select_from(AuthSession)
                            .where(AuthSession.user_id == uid)
                        )
                        == 1
                    )
                page.reload()
                expect(page.get_by_role("heading", name="Dashboard", exact=True)).to_be_visible()
                api(
                    anon,
                    "post",
                    "/api/auth/signup",
                    {"email": email, "password": password},
                    409,
                )
                other = api(
                    b,
                    "post",
                    "/api/auth/signup",
                    {"email": f"qa-other-{token}@example.com", "password": password},
                    201,
                )
                users.append(uuid.UUID(other["id"]))
                duplicate_page = anon.new_page()
                duplicate_page.goto("/signup")
                duplicate_page.get_by_label("Email", exact=True).fill(email)
                duplicate_page.get_by_label("Password", exact=True).fill(password)
                duplicate_page.get_by_role("button", name="Sign up", exact=True).click()
                expect(duplicate_page.locator(".error-state")).to_contain_text("already")
                duplicate_page.close()
                p = anon.new_page()
                p.goto("/login")
                p.get_by_label("Email", exact=True).fill(email)
                p.get_by_label("Password", exact=True).fill("IncorrectPassword123!")
                p.get_by_role("button", name="Log in", exact=True).click()
                expect(p.locator(".error-state")).to_contain_text("Invalid")
                api(
                    anon,
                    "post",
                    "/api/auth/login",
                    {"email": f"qa-missing-{token}@example.com", "password": password},
                    401,
                )
                # Separate identity exercises the full configured failure window.
                limited = f"qa-rate-{token}@example.com"
                for _ in range(5):
                    api(
                        anon,
                        "post",
                        "/api/auth/login",
                        {"email": limited, "password": password},
                        401,
                    )
                api(
                    anon,
                    "post",
                    "/api/auth/login",
                    {"email": limited, "password": password},
                    429,
                )
                p.get_by_label("Password", exact=True).fill(password)
                p.get_by_role("button", name="Log in", exact=True).click()
                expect(p.get_by_role("heading", name="Dashboard", exact=True)).to_be_visible()
                old = next(c["value"] for c in anon.cookies() if c["name"] == "jobpulse_session")
                p.locator(".user-trigger").click()
                p.get_by_role("menuitem", name="Log out", exact=True).click()
                expect(p.get_by_role("heading", name="Welcome back", exact=True)).to_be_visible()
                api(anon, "get", "/api/auth/me", status=401)
                revoked = pw.request.new_context(
                    base_url="http://backend:8000",
                    extra_http_headers={"Cookie": f"jobpulse_session={old}"},
                )
                try:
                    assert revoked.get("/api/auth/me").status == 401
                finally:
                    revoked.dispose()
                p.goto("/jobs")
                expect(p.get_by_role("heading", name="Welcome back", exact=True)).to_be_visible()
                p.close()
                response = a.request.post(
                    "/api/profiles",
                    data={"name": "Forbidden origin"},
                    headers={"Origin": "https://untrusted.example"},
                )
                assert response.status == 403

            check(
                "Browser signup/login/logout, persistence, validation, revocation, rate limit and Origin",
                auth,
            )

            def profiles():
                page.goto("/profiles/new")
                page.get_by_label("Name", exact=True).fill("Primary search")
                page.get_by_label("Active profile", exact=True).check()
                page.get_by_role("button", name="Create profile", exact=True).click()
                expect(page.locator(".error-state")).to_contain_text("at least one role")
                for label, value in [
                    ("Target roles", "Software Engineer"),
                    ("Required skills", "Python"),
                    ("Preferred skills", "SQL"),
                    ("Preferred locations", "India"),
                    ("Excluded locations", "London"),
                    ("Excluded keywords", "Senior"),
                    ("Excluded roles", "Recruiter"),
                ]:
                    field = page.get_by_role("textbox", name=label, exact=True)
                    field.fill(value)
                    field.press("Enter")
                page.get_by_label("Minimum experience (years)").fill("0")
                page.get_by_label("Maximum experience (years)").fill("4")
                page.get_by_label("Full Time", exact=True).check()
                page.get_by_label("Remote", exact=True).check()
                with page.expect_response("**/api/profiles") as response:
                    page.get_by_role("button", name="Create profile", exact=True).click()
                assert response.value.status == 201
                primary = response.value.json()
                state["primary"] = primary["id"]
                expect(
                    page.get_by_role("heading", name="Primary search", exact=True)
                ).to_be_visible()
                page.reload()
                assert api(a, "get", f"/api/profiles/{primary['id']}") == primary
                page.get_by_role("link", name="Edit profile", exact=True).click()
                expect(page.get_by_label("Maximum experience (years)")).to_have_value("4.0")
                page.get_by_label("Name", exact=True).fill("Primary updated")
                page.get_by_role("button", name="Save changes", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Primary updated", exact=True)
                ).to_be_visible()
                secondary = api(
                    a,
                    "post",
                    "/api/profiles",
                    {
                        "name": "Secondary search",
                        "active": True,
                        "roles": [{"name": "Software Engineer"}],
                        "skills": [{"name": "Python", "kind": "required"}],
                        "exp_max": 4,
                        "employment_types": ["full_time"],
                        "locations": [{"name": "London", "excluded": True}],
                        "exclusions": [{"term": "Senior", "kind": "keyword"}],
                    },
                    201,
                )
                state["secondary"] = secondary["id"]
                for data in [
                    {"name": "Primary updated"},
                    {"name": "Bad range", "exp_min": 5, "exp_max": 1},
                    {"name": "Alias not exposed", "aliases": ["Coder"]},
                    {"name": "Settings not exposed", "notify_frequency": "daily"},
                ]:
                    api(
                        a,
                        "post",
                        "/api/profiles",
                        data,
                        409 if data.get("name") == "Primary updated" else 422,
                    )
                api(b, "get", f"/api/profiles/{primary['id']}", status=404)
                api(
                    b,
                    "patch",
                    f"/api/profiles/{primary['id']}",
                    {"name": "Hijack"},
                    404,
                )
                api(b, "delete", f"/api/profiles/{primary['id']}", status=404)
                assert (
                    api(a, "get", f"/api/profiles/{secondary['id']}")["name"] == "Secondary search"
                )

            check(
                "Full profile form, persistence/edit, validation and cross-user isolation",
                profiles,
            )
            cid, sid = create_company("matches", config={"board_token": "qa-fixture"})
            state.update(cid=cid, sid=sid)
            api(a, "post", "/api/subscriptions", {"company_id": cid, "subscribed": True})
            api(
                b,
                "post",
                "/api/profiles",
                {
                    "name": "Other user",
                    "active": True,
                    "roles": [{"name": "Software Engineer"}],
                    "skills": [{"name": "Python", "kind": "required"}],
                },
                201,
            )
            # Only A subscribes; B has no right to source/job details.
            raw = [
                RawJob(
                    "full",
                    "Software Engineer",
                    "Python SQL; requires 2-3 years of experience",
                    "India",
                    "https://example.com/apply/full?utm_source=qa",
                    employment_type="full_time",
                ),
                RawJob(
                    "unknown",
                    "Software Engineer",
                    "Python",
                    "",
                    "https://example.com/apply/unknown",
                ),
                RawJob(
                    "negative",
                    "Recruiter",
                    "Hiring staff",
                    "India",
                    "https://example.com/apply/negative",
                ),
                RawJob(
                    "hard",
                    "Senior Software Engineer",
                    "Python SQL; requires 10 years of experience",
                    "India",
                    "https://example.com/apply/hard",
                ),
                RawJob(
                    "experience",
                    "Software Engineer",
                    "Python SQL; requires 8 years of experience",
                    "India",
                    "https://example.com/apply/experience",
                ),
                RawJob(
                    "employment",
                    "Software Engineer",
                    "Python SQL",
                    "India",
                    "https://example.com/apply/employment",
                    employment_type="contract",
                ),
                RawJob(
                    "location",
                    "Software Engineer",
                    "Python SQL",
                    "London",
                    "https://example.com/apply/location",
                ),
                RawJob("alias", "SDE", "Python", "", "https://example.com/apply/alias"),
            ]

            def discovery():
                result = batch(sid, raw)
                assert result.status == "success", result
                feed = current_jobs(a)
                assert feed["total"] == 3, feed
                full = next(item for item in feed["items"] if "/full" in item["application_url"])
                state["jid"] = full["id"]
                assert full["best_score"] == 100 and len(full["matched_profiles"]) == 2, full
                assert "utm_source" not in full["application_url"]
                unknown = next(
                    item for item in feed["items"] if "/unknown" in item["application_url"]
                )
                assert unknown["best_score"] == 60
                with SessionLocal() as db:
                    rows = list(db.scalars(select(Job).where(Job.source_id == sid)))
                    assert len(rows) == len(raw)
                    state["jobs"] = {j.external_job_id: j.id for j in rows}
                    matches = list(
                        db.scalars(
                            select(JobMatch).where(JobMatch.job_id == uuid.UUID(unknown["id"]))
                        )
                    )
                    for match in matches:
                        components = {c["name"]: c for c in match.evidence["components"]}
                        assert (
                            components["location"]["score"]
                            == components["experience"]["score"]
                            == 0
                        )
                    assert (
                        db.scalar(
                            select(func.count())
                            .select_from(Notification)
                            .where(Notification.user_id == state["owner"])
                        )
                        == 3
                    )
                    positive_notices = list(
                        db.scalars(
                            select(Notification).where(
                                Notification.user_id == state["owner"],
                                Notification.job_id == uuid.UUID(full["id"]),
                            )
                        )
                    )
                    assert len(positive_notices) == 1
                    assert len(positive_notices[0].payload["profiles"]) == 2
                    for identity in ["negative", "hard", "experience", "employment", "location"]:
                        rejected = list(
                            db.scalars(
                                select(JobMatch).where(JobMatch.job_id == state["jobs"][identity])
                            )
                        )
                        assert len(rejected) == 2
                        assert all(not match.matched and match.score == 0 for match in rejected)
                assert current_jobs(b)["total"] == 0
                for path in [
                    f"/api/jobs/{full['id']}",
                    f"/api/jobs/{full['id']}/status",
                ]:
                    api(b, "get", path, status=404)
                foreign_job = b.new_page()
                foreign_job.goto(f"/jobs/{full['id']}")
                expect(
                    foreign_job.get_by_role("heading", name="Job not found", exact=True)
                ).to_be_visible()
                foreign_job.close()
                other_company = next(
                    c for c in api(b, "get", "/api/subscriptions") if c["company_id"] == cid
                )
                assert other_company["source_id"] is None
                assert other_company["source_health"] is None
                assert other_company["last_checked_at"] is None
                api(
                    b,
                    "post",
                    "/api/subscriptions",
                    {"company_id": cid, "profile_id": state["primary"], "subscribed": True},
                    404,
                )
                api(b, "get", f"/api/sources/{sid}/health", status=403)
                api(
                    b,
                    "patch",
                    f"/api/jobs/{full['id']}/status",
                    {"status": "saved"},
                    404,
                )
                result = batch(sid, raw)
                assert result.created_count == result.updated_count == result.evaluated_count == 0
                assert result.unchanged_count == len(raw)
                page.goto("/jobs")
                expect(page.locator(".job-row")).to_have_count(3)
                expect(page.locator(".job-row").filter(has_text="Software Engineer")).to_have_count(
                    2
                )

            check(
                "Acquisition -> normalization -> canonical jobs -> matcher/outbox -> 1 card for 2 profiles",
                discovery,
            )

            def stale():
                api(a, "patch", f"/api/profiles/{state['secondary']}", {"active": False})
                api(
                    a,
                    "patch",
                    f"/api/profiles/{state['primary']}",
                    {"skills": [{"name": "Rust", "kind": "required"}]},
                )
                page.goto("/jobs")
                expect(page.locator(".job-row")).to_have_count(0)
                api(a, "get", f"/api/jobs/{state['jid']}", status=404)
                api(
                    a,
                    "patch",
                    f"/api/jobs/{state['jid']}/status",
                    {"status": "saved"},
                    404,
                )
                assert api(a, "get", "/api/dashboard")["stats"]["new_jobs_count"] == 0
                # An unchanged acquisition must still reevaluate changed profiles.
                result = batch(sid, raw)
                assert result.evaluated_count == len(raw)
                assert current_jobs(a)["total"] == 0

            check(
                "Profile edits invalidate old evidence and reevaluate unchanged jobs",
                stale,
            )
            # Restore through API, then acquire to resume the following independent checks.
            api(
                a,
                "patch",
                f"/api/profiles/{state['primary']}",
                {
                    "skills": [
                        {"name": "Python", "kind": "required"},
                        {"name": "SQL", "kind": "preferred"},
                    ]
                },
            )
            api(a, "patch", f"/api/profiles/{state['secondary']}", {"active": True})
            batch(sid, raw)

            def company_health():
                ucid, usid = create_company("unsupported", config={})
                with SessionLocal.begin() as db:
                    db.get(JobSource, usid).source_type = "workday"
                api(
                    a,
                    "post",
                    "/api/subscriptions",
                    {"company_id": ucid, "subscribed": True},
                )
                page.goto("/companies")
                row = page.locator(".company-row").filter(has_text=f"QA unsupported {token[:8]}")
                expect(row.get_by_text("Unsupported", exact=True)).to_be_visible()
                assert (
                    api(a, "get", f"/api/sources/{usid}/health")["health_status"] == "unsupported"
                )

            check(
                "Unsupported source capability is shown honestly before any run",
                company_health,
            )

            def account_layout():
                page.set_viewport_size({"width": 390, "height": 844})
                page.goto("/account")
                expect(page.get_by_role("heading", name="Account", exact=True)).to_be_visible()
                expect(page.locator(".account-section dd")).to_have_text(email)
                page.screenshot(path=str(artifacts / "account-mobile.png"), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                    page.evaluate(
                        "Array.from(document.querySelectorAll('*')).filter(el=>el.getBoundingClientRect().right>innerWidth).map(el=>({tag:el.tagName,class:el.className,width:el.getBoundingClientRect().width})).slice(-10)"
                    )
                )

            check("Long account email fits mobile viewport", account_layout)

            def failed_source():
                assert batch(sid, error=SourceError("QA source unavailable")).status == "failed"
                malformed = replace(raw[0], title="")
                assert batch(sid, [malformed]).status == "failed"
                with SessionLocal() as db:
                    assert {
                        j.id for j in db.scalars(select(Job).where(Job.source_id == sid))
                    } == set(state["jobs"].values())
                    assert all(
                        j.status == "open"
                        for j in db.scalars(select(Job).where(Job.source_id == sid))
                    )
                changed = [
                    replace(j, description=j.description + "; PostgreSQL")
                    if j.external_id == "full"
                    else j
                    for j in raw
                ]
                notices_before = len(api(a, "get", "/api/notifications"))
                result = batch(sid, changed)
                assert len(api(a, "get", "/api/notifications")) == notices_before + 1
                assert result.updated_count == 1 and result.created_count == 0
                with SessionLocal() as db:
                    assert db.get(Job, state["jobs"]["full"]).id == uuid.UUID(state["jid"])
                result = batch(sid, changed)
                assert result.updated_count == 0
                assert len(api(a, "get", "/api/notifications")) == notices_before + 1
                # Two clean observations close a missing row; errors never advance it.
                reduced = changed[:-1]
                assert batch(sid, reduced).closed_count == 0
                batch(sid, error=SourceError("QA missing observation failed"))
                assert batch(sid, reduced).closed_count == 1
                assert batch(sid, changed).status == "success"

            check(
                "Failure/malformed atomicity, changed/duplicate jobs, closure and reopening",
                failed_source,
            )

            def browser_http():
                generator = career_sites.__wrapped__()
                origin, _state_site = next(generator)
                try:
                    base = fixture_registry(origin)
                    registry = AdapterRegistry(
                        tuple(replace(r, key=f"{r.key}-{token}") for r in base.registrations)
                    )
                    source_ids = []
                    for registration, path in zip(
                        registry.registrations, ["/a/careers", "/b/jobs.json"], strict=True
                    ):
                        with SessionLocal.begin() as db:
                            c = catalog.create_company(
                                db,
                                CompanyCreate(
                                    name=f"QA {registration.key}",
                                    slug=f"qa-{registration.key}",
                                ),
                            )
                            companies.append(c.id)
                            source = catalog.create_source(
                                db,
                                SourceCreate(
                                    company_id=c.id,
                                    source_type="custom",
                                    acquisition_method=registration.acquisition_method,
                                    adapter_key=registration.key,
                                    career_url=origin + path,
                                    active=True,
                                ),
                            )
                            source_ids.append(source.id)
                        api(
                            a,
                            "post",
                            "/api/subscriptions",
                            {"company_id": str(c.id), "subscribed": True},
                        )
                    result = async_call(run_due(SessionLocal, registry=registry))
                    assert len(result) == 2 and all(r.status == "success" for r in result), result
                    assert sum(r.created_count for r in result) == 4
                    with SessionLocal.begin() as db:
                        for sid_ in source_ids:
                            db.get(JobSource, sid_).last_checked_at = None
                    repeat = async_call(run_due(SessionLocal, registry=registry))
                    assert sum(r.created_count for r in repeat) == 0
                    page.goto("/jobs")
                    expect(page.get_by_role("heading", name="Jobs", exact=True)).to_be_visible()
                    expect(page.locator(".job-row")).to_have_count(current_jobs(a)["total"])
                    with SessionLocal.begin() as db:
                        db.get(JobSource, source_ids[0]).config = {"mode": "partial"}
                        for sid_ in source_ids:
                            db.get(JobSource, sid_).last_checked_at = None
                    failed = async_call(run_due(SessionLocal, registry=registry))
                    assert {r.status for r in failed} == {"success", "failed"}
                finally:
                    generator.close()

            check(
                "Real local HTTP and JavaScript browser acquisition through scheduler and feed",
                browser_http,
            )

            def notifications():
                notices = api(a, "get", "/api/notifications")
                assert notices
                nid = notices[0]["id"]
                api(b, "get", f"/api/notifications/{nid}", status=404)
                api(b, "patch", f"/api/notifications/{nid}", {}, 404)
                # Scope deliveries to fixture rows; global claiming is separately tested
                # in pytest's disposable PostgreSQL DB, never alter real users' outbox.
                provider = MockEmailProvider()
                config = NotificationConfig(retry_base_seconds=1)
                for transient in [True, False]:
                    claim = uuid.uuid4()
                    with SessionLocal.begin() as db:
                        record = db.get(Notification, uuid.UUID(nid))
                        record.status = "processing"
                        record.claim_token = claim
                        record.lease_until = datetime.now(UTC) + timedelta(seconds=120)
                        record.attempts += 1
                        record.first_attempt_at = record.first_attempt_at or datetime.now(UTC)
                    if transient:
                        provider.fail_transient_attempts[email] = 1
                    status, _ = deliver_claimed_notification(
                        SessionLocal, uuid.UUID(nid), claim, provider, config
                    )
                    assert status == ("retried" if transient else "sent"), status
                assert len(provider.sent_messages) == 1
                disabled_id = next(n["id"] for n in notices if n["id"] != nid)
                claim = uuid.uuid4()
                with SessionLocal.begin() as db:
                    record = db.get(Notification, uuid.UUID(disabled_id))
                    record.status = "processing"
                    record.claim_token = claim
                    record.lease_until = datetime.now(UTC) + timedelta(seconds=120)
                    record.first_attempt_at = datetime.now(UTC)
                    record.attempts += 1
                disabled_status, _ = deliver_claimed_notification(
                    SessionLocal, uuid.UUID(disabled_id), claim, DisabledEmailProvider(), config
                )
                assert disabled_status == "cancelled", (
                    "Disabled delivery falsely reported",
                    disabled_status,
                )
                assert (
                    api(a, "get", f"/api/notifications/{disabled_id}")["delivery_status"]
                    == "cancelled"
                )
                page.set_viewport_size({"width": 1280, "height": 800})
                page.goto("/notifications")
                expect(
                    page.get_by_role("heading", name="Notifications", exact=True)
                ).to_be_visible()
                expect(page.get_by_text("Email: cancelled", exact=True)).to_be_visible()
                api(a, "patch", f"/api/notifications/{nid}", {})
                assert api(a, "get", f"/api/notifications/{nid}")["delivery_status"] == "sent"

            check(
                "Owned notifications and delivery retry preserve independent read-state",
                notifications,
            )

            def profile_delete():
                page.goto(f"/profiles/{state['secondary']}")
                page.get_by_role("button", name="Delete", exact=True).click()
                expect(page.get_by_role("dialog")).to_be_visible()
                page.keyboard.press("Escape")
                expect(page.get_by_role("dialog")).not_to_be_visible()
                assert (
                    api(a, "get", f"/api/profiles/{state['secondary']}")["name"]
                    == "Secondary search"
                )
                page.get_by_role("button", name="Delete", exact=True).click()
                page.get_by_role("button", name="Delete profile", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Job search profiles", exact=True)
                ).to_be_visible()
                api(a, "get", f"/api/profiles/{state['secondary']}", status=404)

            check(
                "Profile deletion confirmation/cancel and persisted removal",
                profile_delete,
            )
            check(
                "No unhandled browser JavaScript errors",
                lambda: (_ for _ in ()).throw(AssertionError(page_errors)) if page_errors else None,
            )
        finally:
            browser.close()
            with SessionLocal.begin() as db:
                db.execute(delete(User).where(User.id.in_(users)))
                db.execute(delete(Job).where(Job.company_id.in_(companies)))
                db.execute(delete(JobSource).where(JobSource.company_id.in_(companies)))
                db.execute(delete(Company).where(Company.id.in_(companies)))
            proxy.shutdown()
            proxy.server_close()
            pool.shutdown()
            (artifacts / "results.json").write_text(json.dumps(results, indent=2))
    failed = [r for r in results if r["status"] == "FAIL"]
    print(f"QA: {len(results) - len(failed)} passed, {len(failed)} failed", flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
