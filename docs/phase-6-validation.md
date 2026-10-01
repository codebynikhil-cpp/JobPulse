# Phase 6 verification

Verified 2026-10-01 on the final rebuilt Docker Compose PostgreSQL 17 stack.

| Command | Executed result |
| --- | --- |
| `docker compose up --build -d --wait --wait-timeout 120` | Exit 0; backend/frontend/PostgreSQL healthy; migration 0006 applied |
| `docker compose exec -T backend pytest -q` | **353 passed, 1 warning in 60.64s**: 274 stable baseline + 79 Phase 6 cases |
| `docker compose exec -T backend pytest -c /app/pyproject.toml -q /tests/integration/test_monitoring.py /tests/integration/test_career_browser.py /tests/integration/test_browser_providers.py` | **79 passed, 1 warning in 37.88s** |
| `docker compose exec -T backend pytest -c /app/pyproject.toml -q /tests/integration/test_ingestion.py /tests/integration/test_ingestion_safety.py` | **61 passed, 1 warning in 10.32s** |
| `docker compose exec -T backend alembic check` | No new upgrade operations detected |
| `docker compose exec -T backend alembic current` | `0006 (head)` |
| `docker compose exec -T backend python -m app.monitor --help` | Exit 0; run/due/worker/status/subscribe subcommands load |
| `uv run --project backend ruff check --config backend/pyproject.toml backend tests scripts` | All checks passed |
| `uv run --project backend ruff format --check --config backend/pyproject.toml backend tests scripts` | 79 files already formatted |
| `uv lock --project backend --check` | Exit 0; 53 packages resolved |
| `uv run --project backend pre-commit run --all-files` | Ruff check, Ruff format, frontend ESLint passed |
| `npm.cmd --prefix frontend run lint` | Exit 0 |
| `npm.cmd --prefix frontend run typecheck` | Exit 0 |
| `npm.cmd --prefix frontend run build` | Exit 0; compiled successfully in 2.4s |
| `python scripts/smoke_stack.py` | PASS: auth/pages/dashboard/session revocation |
| `python scripts/smoke_profiles.py` | PASS: CRUD/preferences/activation/owner isolation/pages/logout |
| `docker compose ps` | Three healthy services; PostgreSQL has no host port |
| `git diff --check` | Exit 0; Git line-ending notices only |

## Required monitoring acceptance

The five-job scenario with one subscribed active profile proves:

| Run | Created | Updated | Unchanged | Evaluated | Matched | Current match rows |
| --- | --- | --- | --- | --- | --- | --- |
| First | 5 | 0 | 0 | 5 | 5 | 5 |
| Identical repeat | 0 | 0 | 5 | 0 | 0 | 5 |
| One job loses required Python evidence | 0 | 1 | 4 | 1 | 0 | 5 (one now rejected) |

The identical repeat preserves row creation/update timestamps. The changed job
updates its existing row with the full rejected MatchResult and hard-filter
explanation. Current owner-scoped matches return four positives after that change.

The final 41 monitoring cases additionally cover:
- Active subscribed profiles only, unrelated-company exclusion, separate user ownership,
  idempotent subscription and profile deletion cascades.
- All five unsupported classifications remain persistable and never fetch; disabled
  companies/sources do not run; polling boundary/due recheck/manual override.
- Two clean absences close jobs; reappearance reopens with stable identity/counters.
- Fetch/normalization/duplicate failures do not close jobs, advance missing counters,
  or overwrite last successful source time.
- Zero/large-drop anomalies retain jobs and missing counters; first empty board is valid.
- Degraded/failing health escalation, auto-pause, explicit reactivation and recovery.
- Source timeout attribution and one bad source alongside a successful source.
- Matcher failure isolation, nullable unknown error state and pending retry that skips
  the successful profile's existing identical evaluation.
- Durable work after failure following ingestion commit; callback failure rolls back
  canonical jobs and matching work together.
- Shared lock busy behavior, actual concurrent async fetches execute only once,
  low-level manual ingestion respects the monitoring lock, cancellation releases it,
  and interrupted run records become abandoned on recovery.
- Bounded job/profile/source batches and stoppable worker cycles.
- Stale positive evidence hidden after profile edits; complete structured result JSON,
  persisted run counts/timing and emitted log source/error context.
- Migration 0005 downgrade/upgrade preserves baseline jobs/profiles/source records;
  existing migration-from-empty, earlier round trips and schema constraints still pass.

Greenhouse HTTP behavior remains mocked. Browser tests use real local Chromium
against deterministic fixture sites, with a test-only local-origin policy.
The worker, manual source run and due commands were not invoked against live career
sources. Tests use uniquely named disposable PostgreSQL databases; application data
is not truncated. The final focused/full suites have no failures. An intermediate migration test
incorrectly queried post-0006 ORM columns after downgrading to 0004; its identity
assertion now selects only the preserved ID column.
Routine lint found ambiguous local names/import ordering during implementation;
these were corrected before final verification.

The only test warning is the existing Starlette TestClient/httpx deprecation. No
remaining failing checks. The worker is available for explicit supervised startup;
profile/company subscriptions require the internal helper/CLI because no new UI or
API was added. The async timeout does not preempt synchronous DB/matcher execution.
Current match state is not a notification outbox; Phase 7 must implement that policy
separately. No notifications or Phase 7 implementation was started.

## Company career acquisition acceptance

The 79 focused cases comprise 41 monitoring, 27 real-browser/source/security/schema
cases, and 11 mocked Browserbase/provider cases. The mandatory two-company test uses
JavaScript-rendered Company A and structured HTTP Company B through the same
scheduler, ingestion, canonical Job and deterministic matcher pipeline:

| Run | Canonical jobs | Evaluations | Current match rows |
| --- | --- | --- | --- |
| First, two users/profiles subscribed to both companies | 4 | 8 | 8 positive |
| Identical repeat | 4 | 0 | Same 8 rows |
| One A job changes Python to Java | 4 | 2 | Same 8 rows, 2 now rejected |
| A partial extraction fails, B succeeds | 4 | 0 | Existing state preserved |

Pagination, load-more, JS/XHR, malformed/partial extraction, duplicate/conflicting
records, timeout, page failure, bounded pagination, URL/DNS guards, provider capacity,
cleanup/cancellation, source registry resolution and selected-company scheduling are
covered. Migration 0006 round trips preserve legacy HTTP configuration and metadata;
Alembic reports no drift. Backend runs as uid/gid 10001. All three Docker services
are healthy; PostgreSQL remains unexposed to the host.

Browserbase credentials are optional environment configuration. Its API/CDP lifecycle
is implemented and mock-tested, with a separate explicit live/paid probe script.
That script and live company/browser sources were not executed. No additional
production company adapter was introduced. Local fixtures explicitly disable Chromium
sandboxing in this restricted test container; production provider defaults retain
sandboxing and require appropriate public-network egress/container configuration.

Phase 7 proposal only: transactional notification intent/outbox, user/job alert
deduplication across matching profiles, email delivery with retries and an explicit
policy for materially changed jobs. None of this was implemented.
