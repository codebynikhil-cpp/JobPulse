# JobPulse — Production Full-Stack Job Monitoring & Discovery Platform

JobPulse is an automated, multi-source job monitoring and candidate-matching platform. It monitors company career pages directly, discovers new postings, scores candidate fit deterministically, and dispatches timely email alerts through an transactional outbox.

---

## 1. System Architecture

```
                  ┌──────────────────────────────────────────────┐
                  │              Next.js 15 Frontend             │
                  │   (React 19, TypeScript, Tailwind CSS)       │
                  └──────────────────────┬───────────────────────┘
                                         │ HTTP / Same-Origin Cookies
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │               FastAPI Backend                │
                  │    (SQLAlchemy 2.x, Pydantic, Alembic)       │
                  └──────┬───────────────────────────────┬───────┘
                         │                               │
        Database Queries │                Dispatched     │ Background Tasks
        & Transactions   ▼                Background     ▼ (Monitoring & Ingestion)
     ┌───────────────────────┐              ┌───────────────────────────┐
     │     PostgreSQL 17     │              │    Background Worker      │
     │  (Profiles, Sources,  │◄─────────────┤ (app.worker / app.monitor)│
     │ Canonical Jobs, Match │   Claim Rows └─────────────┬─────────────┘
     │   Outbox, Sessions)   │                            │
     └───────────────────────┘                            │
                                                          ▼
                                            ┌───────────────────────────┐
                                            │   Career Source Adapters  │
                                            │  • Greenhouse HTTP        │
                                            │  • Lever HTTP API         │
                                            │  • Ashby Job-Board API    │
                                            │  • Local Playwright       │
                                            └───────────────────────────┘
```

---

## 2. Key Capabilities

- **User-Owned Profiles:** Multi-profile search targets with roles, required/preferred skills, locations (with exclusions), experience limits, and employment types.
- **Multi-Source Career Integrations:** Production adapters for **Greenhouse**, **Lever**, and **Ashby** official public APIs with DNS-level SSRF defense, rate-limiting backoff, and idempotent deduplication.
- **Deterministic Weighted Matching:** Zero-hallucination, explainable scoring engine evaluating keyword, skill, title, location, and seniority alignment.
- **Monitoring & Scheduling Worker:** Background supervisor with concurrency locking (`SELECT ... FOR UPDATE`), fault-isolated execution (one failing source never blocks others), and graceful SIGINT/SIGTERM shutdown.
- **Transactional Outbox & Notifications:** Reliable database-backed outbox claiming (`SELECT FOR UPDATE SKIP LOCKED`), retry with exponential backoff, orphaned-lease recovery, and Resend provider integration.
- **Modern User Experience:** Interactive job feed with score breakdowns, real-time search and filtering, custom job interactions (saved, applied, ignored), and company monitoring management.

---

## 3. Quick Start (Local Development)

### 3.1 Prerequisites
- Docker Engine & Docker Compose
- Node.js 22+ (for local host frontend development)
- Python 3.13+ with `uv` (for local host backend development)

### 3.2 Running with Docker Compose
```bash
# 1. Clone the repository and configure environment
cp .env.example .env

# 2. Build and start all services (PostgreSQL, Backend, Frontend, Worker)
docker compose up --build -d

# 3. Verify health
docker compose ps
```

- **Frontend:** http://localhost:3000
- **Backend API & Swagger Docs:** http://localhost:8000/docs
- **Backend Health Check:** http://localhost:8000/api/health

---

## 4. Background Worker & Monitoring Execution

JobPulse provides a unified background supervisor that runs both monitoring cycles and notification outbox delivery:

```bash
# Run unified worker (monitoring + notifications)
docker compose exec backend python -m app.worker

# Run monitoring supervisor independently
docker compose exec backend python -m app.monitor worker

# Inspect monitoring status of a specific source
docker compose exec backend python -m app.monitor status <SOURCE_UUID>
```

### Fault-Tolerant Worker Features
- **Concurrency Isolation:** `source_lock` ensures manual triggers and background ticks never execute concurrently on the same source.
- **Graceful Shutdown:** Intercepts `SIGINT` and `SIGTERM` to allow in-flight HTTP requests and database transactions to finish cleanly before stopping.
- **Transient Reconnection:** Automatically catches database blips without terminating the worker process.
- **Structured JSON Logging:** Emits machine-readable logs with `source_id`, `company_name`, `created_count`, `updated_count`, `duration_seconds`, and failure tracebacks.

---

## 5. Supported Career Source Adapters

All adapters implement the `JobSourceAdapter` contract and are resolved dynamically via `AdapterRegistry`:

| Provider | Endpoint Contract | Authentication | Key Normalizations |
| :--- | :--- | :--- | :--- |
| **Greenhouse** | `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs` | None (Public) | HTML descriptions unescaped, absolute URLs, ISO-8601 timestamps |
| **Lever** | `GET https://api.lever.co/v0/postings/{site}?mode=json` | None (Public) | Description parts concatenated, commitment normalized to canonical employment types, millisecond timestamps |
| **Ashby** | `GET https://api.ashbyhq.com/posting-api/job-board/{board}` | None (Public) | Secondary locations fallback, unlisted jobs skipped, publishedAt parsed |

---

## 6. Notification Delivery & Resend Integration

Outbox delivery is handled transactionally:
1. Candidate job matches generate pending outbox records.
2. The delivery worker claims batches atomically using `SELECT ... FOR UPDATE SKIP LOCKED`.
3. To enable real email delivery via Resend, configure:
   ```ini
   EMAIL_PROVIDER=resend
   RESEND_API_KEY=re_your_api_key
   EMAIL_FROM="JobPulse Alerts <notifications@yourdomain.com>"
   ```
4. Verify provider connectivity at any time:
   ```bash
   docker compose exec backend python /app/scripts/verify_resend.py
   ```

---

## 7. Quality Assurance & Verification

JobPulse maintains a regression baseline of **430 automated tests**:

```bash
# Run full pytest test suite (unit, integration, and E2E acceptance)
docker compose exec backend python -m pytest -q

# Run Ruff Python linter and formatter checks
docker compose exec backend uv run ruff check /app/app /tests
docker compose exec backend uv run ruff format --check /app/app /tests

# Run Frontend ESLint, TypeScript typecheck, and production build
docker compose exec frontend npm run lint
docker compose exec frontend npm run typecheck
docker compose exec frontend npm run build

# Run End-to-End full stack smoke test
python scripts/smoke_stack.py
```

---

## 8. Production Deployment

Refer to [`docs/deployment.md`](docs/deployment.md) for complete production deployment procedures on Linux VMs (AWS, Hetzner, DigitalOcean) with automated HTTPS, systemd service management, automated backups, and log rotation.
