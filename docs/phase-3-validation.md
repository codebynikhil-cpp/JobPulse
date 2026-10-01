# Phase 3 verification

Verified on 2026-10-01 against PostgreSQL 17 in the Docker Compose stack.

| Command | Result |
| --- | --- |
| `docker compose up --build -d --wait --wait-timeout 120` | Exit 0; backend, frontend and PostgreSQL healthy |
| `docker compose exec -T backend pytest -q` | 127 passed, 1 warning in 22.17s (71 existing + 56 new tests) |
| `docker compose exec -T backend alembic check` | No new upgrade operations detected |
| `docker compose exec -T backend alembic current` | `0004 (head)` |
| `uv run --project backend ruff check --config backend/pyproject.toml backend tests scripts` | All checks passed |
| `uv run --project backend ruff format --check --config backend/pyproject.toml backend tests scripts` | 38 files already formatted |
| `uv lock --project backend --check` | Exit 0; 50 packages resolved |
| `npm.cmd --prefix frontend run lint` | Exit 0 |
| `npm.cmd --prefix frontend run typecheck` | Exit 0 |
| `npm.cmd --prefix frontend run build` | Exit 0; compiled successfully |
| `python scripts/smoke_stack.py` | PASS: auth, pages, protected dashboard, login/logout and revoked access |
| `python scripts/smoke_profiles.py` | PASS: profile pages/API, CRUD, configuration replacement, activation, validation, ownership and logout protection |
| `uv run --project backend pre-commit run --all-files` | Ruff check, Ruff format and frontend ESLint passed |
| `git diff --check` | Exit 0 |
| `docker compose ps` | All three services healthy; PostgreSQL has no host port |

Integration tests create an isolated database and apply every migration from empty.
They also downgrade to Phase 2 and upgrade again while preserving auth/profile data.
New tests cover all six persisted source classifications, schema and direct database
validation, source-scoped identity uniqueness, foreign keys, intentional deletion
restrictions, source/company consistency, canonical job persistence and transaction
rollback. No live career sites are contacted.

The sole pytest warning is the existing Starlette TestClient/httpx deprecation.
The final repeat of `docker compose exec -T backend pytest -q` also passed:
127 passed, 1 warning in 20.18s.
There were no failing checks. Browser interaction automation was not run; stack
smoke checks exercise HTTP responses and server-rendered auth/profile pages.

Phase 3 adds no HTTP endpoints, frontend functionality, adapters, fetching,
normalization, monitoring, matching or notifications. Stored source types classify
records; none imply integration availability. Phase 4 has not begun.
