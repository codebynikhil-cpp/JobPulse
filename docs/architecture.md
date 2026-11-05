# Architecture

## Phase 1 implementation

A modular FastAPI monolith serves `/api/auth` with Pydantic v2 input/output schemas. Routes handle HTTP, origin checks, cookies and request context; the auth service handles credential verification, transactional persistence and throttling. SQLAlchemy 2.x models and sessions connect to PostgreSQL; Alembic owns schema creation.

The Next.js App Router shell contains login/signup forms and a placeholder dashboard. Browser mutations go through a narrow same-origin `/api/auth/[action]` proxy that forwards cookies and Origin, propagates Set-Cookie, and permits only signup, login and logout. The dashboard server component forwards cookies to `/api/auth/me` with caching disabled, redirects on 401 and displays an error on backend failures. It never relies solely on middleware.

Database tables: users, auth_sessions and auth_rate_limits. UUID keys; unique normalized emails and session digests; foreign-key cascade from users to sessions. Timestamped sessions expire without background processing. Session expiry and old rate windows are cleaned during login/signup. Database transaction advisory locks serialize each IP/email identity; upserts count failures safely across workers. Passwords and raw tokens are never returned or logged.

Docker Compose runs PostgreSQL, backend and frontend. Database readiness gates backend migration startup; backend health gates frontend startup. Persistent database storage is internal to Docker; application ports bind localhost. Python and Node dependencies use committed lock files. The local database role is deliberately privileged for migration and isolated test-database creation; production uses separate migration and runtime roles.

## Future interfaces (design only)

Later phases will implement `JobSource` adapters returning `RawJob`, a separate normalizer, and a standalone `Matcher` protocol returning scores and explanations. Monitoring will fetch, normalize, deduplicate, persist, match, then create matches and notifications transactionally; notification delivery follows separately. None of those modules, tables, workers or endpoints are implemented in Phase 1.

## Phase 2 implementation

Profiles are user-owned aggregates with four normalized child collections: roles,
skills (required/preferred), locations (preferred/excluded), and exclusions
(keyword/role). The FastAPI profile router uses a shared session dependency and
passes the authenticated user id to a profile service. All lookups constrain both
profile id and owner id; foreign-owned resources return 404. Write routes retain
the existing Origin protection. Body schemas reject ownership/child-id injection.

The service locks the parent row during mutations, validates the complete merged
state before touching collections, replaces only supplied lists, and commits all
changes together. It flushes orphan deletion before reinserting equivalent keys,
so changing a skill's kind is safe under uniqueness constraints. Failed validation
and conflicts leave the entire aggregate unchanged. Reloading committed profiles
makes create/update/read responses consistent with database decimals and list order.
Select-in loading bounds collection queries and avoids per-profile N+1 loads.

Next.js adds a session-protected /profiles section with list, create, details and
edit pages; each backend data request forwards cookies with caching disabled.
The same-origin profile proxy allows only the specified collection/detail methods,
validates path IDs, and forwards Origin/cookies. Client components handle chip entry,
preferences, busy/error states, activation and explicit deletion confirmation.
The dashboard links to profiles while retaining its existing server-side session gate.
Empty state, pagination, unavailable profile and global loading/error states are present.

See api.md and database.md for the implemented contracts. The existing three-service
Docker topology, authentication schema, dependency locks and infrastructure are unchanged.

## Phase 3 source classification and adapter availability

The future `job_sources.source_type` persistence contract supports exactly these
classifications: `greenhouse`, `lever`, `ashby`, `workday`, `api`, and `custom`.
Database and Pydantic validation enforce that set without consulting installed
adapters. Persistence must accept a valid type even when no adapter exists for it.

Source classification and adapter availability are separate concepts. A record with
`source_type = "workday"` identifies a Workday-classified source; it does not mean
that the application can fetch or monitor Workday. Future runtime capability checks
and any supported-integration labels must use adapter availability, never infer it
from the presence of a persisted type. The `api` and `custom` classifications likewise
do not authorize arbitrary fetching or imply a generic implemented adapter.

Phase 3 implements persistence only, with no adapters or provider-specific fetching
logic. Phase 4 implements the Greenhouse adapter only, plus FakeSource for tests.
The six-type persistence contract does not promise six supported integrations.
Phase 3 implements these source tables and validation rules. No adapters or
monitoring capabilities have been added.

## Phase 3 persistence implementation

The monolith now persists companies, job_sources and canonical jobs. Source type
and generic JSON configuration live on each source, not on the company, allowing
multiple independently classified sources per company. Source health defaults to
unknown; its counters/check timestamps and polling interval are stored metadata
only. Active/enabled flags express configuration intent and do not execute work.

SQLAlchemy models, Pydantic data contracts and internal catalog/job services implement
create/read persistence. Services validate source-company consistency and flush
without committing, so callers own transactions spanning companies, sources and jobs.
Failures propagate; the caller must roll back a failed transaction. Job identity is
UNIQUE(source_id, external_job_id); a composite foreign key also enforces that a job's
company is the source's company. Restrictive source/company deletion preserves jobs
until leaf records are explicitly removed; enable/active flags allow retention instead.

There are no new HTTP endpoints or frontend pages in this persistence phase. Catalog
services are trusted internal operations, not user-accessible administrative APIs.
Existing session-protected profile/auth flows are unchanged. All mutable tables share
one timestamp mixin, extracted without changing the Phase 2 schema. No infrastructure
or dependency additions. No fetching, adapters, normalizer, deduplication pipeline,
monitoring, matching or delivery modules have been implemented.

## Phase 4 source ingestion

`source_type="greenhouse"` is currently the only source type with an implemented
adapter. The six persisted classifications remain valid independently. The source
registry selects Greenhouse at invocation time; it does not alter persistence
validation. FakeSource implements the same interface only for deterministic tests.

The pipeline is `JobSourceAdapter.fetch_jobs -> list[RawJob] -> normalize_job ->
JobCreate -> upsert_job`. Adapters expose provider data without database access;
the provider-neutral normalizer handles text, URLs and hashing; PostgreSQL handles
identity and transactional writes. `health_check -> HealthResult` is available for
manual use, with no periodic checks. Greenhouse uses the public complete-board GET,
an injected async HTTP client, a fixed official host and validated board token.

`ingest_source` owns transactions via an injected session factory. Fetching and
validation precede writes. Source-row locking serializes persistence; runs older
than the latest completed check are rejected. Job insertion uses PostgreSQL
ON CONFLICT DO NOTHING against (source_id, external_job_id), followed by a locked
existing-row update when needed. IDs and first_seen_at survive repeats and changes.
Success metadata commits atomically with jobs; failures roll back job writes and
record checked/error timestamps separately before raising IngestionError with a
result. Missing jobs are retained; closure detection remains Phase 6.

IngestionResult reports fetched, normalized, created, updated, unchanged, failed
and duration. A failed run reports zero committed creations/updates; failed_count
counts the fetched batch (or one source failure if nothing was fetched). No durable
monitor-run tables, public endpoints, dashboard features or scheduler are added.

Manual live invocation: `docker compose exec -T backend python -m app.ingest SOURCE_UUID`.
The source and company must already exist, with config `{ "board_token": "..." }`.
This explicit command performs a network request; the ordinary suite does not.
Manual invocation is allowed regardless of active/enabled flags, which remain future
scheduling configuration. The caller is trusted internal tooling, not a public API.

## Phase 5 standalone matching

`app.matching` contains immutable inputs/results, a Matcher protocol, exact phrase
normalization, an optional small role seed, pure experience parsing and configurable
scoring. It accepts canonical materialized Job-like values without importing the
canonical schema/model or reading database state. MatchingProfile captures explicit
roles/aliases, required/preferred skills, locations, exclusions and preferences.
ScoringConfig owns defaults and is injected into DeterministicMatcher.

Flow: inputs -> hard-filter diagnostics -> experience/role/skill evidence -> six
component scores -> hard-failure zeroing -> configured threshold -> MatchResult.
Every awarded component carries evidence; uncertain and absent evidence remain
visible. The matcher does not integrate with ingestion or write matches. No new
routes, UI, schema, migrations, scheduler or notifications are introduced. See
[matching.md](matching.md) for precedence, hard requirements and unknown semantics.

## Phase 6 monitoring

An explicitly supervised `python -m app.monitor worker` process uses the same
backend image/database. The sequential loop queries a bounded due-source batch,
acquires a shared PostgreSQL advisory source lock, and calls the existing ingestion
service. Optional ingestion transaction hooks record clean observations, closure
counters and pending matching work atomically with canonical job writes.

`app.monitoring.evaluation` pages pending jobs and subscribed active profiles,
materializes profile preferences into the existing MatchingProfile, invokes the
unchanged Matcher, and upserts current JobMatch state. Transactions/savepoints
isolate failures; pending flags recover work after partial execution. MonitorRun
records durable run metadata and results; SourceMonitorState/JobMonitorState keep
absence/anomaly evidence separate from the canonical Job schema. Source locks also
cover the Phase 4 manual ingestion command.

Migration 0005 adds these tables and explicit ProfileCompany subscriptions. No
profile/company UI or HTTP monitoring endpoints. Trusted CLI subcommands provide
subscription configuration, one source run, due batch, worker and run inspection.
Owner-scoped current match reads are available internally for future consumers.
No notification rows/outbox/provider/scheduler microservice is introduced. See
[monitoring.md](monitoring.md) for recovery, eligibility, health and data semantics.

## Official company career sources and dual acquisition

The product monitors official company career sites selected by users. ATS/platform classification is an implementation detail of acquiring jobs from those company sites.

Migration 0006 adds source career_url/acquisition_method/adapter_key. Shared global
companies and canonical source-scoped jobs continue serving independently owned
profiles via ProfileCompany. Due selection now requires at least one active company
subscription. Runtime registry entries describe adapter/platform/acquisition capability;
Greenhouse/http remains the only production entry. The HTTP adapter is unchanged.

`BrowserSourceAdapter -> BrowserProvider -> isolated Playwright Page` is the browser
boundary. Company adapters implement readiness, extraction and navigation; optional
request observation is scoped to an adapter. LocalPlaywrightProvider and optional
BrowserbasePlaywrightProvider share page lifecycle/security controls. Both return
RawJob through the same ingestion/normalizer/upsert/Matcher pipeline; no matching
logic is introduced into acquisition. Real local JavaScript/HTTP fixtures verify
this pipeline for two companies and two users. No production browser company adapter
is introduced. See [company-career-sources.md](company-career-sources.md).

## Phase 7 Notification Architecture

Phase 7 implements transactional notification generation and decoupled email delivery:

```
Match evaluation
    ↓
Database transaction
    ├── update match state (job_matches)
    └── create notification outbox record (notifications)
                 ↓
            commit
                 ↓
          notification worker (database-backed, FOR UPDATE SKIP LOCKED)
                 ↓
            email provider (NotificationProvider -> EmailNotificationProvider)
                 ↓
        delivery/update status (sent, failed/retried, permanently_failed)
```

### 1. Transactional Outbox & Boundary
- Match state updates and outbox insertion occur in the same per-job database transaction.
- If evaluation succeeds, the match state and outbox record commit atomically.
- If evaluation fails or rolls back, neither match state nor notification record is partially persisted.
- No network/email delivery occurs within the matcher, adapter, or monitoring transaction.

### 2. User/Job Deduplication
- Multiple active profiles belonging to the same user that match the same job are aggregated into exactly ONE notification.
- Logical identity constraint: `UNIQUE(user_id, job_id, kind, revision)` on `notifications`.
- The notification payload aggregates all matching profiles with their individual match scores and explanation evidence.
- Different users matching the same job each receive their own independent notification.

### 3. Changed-Job Alert Policy
- Material change is defined by canonical fields: `title`, `description`, `location`, `employment_type`, `experience_text`, `min_exp_years`, `max_exp_years`, `application_url`.
- A SHA-256 fingerprint of canonical fields represents the job's material version.
- Policy behavior:
  - **Unchanged:** No notification (material hash matches prior notification).
  - **Changed but irrelevant:** 0 matching profiles; no notification.
  - **Changed and newly becomes relevant:** User was not previously matched; notifies candidate.
  - **Changed and remains relevant:** Evaluated against configured policy (`material`: notifies once per material revision; `newly_relevant`: suppresses notification for already-relevant users; `off`: disables changed-job alerts).
  - **Changed and no longer relevant:** Matches no profiles; no notification.

### 4. Worker Claiming and PostgreSQL Locking
- Worker queries due records (`(status IN ('pending', 'failed') AND available_at <= now) OR (status = 'processing' AND lease_until <= now)`) using `SELECT FOR UPDATE SKIP LOCKED`.
- Claiming atomically assigns a unique `claim_token`, sets `lease_until = now + lease_seconds`, sets `status = 'processing'`, and increments `attempts`.
- Two concurrent workers can never claim or deliver the same outbox record.
- Orphaned tasks (e.g. from crashed workers) are recovered after `lease_until` expires, subject to a bounded recovery window (`recovery_window_seconds`).

### 5. Email Provider Abstraction & Idempotency
- `NotificationProvider` -> `EmailNotificationProvider` abstraction decouples business logic from vendors.
- `ResendEmailProvider` integrates via HTTPS POST with bearer auth and passes `Idempotency-Key: jobpulse-<notification_id>`.
- `MockEmailProvider` and `DisabledEmailProvider` support deterministic test and headless operation.
- **Delivery Semantics:** Email delivery over distributed networks provides at-least-once delivery with provider-side deduplication. Because email providers generally do not guarantee absolute exactly-once delivery across network partitions and post-send crashes, stable idempotency keys minimize duplicate delivery risk while acknowledging standard SMTP/HTTP edge cases.

### 6. Retry Policy
- Differentiates transient errors (`RetryableDeliveryError`: timeouts, connection errors, HTTP 429, HTTP 5xx) from permanent failures (`PermanentDeliveryError`: invalid recipients, 401/403 auth errors, 400/422 malformed requests).
- Bounded exponential backoff: `delay = min(cap_seconds, base_seconds * 2^(attempts - 1))`.
- When `attempts >= max_attempts`, transitions to `permanently_failed` with the last recorded error.



## Phase 8: personal dashboard and ownership

The authenticated workspace contains Dashboard, Jobs, Saved, Applied,
Notifications, Profiles, Companies and Account. There is no admin role or admin
workspace. The original spec's administrative/debug endpoints do not apply to
this phase. Next.js proxies forward session cookies and origin; backend mutation
routes use the same origin validation as profile mutations.

Canonical `jobs` remain shared. `user_job_interactions` has a unique
`(user_id, job_id)` identity and saved/applied/ignored states. An absent row means
new; restore deletes only that user's row. Status updates never write canonical
jobs. Feed, detail and status access require an evaluated positive match through
an active profile owned by the authenticated user. A job appears once regardless
of how many profiles match; all matching profiles and persisted reason strings
are displayed. Deactivating a profile removes its matches from current feed
access; interaction history remains stored and counted in the overview.

`notifications.read_at` represents UI read state independently of email/outbox
status. Public serialization omits provider errors and internal payloads.
Notifications and delivery aggregates are owner scoped; read-all only updates
that user's unread rows. Application links come from the persisted application
URL. Read changes leave delivery state untouched.

ProfileCompany remains the subscription identity. Company discovery lists enabled
companies, with subscription status and official career URL. Subscribing without a
profile ID targets all active owned profiles; a specific profile must be owned.
Source IDs, health, check timestamps and acquisition metadata are returned only
for monitored companies. The health endpoint requires an active owned subscribed
profile. No canonical company/job editing API is added for ordinary users.

Source health uses current scheduler state, not historical last_error_at:
missing/inactive source, disabled company or unsupported status -> unsupported;
3+ consecutive failures or active failing state -> failing; 1-2 failures or
active degraded state (including acquisition anomalies) -> degraded; otherwise
healthy. A successful normal run resets active failures; old error timestamps
never permanently mark a source failing. Never-checked healthy sources still show
last checked/last success as unavailable, not an invented check time.

Jobs use SQL filtering for profile/company/location/open or closed status,
interaction status, score, employment type, title/description/company search and
first discovery timestamp. Pagination defaults to 20, capped at 100. A distinct
job query counts before LIMIT/OFFSET; matching profile data is fetched only for
that page. Ignored jobs are hidden by default. Saved/applied views include closed
jobs. Sort is posted/discovered timestamp then job ID. Notifications use bounded
limit/offset, sorted by creation time and ID. Indexes support user/status lookup,
user/read lookup and user/created_at/id notification ordering. No search engine.

Migrations 0008 and 0009 add interactions/read state and notification ordering.
0009 is separate because the inherited development database already had 0008.
Browser verification uses persisted FakeSource data and local Chromium; it does
not depend on Browserbase, live company access or an email provider.

Disabled companies remain visible to current subscribers as unsupported. For a
company with multiple sources, the company health card uses the most severe
source state (unsupported > failing > degraded > healthy), with source ID as a
deterministic tie-breaker. Its timestamps/method refer to that representative
source; the health API remains individually scoped by source ID. Migration 0010
repairs inherited development column drift to Phase 7's Text contract without
truncating stored errors.


## Approved frontend redesign

Authenticated routes now live under the `(app)` route group without changing
public URLs. Its server layout validates the session and supplies the shared
sidebar/header with account identity and unread notification count. Pages fetch
owner-scoped backend data on the server; interactivity is confined to action,
dialog, navigation and form components. Backend authorization remains authoritative.

`components/ui` owns design primitives, status/score badges, pagination,
loading/empty/error states, Radix confirmation dialogs and accessible toast feedback.
`components/layout` owns the responsive shell. Domain folders contain reusable job
rows/actions/filter controls, dashboard sections, company subscription controls,
profile sections and notification rows. Dashboard and Jobs share the same job UI.

`lib/product-api.ts` handles typed server reads and complete profile option loading;
`lib/client-api.ts` centralizes browser mutations, session expiry and backend errors.
Existing same-origin proxies retain cookie forwarding, Origin enforcement and auth
Set-Cookie behavior. No backend routes, matching logic, schema or migration changes.

Job filters and pagination are URL driven. Backend pagination retains newest-first
ordering; score/company ordering applies explicitly within the current page.
Notifications use one lookahead row for pagination and existing read/unread filters.
Company health is shown only when monitored; `failing` is labelled Issue, and raw
errors/acquisition internals are omitted. Existing subscribed-profile IDs support
per-profile controls for active profiles. Application links never implicitly mark
a job applied. External descriptions are rendered as text, never unsafe HTML.

Authenticated data links disable speculative prefetch, avoiding unnecessary
owner-scoped queries. Query-only pagination, filter reset and notification tabs
use document navigation, consistent with GET filter forms; this prevents stale
query views after form submission/reload in the current Next.js runtime.


### Bauhaus presentation layer

The full app uses shared Bauhaus tokens in `app/globals.css` and Outfit loaded in
`app/layout.tsx` with next/font. `components/ui/geometry.tsx` owns the decorative
three-shape brand and abstract composition, shared across public/auth/workspace
branding. The landing page composes product steps, benefits and native FAQ
disclosures; it does not fetch or fabricate product data. Existing domain
components inherit the updated presentation without changing their server reads,
client mutations, API contracts or authorization boundaries.


### Functional QA corrections

`services/current_matches.py` centralizes public match visibility for feed/detail,
interaction authorization, dashboard opportunity counts and company match counts.
It checks current job/profile evidence and subscription ownership before pagination
or actions. Observation processing queues returned unchanged open jobs for new or
updated active subscriptions; cache reuse also requires a current profile timestamp.
Source-health projection resolves actual production registry capability. These
corrections add no schema, matching weights or production adapters.

The disabled email provider returns cancelled. The notification worker persists
that terminal state without a sent timestamp, counts cancellations separately,
and rejects unsupported provider result statuses.

`scripts/qa_e2e.py` verifies the running Compose stack with scoped fixtures, Chromium
forms and real local HTTP/JavaScript acquisition. Its container-local TCP forwarder
preserves the browser localhost origin; UI API responses are not intercepted.
`docs/functional-qa.md` records evidence, commands and remaining deployment limits.


## Phase 9 — Multi-company career integrations (Lever & Ashby)

The career adapter architecture is built on the `JobSourceAdapter` abstract protocol and resolved through `AdapterRegistry`. In Phase 9, production-ready adapters for Lever and Ashby join Greenhouse:

1. **Lever Adapter (`app/sources/lever.py`):**
   - Targets the official public postings endpoint: `GET https://api.lever.co/v0/postings/{site}?mode=json`.
   - Enforces DNS SSRF verification (`verify_public_host`) restricting resolution to global public IPs.
   - Normalizes raw commitment strings into canonical schema values (`full_time`, `part_time`, `contract`, `internship`, `temporary`).
   - Reconstructs multi-part job descriptions from body, categorized lists, and additional markdown/HTML.
   - Parses millisecond timestamps into UTC datetimes.
   - Enforces a 20 MB response size cap and exponential backoff retry for transient 429/5xx errors.

2. **Ashby Adapter (`app/sources/ashby.py`):**
   - Targets the official public board endpoint: `GET https://api.ashbyhq.com/posting-api/job-board/{board_name}`.
   - Enforces DNS SSRF verification against non-public addresses.
   - Skips unlisted postings (`isListed is False`).
   - Normalizes employment types and extracts primary/secondary locations with fallback to Remote.
   - Parses ISO-8601 published timestamps.
   - Handles rate limits and response caps identically to Greenhouse and Lever.

3. **Registry Compatibility:**
   `AVAILABLE_ADAPTERS` in `app/sources/registry.py` explicitly registers `SourceType.GREENHOUSE`, `SourceType.LEVER`, and `SourceType.ASHBY`. Non-registered catalog types (`workday`, `custom`, `api`) remain valid database classifications but raise explicit `SourceError` on attempted acquisition.


## Phase 10 — Reliable background worker & scheduler

1. **Unified Background Worker (`app/worker.py`):**
   - Concurrently executes the monitoring scheduler loop and the notification outbox delivery loop in a single supervised process via `asyncio.gather`.
   - Attaches signal handlers for `SIGINT` and `SIGTERM` across Unix and Windows environments, setting a cooperative `stop_event` that allows in-flight HTTP requests and database transactions to commit cleanly before exit.
   - Employs fault isolation: an exception querying or executing one source never crashes the worker or blocks other due sources.
   - Recovers automatically from transient PostgreSQL disconnections.

2. **Structured Logging:**
   - Both `app.monitor` and `app.monitoring.runner` emit structured JSON log records with `source_id`, `company_name`, `adapter_key`, `acquisition_method`, `created_count`, `updated_count`, `unchanged_count`, `failed_count`, `duration_seconds`, and full tracebacks on failures.


## Phase 11 — Notification delivery & Resend verification

- **Transactional Outbox Claiming:** Uses PostgreSQL row-level locks via `SELECT ... FOR UPDATE SKIP LOCKED` to prevent duplicate deliveries across worker replicas.
- **Orphaned Lease Recovery:** If a worker crashes mid-delivery, the notification's lease expires (`lease_until <= now`), allowing subsequent worker iterations to reclaim and re-drive delivery.
- **Resend Verification Script (`scripts/verify_resend.py`):** Provides a production validation tool for testing live email delivery via the Resend API when credentials are provided, or skipping gracefully with actionable configuration instructions when omitted.


## Phase 15 — End-to-end acceptance testing

A 14-step automated acceptance test (`tests/integration/test_e2e_acceptance.py`) validates the complete user journey:
1. User registration (`POST /api/auth/signup`)
2. Session establishment (`GET /api/auth/me`)
3. Target profile configuration (`POST /api/profiles`)
4. Company subscription management across Lever and Ashby (`POST /api/subscriptions/toggle`)
5. Monitoring execution with isolated mock adapters (`run_source`)
6. Ingestion through Lever and Ashby adapters
7. Ingestion deduplication on repeated runs
8. Deterministic profile matching
9. Match score and evidence recording (`JobFeedItem.best_score`)
10. Notification generation for relevant opportunities
11. Delivery processing via `NotificationWorker`
12. Delivery state transitions (`pending` -> `sent`)
13. User job interactions (`saved`, `applied`, `ignored` via `POST /api/jobs/{id}/status`)
14. Real-time company health verification (`GET /api/subscriptions`, `GET /api/sources/{id}/health`)
