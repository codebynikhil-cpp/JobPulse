# Phase 6 files

New:
- `backend/alembic/versions/0005_monitoring.py`: subscriptions, durable run/current
  match state, clean-board baseline, missing counters and recoverable matching work.
- `backend/app/models/monitoring.py`: matching ORM models and constraints.
- `backend/app/services/source_lock.py`: shared advisory source lock lifecycle.
- `backend/app/monitoring/__init__.py`: orchestration package boundary.
- `backend/app/monitoring/config.py`: worker limits and health/anomaly policy.
- `backend/app/monitoring/subscriptions.py`: ownership-checked company selection.
- `backend/app/monitoring/observations.py`: transactional enqueue/absence/anomaly/closure.
- `backend/app/monitoring/evaluation.py`: bounded profile/job pages, matcher input
  materialization, failure isolation, idempotent current state and owner-scoped reads.
- `backend/app/monitoring/runner.py`: source orchestration and structured durable result.
- `backend/app/monitoring/scheduler.py`: due selection, bounded cycles, sequential worker.
- `backend/app/monitor.py`: manual/due/worker/status/subscription CLI with JSON logging.
- `tests/integration/test_monitoring.py`: Phase 6 integration and recovery verification.
- `docs/monitoring.md`, `docs/phase-6-files.md`, `docs/phase-6-validation.md`:
  behavioral/operational contract, inventory and executed verification.

Updated:
- `backend/app/services/ingestion.py`: optional atomic transaction callback, shared
  source lock, and reopened jobs classified as updated. Core fetching/normalization/
  upsert logic is reused.
- `backend/alembic/env.py`: register new metadata.
- `backend/app/core/config.py`, `.env.example`: monitoring environment defaults.
- `tests/integration/test_catalog_jobs.py`: include Phase 6 tables in exact schema inventory.
- `README.md`, `docs/architecture.md`, `docs/database.md`, `docs/product-decisions.md`,
  `docs/spec.md`: operational instructions and explicit scope/state decisions.

## Official career acquisition correction

New: migration `0006_career_acquisition.py`; `backend/app/browser/` (provider and
URL-policy modules); `backend/app/sources/browser.py`; `scripts/verify_browserbase.py`;
`tests/integration/career_fixtures.py`, `conftest.py`, `test_career_browser.py`,
`test_browser_providers.py`; `tests/fixtures/career_sites/company_a.html`; and
`docs/company-career-sources.md`.

Updated: catalog model/schema/service, adapter registry, ingestion, monitoring
runner/scheduler and CLI, settings/environment example, backend dependency manifest
and lockfile, Docker Chromium installation, monitoring tests and architecture,
product, specification, database, README and verification documentation.

The stable Phase 5 matcher package/tests are preserved. Canonical Job schema/model,
existing API/UI, Greenhouse adapter and local `.env` are unchanged.
No Phase 7 notification work.
