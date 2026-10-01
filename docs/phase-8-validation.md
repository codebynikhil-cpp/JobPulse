# Phase 8 validation ? 1 October 2026

Phase 8 completes the personal user dashboard on top of the approved Phase 7
commit ff3fc1fc3845dbe2c8e09391a8de5f16e48d9869. Existing partial work from the
other IDE was retained, completed and verified. No Phase 9 implementation.

## Files changed

See [phase-8-files.md](phase-8-files.md) for the exact repository-relative list.
Backend changes cover dashboard/feed/subscriptions services and APIs, interaction
and notification read schemas/models, migrations, public notification projections
and owner-scoped notification metrics. Frontend changes add eight account pages,
job detail, proxies, shared controls and responsive styles. Tests, architecture,
product decisions, spec refinement and a repeatable browser smoke script are included.

## Schema changes

- 0008: user_job_interactions, unique user/job, saved/applied/ignored constraint,
  applied timestamp, notes, timestamps and user/status index; notifications.read_at
  plus user/read index. No canonical Job columns changed.
- 0009: notifications(user_id, created_at, id) index for paginated owner feeds.
  Kept separate because the inherited development database had already applied 0008.
- 0010: repairs inherited local last_error VARCHAR(100) drift to Phase 7's declared
  TEXT type. This widens storage; downgrade retains TEXT to avoid truncation.

## APIs

| Method | Path | Behavior |
| --- | --- | --- |
| GET | /api/dashboard | Owned aggregates, five recent jobs and notifications, monitored health |
| GET | /api/jobs | SQL-filtered paginated current matched jobs |
| GET | /api/jobs/{id} | Owned match explanations and detail |
| GET | /api/jobs/{id}/status | Owned interaction, absent row means new |
| POST/PATCH | /api/jobs/{id}/status | Save, applied, ignore, restore |
| GET | /api/notifications | Existing bounded feed extended with read filter and safe display fields |
| GET | /api/notifications/{id} | Owned notification |
| POST/PATCH | /api/notifications/{id}/read | Idempotent read timestamp |
| POST/PATCH | /api/notifications/read-all | Mark only owned unread notifications |
| GET | /api/notifications/metrics | Existing route now owner scoped; provider error omitted |
| GET | /api/subscriptions | Company discovery and owned monitoring state; health withheld if unsubscribed |
| POST | /api/subscriptions/toggle | Set monitoring across active owned profiles, or one specified profile |
| PATCH | /api/subscriptions/{company_id} | Set company subscription |
| GET | /api/sources/{id}/health | Only actively subscribed owner can access |

Next.js proxies provide the UI paths. Mutation routes enforce the existing
configured-origin check. No ordinary-user canonical job/company mutation API.

## Dashboard and feed

Navigation: Dashboard, Jobs, Saved, Applied, Notifications, Profiles, Companies,
Account, plus job detail. Overview links actionable active-profile/company,
new/saved/applied/ignored-job and unread-notification counts to their pages.
Recent jobs/notifications and monitored source health are visible.

Feed filters: profile, company, location, canonical status, personal status,
minimum score, employment type, title/description/company keyword and discovery
cutoff. SQL count/LIMIT/OFFSET, default 20 and maximum 100 rows. One job card
aggregates all current positive owned profile matches. Explanations come from
persisted Phase 5 reasons. Missing experience/employment/posted data is omitted;
actual discovery timestamp is shown. Saved/applied include closed jobs. Ignored
jobs are hidden from default feed and accessible with their explicit filter.

Loading, empty, error/retry, success and pagination states are present. Official
career and application URLs open externally only for HTTP(S) URLs; job HTML is
rendered as escaped text. Normal development requires persisted data, not live
Browserbase access.

## Interaction and notification models

Canonical Job is shared; one user's interaction never writes it. No interaction
row means new. Saved/applied/ignored are durable owned rows, and restore deletes
only that owned row. Two users can independently save/apply the same canonical job.

UI read/unread is derived exclusively from read_at. Email delivery remains its
own lifecycle, unchanged by read actions. Notification public output excludes
internal payloads and provider errors. Notifications display kind, company/title,
time, score, matching profiles, delivery status and application/job links.

## Source health and subscriptions

Missing/inactive source, disabled company or unsupported source -> unsupported.
Three or more consecutive failures or current failing state -> failing. One or
two failures or current degraded/anomaly state -> degraded. Otherwise healthy.
Historical last_error_at does not override recovered state. Never-checked sources
show unavailable timestamps. Disabled companies remain visible to subscribers.
Multiple-source company cards use the worst state, with deterministic source ID
tie-breaking; timestamps and method belong to that representative source.

Company catalog discovery is shared. Source health/IDs/check timestamps/methods
are withheld for unsubscribed companies. Explicit source-health access requires
an active owned subscribed profile. Subscription changes may target only an
owned profile; otherwise they target all active owned profiles.

## Authorization

Feed/detail/status require a positive evaluated current match through an active
owned profile. Unknown or unmatched jobs return 404 even for status mutations.
Notifications and read changes are scoped by user ID. Profile/company subscription
ownership is validated. Notification metrics no longer aggregate other users.
Deactivated profile matches leave the current feed; historical interaction rows
remain stored and counted on the overview.

## Verification

- Complete regression: **404 passed, 0 failed in 82.18 seconds**, including **27 Phase 8 tests**.
- Phase 8 focused run: **27 passed, 377 deselected, 0 failed**.
- Backend Ruff lint and formatting checks passed.
- Frontend ESLint, TypeScript and production build passed.
- Pre-commit: **3 hooks passed** (Ruff check, Ruff format, frontend ESLint).
- Fresh test databases migrated through head; running database upgraded to 0010.
  Alembic check: no new upgrade operations detected.
- Docker backend/frontend builds passed; PostgreSQL/backend/frontend healthy.
- Existing stack authentication smoke and profile smoke passed.
- Real Chromium smoke passed across **9 authenticated pages**, desktop and
  390 x 844 mobile: FakeSource -> canonical job -> current matches -> notification
  -> dashboard -> saved -> applied; two profiles produced one card; two users
  kept independent states; read did not change delivery; canonical row unchanged.
- Browser smoke creates and removes its own fixture users/company/source/jobs.
  Internal Compose browser API requests use the configured public Origin header.
- [Query plans](phase8-query-plans.txt) inspect representative bounded notification
  and matched-job queries. The fixture is small; these are not production-scale
  performance measurements.
- [Dashboard screenshot](screenshots/phase8-dashboard.png) and
  [mobile screenshot](screenshots/phase8-mobile.png) were visually reviewed.

## Warnings and limitations

One existing Starlette/httpx TestClient deprecation warning remains. No live
Browserbase, real-company integration or email-provider send was required/run.
Ordinary regression tests use fixtures. The unrelated live integrations remain
separate. No backend static typechecker is configured; typecheck refers to the
frontend TypeScript check. Subscription discovery loads the small company catalog;
job, notification and match collections remain bounded on user pages.

## Commit and proposed Phase 9

The final Phase 8 commit hash is reported in the completion message and can be
retrieved with `git log -1 --format=%H`. The report is included in that commit.

Proposed Phase 9: add Lever and Ashby company-career adapters behind the existing
registry and acquisition contract, with deterministic recorded contract fixtures,
normalization/idempotency, monitoring/notification regressions and documented source
access/support limits. Keep Workday optional after feasibility review. Do not start
Phase 9 until explicitly requested.
