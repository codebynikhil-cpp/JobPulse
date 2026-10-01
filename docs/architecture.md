# Architecture

## Phase 1 implementation

A modular FastAPI monolith serves `/api/auth` with Pydantic v2 input/output schemas. Routes handle HTTP, origin checks, cookies and request context; the auth service handles credential verification, transactional persistence and throttling. SQLAlchemy 2.x models and sessions connect to PostgreSQL; Alembic owns schema creation.

The Next.js App Router shell contains login/signup forms and a placeholder dashboard. Browser mutations go through a narrow same-origin `/api/auth/[action]` proxy that forwards cookies and Origin, propagates Set-Cookie, and permits only signup, login and logout. The dashboard server component forwards cookies to `/api/auth/me` with caching disabled, redirects on 401 and displays an error on backend failures. It never relies solely on middleware.

Database tables: users, auth_sessions and auth_rate_limits. UUID keys; unique normalized emails and session digests; foreign-key cascade from users to sessions. Timestamped sessions expire without background processing. Session expiry and old rate windows are cleaned during login/signup. Database transaction advisory locks serialize each IP/email identity; upserts count failures safely across workers. Passwords and raw tokens are never returned or logged.

Docker Compose runs PostgreSQL, backend and frontend. Database readiness gates backend migration startup; backend health gates frontend startup. Persistent database storage is internal to Docker; application ports bind localhost. Python and Node dependencies use committed lock files. The local database role is deliberately privileged for migration and isolated test-database creation; production uses separate migration and runtime roles.

## Future interfaces (design only)

Later phases will implement `JobSource` adapters returning `RawJob`, a separate normalizer, and a standalone `Matcher` protocol returning scores and explanations. Monitoring will fetch, normalize, deduplicate, persist, match, then create matches and notifications transactionally; notification delivery follows separately. None of those modules, tables, workers or endpoints are implemented in Phase 1.
