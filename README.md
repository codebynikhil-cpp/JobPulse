# JobPulse - Phases 1-3

Accounts, sessions, user-owned job-search profiles, and company/source/job persistence.

## Run locally

Install Docker Desktop with its Linux engine running. Copy `.env.example` to `.env`, replace the password placeholder with a random local password, and use the same password in `DATABASE_URL` (URL-encode special characters). Do not commit `.env`.

```sh
docker compose up --build -d
docker compose ps
```

Open http://localhost:3000. API docs: http://localhost:8000/docs. Backend health: `/api/health`. The Compose stack runs production-built Next.js; PostgreSQL has no host port. Backend and frontend ports bind only to localhost. All containers run as non-root users.

The local backend startup applies `alembic upgrade head` before serving. **Production should run migrations as a separate deployment step**, once, before starting application instances:

```sh
docker compose run --rm backend alembic upgrade head
```

Override the backend command in production to `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Supply secrets through the deployment environment, use a least-privilege application database role and a separate migration role, configure HTTPS and `COOKIE_SECURE=true`, and set `APP_ORIGIN` to the exact public origin.

## Auth

POST `/api/auth/signup` and `/api/auth/login`: JSON `email`, `password`. POST `/api/auth/logout`: revoke the current session. GET `/api/auth/me`: authenticated account. Mutation requests require an `Origin` header matching `APP_ORIGIN`; the frontend forwards it. Passwords are 12-128 characters. Email is NFKC-normalized, trimmed, lowercased, validated and stored under a unique constraint.

Session cookies are HttpOnly, SameSite=Lax, Path=/; HTTPS uses Secure and the `__Host-` prefix. Tokens have 256 random bits; only SHA-256 token digests are stored. Logging in rotates the presented session. Sessions last `SESSION_HOURS` (default 168); logout deletes the current one.

Rate limiting counts failed credential attempts (login failures and duplicate signups), per route and IP + normalized email, using fixed windows. Successful attempts do not increment the counter. Invalid request bodies are rejected by Pydantic before credential processing. Default: 5 failures per 900 seconds; the next attempt returns 429. Expired sessions and rate rows are deleted opportunistically during valid login/signup requests. No scheduler or background cleanup exists.

`TRUST_FORWARDED_FOR=false` uses the backend socket peer IP and ignores X-Forwarded-For. Through the frontend proxy, that peer is the frontend container, so users with the same email share its limit. To use original client IPs, explicitly enable the option only behind a trusted ingress that **overwrites** incoming X-Forwarded-For and blocks direct access to the backend. Both frontend and backend honor this setting. Never enable it for an untrusted proxy or expose the backend directly in that mode.

## Verify

```sh
docker compose exec backend pytest -q
docker compose exec backend ruff check . /tests
docker compose exec backend ruff format --check . /tests
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
uv run --project backend pre-commit install
uv run --project backend pre-commit run --all-files
python scripts/smoke_stack.py
```

Pytest creates a uniquely named disposable database, applies migrations from scratch, tests against real PostgreSQL, then drops only that test database. The local development DB role needs CREATEDB (the Docker bootstrap user has it). Tests never truncate the application database. Run pytest inside the backend container because PostgreSQL is not exposed on the host.

Python dependencies are locked in `backend/uv.lock` (`uv sync --frozen`); Node dependencies in `frontend/package-lock.json` (`npm ci`). For host backend development, set `DATABASE_URL` to a reachable development PostgreSQL, then run `uv sync --project backend`; run backend commands from `backend/`. No SQLite substitutes are used.

Stop with `docker compose down`; this preserves PostgreSQL data. See `docs/architecture.md`, `docs/product-decisions.md`, and `docs/phase-1-validation.md`.

## Manage profiles (Phase 2)

After login, open Dashboard > Manage profiles, or `/profiles`. Create separate searches
with target roles, required/preferred skills, preferred/excluded locations, exclusions,
experience bounds and employment/work-mode preferences. Use Add or Enter for each
individual chip. Save as an inactive draft or activate after adding a role. Edit,
activate/deactivate or delete from the list or details page; deletion asks for confirmation.

Migration 0003 adds only profile/configuration tables; Phase 1 authentication is unchanged.
Rebuild the same Compose stack to apply it locally. No new services or dependencies.

```sh
python scripts/smoke_profiles.py
```

All backend tests still run with the existing pytest command, including both phases
and an upgrade/downgrade round-trip in an isolated PostgreSQL database. See
`docs/api.md`, `docs/database.md` and `docs/phase-2-validation.md` for contracts and results.

## Company/source/job persistence (Phase 3)

Migration 0004 adds companies, job_sources and canonical jobs. Rebuild the same Compose
stack to apply it locally. No new frontend pages, endpoints, services or dependencies.
Internal persistence services flush writes; callers explicitly commit or roll back
transactions. See docs/api.md and docs/database.md for the data contracts.

Source classifications are exactly greenhouse, lever, ashby, workday, api and custom.
All six can be stored, but no adapters are implemented yet. Stored type and active
flags never claim monitoring support. Phase 4 will implement Greenhouse only.

The existing backend test command runs all three phase suites, including source-type
persistence, database uniqueness/foreign-key/check violations, deletion restrictions,
transaction rollback and migration round trips. Results are in docs/phase-3-validation.md.
