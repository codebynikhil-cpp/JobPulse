# JobPulse functional QA — 2026-10-04

The local product journeys passed after four functional fixes. This report records
actual Chromium, API, service and PostgreSQL checks; it does not certify live
production providers or unattended deployment.

## Environment and inspection

Inspected frontend routes/forms, FastAPI contracts and authentication, SQLAlchemy
models and migrations, monitoring/acquisition/normalization, matcher, notification
worker, existing tests, product decisions and architecture documentation before
changing code. The pre-existing frontend redesign was preserved.

Docker Compose ran PostgreSQL, FastAPI at localhost:8000 and the production Next.js
build at localhost:3000. Alembic reports 0010 (head) and no pending schema drift.
Required configuration was checked without exposing secrets. The local browser
provider is enabled; email defaults to disabled. Compose does not start monitoring
or notification workers automatically.

Running-stack fixtures use unique users, companies and sources, then remove only
their own records. The existing application database was not reset or truncated.
Regression tests create, migrate and remove a separate PostgreSQL database.

## Bugs reproduced and fixed

| Bug | Reproduction and resulting behavior |
| --- | --- |
| Mobile account overflow | A long email caused horizontal overflow at 390px. Account values now wrap; the loaded account screen fits the viewport. |
| Unsupported source reported healthy | A stored source with no registered production adapter appeared healthy before its first run. Health now checks actual registry capability. |
| Stale profile evidence and missed reevaluation | Editing a profile left old matches visible; unchanged jobs could skip matching for edited or newly subscribed profiles. Public queries now require current owned, active, subscribed evidence, and successful observations queue returned unchanged jobs when evaluation is missing or stale. Existing alert deduplication remains intact. |
| Disabled email falsely marked Sent | The disabled provider sent nothing but the worker stamped sent_at and exposed Sent. Suppressed delivery now becomes Cancelled with no sent timestamp, including through actual worker claiming and the browser notification row. |

No matching weights, schema, validation rules or production acquisition adapters
were relaxed. Regression assertions cover the corrected behavior.

## Coverage and evidence

| Area | Exercised behavior |
| --- | --- |
| Authentication | Browser signup, invalid email/weak password/duplicate validation, correct and incorrect login, nonexistent account, five failures followed by rate limiting, session reload/navigation, logout revocation, Origin enforcement, 12 protected routes and five protected API groups. |
| Profiles | Complete supported structured form, persisted create/edit, validation, activation, multiple independent profiles, foreign-user access, delete confirmation/cancel and removal. |
| Companies | Subscriptions, source health states, capability rejection and ownership; unsubscribing removes current match eligibility. |
| Acquisition | Real local HTTP and JavaScript browser sources through due-source scheduling, normalization and PostgreSQL; duplicate/new/changed/unchanged jobs, missing optional data, malformed payloads, source failure, atomicity, failure isolation, two successful missing observations before closure and reopening. |
| Matching | Exact role, seeded alias, required/preferred skills, excluded terms, location and experience evidence, hard filters, unknown data, explicit negative cases, expected scores and one job card for two matching profiles. Standalone matcher examples also exercise custom aliases. |
| Job state | Save/apply/ignore/restore, filtering and pagination, state persistence, independent users, unchanged canonical job data. |
| Notifications | Material-event deduplication, two-profile payload, owned access, transient retry, independent read state, scoped mock delivery and disabled cancellation. Disposable-database integration tests exercise claiming, leases and concurrency. |
| Browser regression | Ten authenticated screens at 390×844, 768×1024, 1280×800 and 1920×1080; landing CTA/FAQ, mobile navigation, dialogs/focus/Escape and no unhandled JavaScript errors. |

The original suite passed 404 tests before QA. The first browser regression found
the account overflow. After fixes, the original dashboard smoke journey passed,
and the expanded running-stack suite passed all 13 groups. Machine-readable final
results are in [qa-results.json](qa-results.json).

Final PostgreSQL regression result: **411 passed**, one existing deprecation
warning, in 73.44 seconds.

Screenshots: [dashboard](screenshots/qa-dashboard.png),
[mobile dashboard](screenshots/qa-dashboard-mobile.png),
[job detail](screenshots/qa-job-detail.png),
[mobile account](screenshots/qa-account-mobile.png),
[landing](screenshots/qa-landing.png),
[mobile landing](screenshots/qa-landing-mobile.png).

## Reproduction

Start the configured local stack with `docker compose up --build -d`. Run:

```powershell
docker compose exec -T backend pytest -q
docker compose cp scripts/qa_e2e.py backend:/tmp/qa_e2e.py
docker compose exec -T -e PYTHONPATH=/app:/ backend python /tmp/qa_e2e.py
docker compose cp scripts/smoke_dashboard.py backend:/tmp/smoke_dashboard.py
docker compose exec -T -e PYTHONPATH=/app backend python /tmp/smoke_dashboard.py
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
```

The extended suite uses a container-local TCP forwarder to preserve the actual
localhost browser origin. It does not intercept browser API responses. Fixture
HTTP/browser adapters are registered only for QA; failed-source logs are deliberate
failure-path evidence. Mock delivery is limited to fixture-owned notifications.

Backend Ruff checks, frontend lint/typecheck and the production frontend Docker
build passed. The regression suite emits one existing Starlette/httpx deprecation
warning.

## Remaining operational limits

- Chromium was exercised; cross-browser and assistive-technology certification
  remain outside this pass.
- Live Greenhouse traffic, Browserbase cloud acquisition and real Resend inbox
  delivery were not verified. The deterministic sources use real local networking
  and Chromium, with a scoped mock email provider.
- Production acquisition currently implements Greenhouse HTTP. Other stored
  platform classifications can be displayed but are unsupported for acquisition.
- Custom role aliases and per-profile notification preferences are not exposed
  by the current profile API. Unsupported fields are rejected; seeded aliases are
  exercised through the pipeline. Missing work-mode data remains unknown.
- Automatic monitoring and email delivery require explicitly supervised worker
  processes. The due-source pipeline and worker mechanics were exercised, but
  continuous production operation was not demonstrated. With email disabled,
  notifications remain visible and delivery is Cancelled.

These limits should be resolved according to deployment requirements before
calling the project production-complete.
