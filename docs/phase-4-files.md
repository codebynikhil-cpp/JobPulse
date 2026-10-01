# Phase 4 changed files

Compared with Phase 3 commit `5c2b99b`:

- `README.md`: manual ingestion instructions and phase status.
- `backend/pyproject.toml`, `backend/uv.lock`: httpx declared as a runtime dependency.
- `backend/app/ingest.py`: explicit internal manual invocation.
- `backend/app/sources/__init__.py`: adapter package.
- `backend/app/sources/base.py`: RawJob, adapter protocol, health result and source errors.
- `backend/app/sources/greenhouse.py`: fixed-host public board fetching and validation.
- `backend/app/sources/fake.py`: deterministic test adapter with batches/failures.
- `backend/app/sources/registry.py`: availability separate from persisted classification.
- `backend/app/services/normalization.py`: canonical text/URL normalization and hashing.
- `backend/app/services/ingestion.py`: transactional upsert, results and source metadata.
- `tests/__init__.py`, `tests/integration/__init__.py`: explicit test packages.
- `tests/fixtures/greenhouse/board.json`: synthetic deterministic provider fixture.
- `tests/integration/test_ingestion.py`: adapter, normalizer and ingestion acceptance tests.
- `tests/integration/test_ingestion_safety.py`: DNS, rollback, stale runs and concurrency.
- `docs/greenhouse.md`: verified contract and implementation limitations.
- `docs/architecture.md`: ingestion boundaries and manual execution.
- `docs/product-decisions.md`: hash/update, identity and transaction decisions.
- `docs/phase-4-validation.md`: commands, results and limitations.
- `docs/phase-4-files.md`: this manifest.

Authentication/profile code, database schemas/migrations, Docker configuration and
frontend code are unchanged. No scheduler, other production adapters, matching,
notifications or new user-facing features were added.
