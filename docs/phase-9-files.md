# Phase 9-15 Files Changed & Added

## Backend & Integration Code
- `backend/app/sources/lever.py` — Production Lever career postings adapter with DNS SSRF validation, multi-part description builder, and canonical commitment normalization.
- `backend/app/sources/ashby.py` — Production Ashby job board adapter with DNS SSRF validation, unlisted posting filtering, and location extraction.
- `backend/app/sources/registry.py` — Registered `SourceType.LEVER` and `SourceType.ASHBY` into `AVAILABLE_ADAPTERS` and `DEFAULT_REGISTRY`.
- `backend/app/worker.py` — Unified background worker executing monitoring scheduler and notification outbox delivery loops concurrently with graceful signal handling.
- `backend/app/monitor.py` — Enhanced CLI with graceful signal handling and detailed structured JSON logging.
- `backend/app/monitoring/runner.py` — Added structured metrics logging (counts, duration, tracebacks) and error isolation.
- `backend/app/monitoring/scheduler.py` — Wrapped due source queries and worker execution with fault-tolerant recovery for database blips.

## Test Fixtures & Automated Test Suite
- `tests/fixtures/lever/postings.json` — Verified realistic Lever postings payload.
- `tests/fixtures/ashby/board.json` — Verified realistic Ashby job board payload.
- `tests/integration/test_lever.py` — 10 integration tests covering registry resolution, fetching, normalization, duplicates, missing fields, malformed JSON, retries, and database ingestion.
- `tests/integration/test_ashby.py` — 10 integration tests covering Ashby board fetching, unlisted filtering, normalization, rate limits, and ingestion idempotency.
- `tests/integration/test_e2e_acceptance.py` — Comprehensive 14-step end-to-end acceptance test covering the entire candidate journey.
- `tests/integration/test_dashboard_and_feed.py` — Updated unimplemented capability parametrization to reflect Lever implementation.
- `tests/integration/test_ingestion.py` — Updated `AVAILABLE_ADAPTERS` inventory test to include Lever and Ashby.
- `tests/integration/test_monitoring.py` — Updated unsupported source classification test to reflect Lever and Ashby availability.

## DevOps, CI/CD & Scripts
- `.github/workflows/ci.yml` — Production GitHub Actions workflow running backend tests, Ruff linting/formatting, frontend lint, typecheck, build, and Docker Compose builds.
- `docker-compose.yml` — Added dedicated `worker` service running `app.worker` with auto-restart and health check dependencies.
- `docker/backend.Dockerfile` — Configured non-root ownership on `/tests/` to eliminate pytest cache warnings.
- `docker/frontend.Dockerfile` — Configured non-root ownership on `/app` to ensure clean typecheck builds.
- `.env.example` — Complete, production-grade documentation of all environment variables across all phases.
- `scripts/verify_resend.py` — Automated verification script for testing live email delivery via Resend API with actionable error reporting.

## Documentation
- `README.md` — Comprehensive project documentation reflecting Phase 9–15 capabilities, architecture, and verification.
- `docs/deployment.md` — Production deployment guide for Linux virtual machines (AWS, DigitalOcean, Hetzner) with reverse proxy, systemd, and backups.
- `docs/architecture.md` — Documented multi-source adapter architecture, background worker supervision, and outbox recovery.
- `docs/phase-9-validation.md` — Test evidence and regression report.

