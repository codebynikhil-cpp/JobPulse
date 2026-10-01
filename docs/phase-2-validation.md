# Phase 2 validation

Completed on 2026-10-01 from approved foundation commit 9e0d2d4.
Only user-owned profile configuration and its management UI were implemented.

## Commands and exact observed results

| Command | Result |
| --- | --- |
| `docker compose up --build -d --wait --wait-timeout 120` | Exit 0; PostgreSQL, backend and frontend healthy. Production Next.js build completed inside Docker. |
| `docker compose exec -T backend pytest -q` | Exit 0; **71 passed, 1 warning in 20.20s**: 16 foundation/auth tests + 55 profile tests. |
| `docker compose exec -T backend alembic check` | No new upgrade operations detected. |
| `docker compose exec -T backend alembic current` | `0003 (head)`. |
| `docker compose exec -T backend ruff check . /tests` | All checks passed. |
| `docker compose exec -T backend ruff format --check . /tests` | 26 files already formatted. |
| `uv run --project backend ruff check --config backend/pyproject.toml backend tests scripts` | All checks passed. |
| `uv run --project backend ruff format --check --config backend/pyproject.toml backend tests scripts` | Formatting passed (28 Python files, including smoke scripts). |
| `uv lock --project backend --check` | Resolved 50 packages; existing lock remains current. |
| `npm.cmd --prefix frontend run lint` | Exit 0, no warnings or errors. |
| `npm.cmd --prefix frontend run typecheck` | Exit 0. |
| `npm.cmd --prefix frontend run build` | Exit 0; compiled successfully in 4.0s, type/lint checks and route generation passed. |
| `uv run --project backend pre-commit run --all-files` | Ruff check, Ruff format and frontend ESLint passed. |
| `python scripts/smoke_stack.py` | Existing home/login/signup, dashboard, wrong-password/login/logout and revoked dashboard access checks passed. |
| `python scripts/smoke_profiles.py` | Profile pages/API proxy, create/detail/edit rendering, configuration replacement, activation/deactivation, validation, two-user isolation, delete and logout protection passed. |
| `docker compose ps` | Three healthy services; application ports remain localhost-only, PostgreSQL has no published port. |
| `git diff --cached --check` | No whitespace errors. |

## Backend coverage

Tests use a uniquely named disposable PostgreSQL database and apply all migrations
from empty. Coverage includes CRUD and multiple profiles; deterministic persisted
responses; merged PATCH validation; omitted-list preservation; replacement and clearing
of each child collection; required/preferred transitions; database uniqueness and
check constraints; direct database cascades for profile/user deletion; owner isolation
including child replacement and activation; missing/invalid IDs; session requirements;
origin protection; scoped normalized name uniqueness; concurrent duplicate creation;
concurrent partial updates preserving unrelated fields; empty and invalid values;
experience bounds/precision; supported preference enums and duplicate enum values;
null handling; normalized duplicate roles/skills/locations/exclusions; cross-list
conflicts; ownership-ID injection; activation/deactivation and pagination.

The migration round-trip test downgrades only the disposable database to 0002,
checks that the profile tables are gone and existing authentication still works,
then upgrades to head and verifies profile/auth access. Foundation migration files,
auth models/services and dependency locks are unchanged. The foundation table
inventory assertion was changed to a subset assertion because the schema now
contains profile tables; its existing auth constraints still run unchanged.

## Failures fixed

The initial full backend run had 12 failing comparisons caused by create responses
using insertion-order lists and unscaled decimals, while GET returned database order
and one-decimal values. The service now reloads persisted profiles after successful
create/update; the entire suite was rerun and passed. No failing tests were removed,
skipped or weakened to hide this issue. Additional tests then covered migration
round trips, concurrent partial updates and null characters rejected before PostgreSQL.

## Warnings and limits

One existing Starlette TestClient/httpx deprecation warning remains; it was not
suppressed. No functional failures observed in the final checks. Frontend validation
uses lint/typecheck/production builds and real HTTP/server-rendering smoke checks;
interactive browser automation was not run. HTTP smoke scripts create random local
accounts and delete the profile they create; pytest removes its isolated databases.
The stack remains running at http://localhost:3000.

## Exact proposed Phase 3 scope (not started)

Company, source-configuration and canonical Job persistence only, following the
spec's Phase 3 row: SQLAlchemy models, Pydantic data schemas, persistence services,
and Alembic migrations for companies, job_sources and jobs. Include foreign keys,
intentional cascade policies, timestamps, UNIQUE(source_id, external_job_id), and
the required jobs indexes on content_hash, (company_id, closed_at), and first_seen_at.
Verify persistence, unique violations, foreign-key behavior and migrations, and run
both existing phase suites and stack checks. Document schema and persistence contracts.
No adapters/fetching, scraping, normalization pipeline, scheduler/monitoring, matching,
notifications, email delivery, or new infrastructure. Begin only when instructed.
