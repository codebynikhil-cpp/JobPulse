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
