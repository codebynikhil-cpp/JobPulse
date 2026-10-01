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
