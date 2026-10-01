# Phase 4 verification

Verified 2026-10-01 using the Docker Compose PostgreSQL 17 stack.

| Command | Exact result |
| --- | --- |
| `docker compose up --build -d --wait --wait-timeout 120` | Exit 0; backend, frontend and PostgreSQL healthy |
| `docker compose exec -T backend pytest -q` | **188 passed, 1 warning in 24.69s**; 127 existing + 61 Phase 4 tests |
| `docker compose exec -T backend pytest -c /app/pyproject.toml -q /tests/integration/test_ingestion.py /tests/integration/test_ingestion_safety.py` | Earlier focused run: 58 passed, 1 warning in 4.53s, before the final two safety tests were added |
| `docker compose exec -T backend alembic check` | No new upgrade operations detected |
| `docker compose exec -T backend alembic current` | `0004 (head)`; no Phase 4 migration required |
| `uv run --project backend ruff check --config backend/pyproject.toml backend tests scripts` | All checks passed |
| `uv run --project backend ruff format --check --config backend/pyproject.toml backend tests scripts` | 50 files already formatted |
| `uv lock --project backend --check` | Exit 0; 50 packages resolved |
| `npm.cmd --prefix frontend run lint` | Exit 0 |
| `npm.cmd --prefix frontend run typecheck` | Exit 0 |
| `npm.cmd --prefix frontend run build` | Exit 0; compiled successfully in 2.2s |
| `uv run --project backend pre-commit run --all-files` | Ruff check, Ruff format and frontend ESLint passed |
| `python scripts/smoke_stack.py` | PASS: auth/pages, server-protected dashboard, login/logout and revoked access |
| `python scripts/smoke_profiles.py` | PASS: profile pages/API, CRUD, configuration replacement, activation, validation, ownership and logout protection |
| `docker compose exec -T backend python -m app.ingest --help` | Exit 0; manual CLI loads and displays source UUID argument |
| `git diff --check` | Exit 0 |
| `docker compose ps` | Three healthy non-root services; PostgreSQL has no host port |

The mandatory `test_mandatory_fake_source_three_run_acceptance` executed in both the
focused and full suites. Its five-job fixture asserts:

| Run | Created | Updated | Unchanged | Total rows |
| --- | --- | --- | --- | --- |
| First | 5 | 0 | 0 | 5 |
| Identical repeat | 0 | 0 | 5 | 5 |
| One changed title | 0 | 1 | 4 | 5 |

All UUIDs and first_seen_at values remain stable. Tests additionally cover mock
Greenhouse-to-database ingestion, request construction, complete-board behavior,
transient retries, non-retried 4xx/redirects, retry guidance, malformed/incomplete
payloads, response limits, DNS address rejection, normalization/null fields,
deterministic hashes, distinct-source identities, atomic rollback, stale-run
rejection, concurrent upserts and reopening returned jobs. Existing constraint and
migration-from-empty tests still execute against an isolated disposable database.

An early test invocation ran before the rebuilt container was ready and found no
new test file. Another targeted invocation omitted the backend pytest config and
failed collection (plus cache permission warnings). Waiting for the build and
selecting `-c /app/pyproject.toml` fixed the invocation; these errors were not
suppressed. Default full-suite invocation selects the config automatically.

The final suite has only the existing Starlette TestClient/httpx deprecation warning.
No live Greenhouse job-board request or live integration test was executed. Official
documentation was retrieved separately to verify the contract. All adapter HTTP and
DNS behavior in tests is mocked; fixtures are synthetic, not claimed as live captures.
Browser interaction automation was not run; stack checks use HTTP/server rendering.

Phase 5 has not begun. Proposed scope: standalone DB/network-free Matcher interface,
hard filters, configurable soft scoring with reasons for every score, role aliases,
and a pure experience parser with at least 30 realistic cases. Unknown experience
is a soft penalty. No scheduler, matching orchestration or notifications in that phase.
