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

