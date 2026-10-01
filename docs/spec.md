# JobPulse: Project Spec

> Source of truth for the project. Read this before starting any phase. If code and spec disagree, flag it and update one of them. Do not silently drift.

---

## 1. Product

A profile-based job monitoring platform. A user creates one or more job-search **profiles**, selects the **companies** to monitor, and the system continuously discovers new jobs, decides whether each matches a profile, and notifies the user **only** about relevant new jobs.

```
User -> Profile -> Selected Companies -> Monitoring Engine
     -> Fetch -> Normalize -> Dedup -> Match -> Notify -> User action
```

This is **not** a scraper. The three capabilities are: career-site monitoring, profile-based matching, and personalized alerts.

Job states per user: `new`, `saved`, `applied`, `ignored`.

---

## 2. Fixed product decisions

Do not re-litigate these. Document trade-offs in `docs/product-decisions.md` only if you deviate.

1. **One notification per job per user**, listing all matching profiles inside it. Not one per profile.
2. **Idempotency:** `UNIQUE(profile_id, job_id)` on matches. The match row and its notification row are created in the **same transaction**. Retries must never produce duplicate alerts.
3. **Updated jobs:** a material change (title, location, or experience requirement) re-evaluates matching. A re-alert only happens if the user enabled "update alerts" on the profile. Default is off.
4. **Removed jobs:** a job absent from a successful fetch is marked `closed` after 2 consecutive successful fetches without it. A **failed** fetch never closes jobs.
5. **Failed sources are never treated as "zero jobs".** A fetch error and a legitimate empty result are different states.
6. **No LLM or paid API is required anywhere in the MVP.** The matcher must sit behind an interface so a semantic matcher can be added later.
7. **Modular monolith.** No microservices.

---

## 3. Stack (lean by default)

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2 | |
| DB | PostgreSQL | `pgvector` only in Phase 10 |
| Scheduling | **APScheduler** or a simple worker loop with `asyncio` concurrency | Introduce Redis + Celery/RQ **only** when concurrency or reliability needs justify it, and document why |
| Frontend | Next.js, TypeScript, Tailwind | |
| HTTP | `httpx` | |
| Text | RapidFuzz, stdlib | |
| Browser automation | Playwright | **Off by default.** Add only for a specific source that cannot be read any other way |
| Email | SMTP behind a provider interface | |
| Dev | Docker, docker-compose, `.env`, pytest, ruff, ESLint, pre-commit | |

Do not add technologies without a concrete reason.

---

## 4. Source adapter architecture

The core system must never know how a specific career site works.

```python
@dataclass
class RawJob:
    external_id: str
    title: str
    description: str
    location: str
    url: str
    posted_at: datetime | None = None
    employment_type: str | None = None
    raw: dict | None = None

class JobSource(ABC):
    @abstractmethod
    async def fetch_jobs(self) -> list[RawJob]: ...
    async def fetch_job_details(self, external_id: str) -> RawJob: ...   # optional
    @abstractmethod
    async def health_check(self) -> HealthResult: ...
```

Each adapter only converts a source's data into `RawJob`. A separate **normalizer** maps `RawJob` to the canonical `Job`. Adding a source means writing one adapter class and registering it.

**Adapter scope**
- Phase 4: **Greenhouse only** (public JSON endpoint `boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true`), plus a `FakeSource` for tests.
- Phase 9: Lever, Ashby. Workday only if time allows.
- Google, Amazon, Microsoft and other custom portals are **out of MVP scope**. Mark them `unsupported` rather than attempting a fragile scrape.

---

## 5. Data model (starting point; refine with migrations)

```
users              id, email, password_hash, created_at
companies          id, name, slug, ats_type, board_token/source_config (json), enabled
job_sources        id, company_id, type, config (json), active, poll_interval_sec,
                   last_checked_at, last_success_at, last_error_at,
                   consecutive_failures, health_status
jobs               id, company_id, source_id, external_job_id, title, description,
                   location, employment_type, experience_text, min_exp_years, max_exp_years,
                   posted_at, first_seen_at, last_seen_at, closed_at, application_url,
                   source_url, raw_data (jsonb), content_hash, status
profiles           id, user_id, name, active, exp_min, exp_max, employment_types[],
                   work_modes[], min_score, notify_channel, notify_frequency,
                   update_alerts
profile_roles      profile_id, role_group / title
profile_skills     profile_id, skill, kind (required|preferred)
profile_locations  profile_id, location, excluded (bool)
profile_keywords   profile_id, keyword, kind (include|exclude)
profile_companies  profile_id, company_id
job_matches        id, profile_id, job_id, score, reasons (jsonb), negative_reasons (jsonb),
                   created_at            UNIQUE(profile_id, job_id)
notifications      id, user_id, job_id, channel, status, sent_at, error, payload (jsonb)
                   UNIQUE(user_id, job_id, channel)
user_job_status    user_id, job_id, status (new|saved|applied|ignored), updated_at
monitor_runs       id, source_id, started_at, finished_at, status, jobs_fetched,
                   jobs_new, jobs_changed, jobs_duplicate, jobs_closed, matches_created,
                   notifications_created, error, duration_ms
source_errors      id, source_id, run_id, occurred_at, error_type, message
```

Required constraints and indexes:
- `UNIQUE(source_id, external_job_id)` on `jobs`
- Index on `jobs(content_hash)`, `jobs(company_id, closed_at)`, `jobs(first_seen_at)`
- `UNIQUE(profile_id, job_id)` on `job_matches`
- `UNIQUE(user_id, job_id, channel)` on `notifications`
- Foreign keys everywhere, `created_at` / `updated_at` on mutable tables

---

## 6. Deduplication and change detection

Layered, cheapest first:
1. `(source_id, external_job_id)`: primary identity.
2. Normalized URL (strip tracking params, fragments, trailing slashes).
3. `content_hash` of normalized title + location + description text: detects material changes.
4. Fuzzy `(company, title, location)` similarity (RapidFuzz) for cross-source duplicates. Phase 10.

Classification per fetched job: `new`, `unchanged`, `updated`. Per known job absent from fetch: `missing` -> `closed` after 2 clean runs.

---

## 7. Matching engine

A standalone service. **No matching logic in adapters, routes, or the scheduler.**

```python
class Matcher(Protocol):
    def match(self, job: Job, profile: Profile) -> MatchResult: ...

@dataclass
class MatchResult:
    matched: bool
    score: int                    # 0-100
    reasons: list[str]
    negative_reasons: list[str]
```

**Hard filters** (a failure means `matched=False`, no score needed):
- Excluded keywords in the title (e.g. Senior, Staff, Principal, Manager, Director, Lead)
- Excluded locations
- Employment type mismatch
- Required experience above the profile maximum

**Soft scoring** (weights are configurable constants, not magic numbers scattered in code):
- Title/role-group match
- Required and preferred skill overlap
- Location match
- Experience fit
- Work mode fit

Every point of score must map to a reason string. Alert threshold is per profile (`min_score`).

**Stages**
1. Normalized exact matching (lowercase, punctuation stripped, alias expansion).
2. Fuzzy matching for titles and skills via RapidFuzz.
3. Semantic matcher behind the same `Matcher` interface (Phase 10 only), applied only to jobs that pass hard filters and have borderline scores.

**Role groups:** ship a seed file of role groups (e.g. `software_engineer: [SDE, Software Developer, Associate Software Engineer, Graduate Software Engineer, ...]`). Users pick groups and can add custom aliases.

### Experience parsing spec

Implement as a pure, heavily tested function `parse_experience(text) -> ExperienceRange | None`.

Must handle at least:
- Ranges: "0-2 years", "0 to 2 yrs", "1-3 years of experience"
- Minimums: "3+ years", "at least 5 years", "minimum 2 years", "5 years or more"
- Entry-level phrases (treat as 0-1): "fresher", "new grad", "recent graduate", "entry level", "campus", "graduate program", "early career"
- Title signals as a fallback: "Intern", "Associate", "Junior", "I" -> entry; "Senior", "Staff", "Principal", "Lead" -> senior
- Ambiguity: when multiple numbers appear ("5 years Java, 2 years AWS"), take the **largest required** figure and note the ambiguity in `reasons`
- Unknown: return `None`. An unknown requirement is a **soft penalty**, not a hard reject.

Write at least 30 unit-test cases from realistic phrasings.

---

## 8. Monitoring workflow

1. Select active sources due for a check (`now - last_checked_at >= poll_interval`).
2. Fetch (bounded concurrency, per-source timeout, retry with backoff on transient errors).
3. Normalize -> dedup -> persist (transactional).
4. Detect new / updated / closed jobs.
5. Match new and updated jobs against active profiles that select this company.
6. Create `job_matches` + `notifications` in one transaction.
7. Update source metadata and write a `monitor_runs` row.
8. Send pending notifications (separate step; failures do not roll back matches).

**Source health**
- `healthy` -> `degraded` (1-2 consecutive failures) -> `failing` (3+) -> auto-pause after a configured limit.
- **Anomaly rule:** if a source that normally returns N jobs returns 0, or drops by more than a configured percentage in one run, mark `degraded` and do **not** close any jobs.
- Partial failure: one failing source must never block others.

---

## 9. Notifications

```
NotificationProvider
  |-- EmailNotificationProvider   (implement in MVP)
  |-- TelegramNotificationProvider (interface stub only)
  |-- DiscordNotificationProvider  (interface stub only)
```

Payload: company, role, location, experience, matched profile(s), score, "why it matched", posted date, application URL. Email is plain text plus simple HTML, with all external content sanitized.

Frequencies: `instant` and `daily_digest` for MVP.

---

## 10. API

REST, versioned under `/api`, Pydantic schemas for all input and output, **no business logic in route handlers**.

```
POST/GET/PATCH/DELETE  /api/profiles[/{id}]
POST   /api/profiles/{id}/duplicate
GET    /api/companies            (search)
GET/POST/PATCH  /api/sources
GET    /api/jobs                 (filters: profile, company, location, min_score, status, date)
GET    /api/jobs/{id}
POST   /api/jobs/{id}/save | apply | ignore
GET    /api/notifications
POST   /api/monitor/run          (admin)
GET    /api/monitor/status       (admin)
```

---

## 11. Frontend

Practical SaaS dashboard: responsive, loading/empty/error states, dark mode only if cheap.

- **Phase 2:** minimal profile form only.
- **Phase 8:** Overview, Profiles, Sources (with health), Jobs (filters + Save/Ignore/Applied), Notifications.
- Onboarding wizard and polish come last.

---

## 12. Security

- Password hashing (argon2 or bcrypt), secure session/JWT handling, per-user authorization on every resource
- Input validation everywhere, rate limiting on auth and expensive endpoints
- Secrets via environment variables only. Nothing hardcoded, nothing logged
- **SSRF protection:** adapters only call hosts from an allowlist derived from adapter config. Block private and loopback IP ranges. Never fetch a user-supplied URL directly
- Sanitize all job HTML before rendering or emailing
- Secure DB config (no default credentials outside local dev)

---

## 13. Source access policy

Use only publicly accessible career data and documented or public endpoints. Respect robots rules and site terms. **Never** bypass CAPTCHAs, authentication, access controls, or anti-bot protections. If a source cannot be monitored safely and reliably, mark it `unsupported`.

---

## 14. Observability

Structured logs per run: source, jobs fetched/new/updated/duplicate/closed, matches, notifications, errors, duration. Persist in `monitor_runs` and `source_errors`. Expose in an admin/debug view. Never log credentials.

---

## 15. Testing

- No live career sites in ordinary tests. Use `FakeSource` and recorded fixtures.
- Backend: profile CRUD + validation, normalizer, dedup, experience parser, matcher, notification generation, API endpoints and authorization
- Monitoring: new-job detection, duplicate detection, failed source, retry logic, partial failure, zero-job anomaly, idempotent re-run
- Frontend: profile form, job filters, status changes
- One optional live-integration test for Greenhouse, skipped by default

---

## 16. Evaluation (portfolio differentiator, required)

Build `eval/`:
- A labeled set of 100-200 real job postings, each labeled relevant / not relevant for at least 2 profiles
- A script that reports **precision, recall, and F1** for: keyword-only, weighted scoring, and (later) embeddings + hard filters
- Results checked into `docs/evaluation.md` with a short analysis of failure cases

---

## 17. Repository structure

```
backend/app/
  api/  core/  db/  models/  schemas/
  services/
  matching/         (matcher, scoring, experience parser, role groups)
  monitoring/       (scheduler, runner, health)
  notifications/
  sources/          (base.py, greenhouse.py, fake.py, ...)
  workers/  utils/  main.py
frontend/           (app/, components/, features/, lib/, types/)
tests/              (unit/, integration/, fixtures/)
eval/  scripts/  docker/  docs/
```

---

## 18. Phases and definitions of done

Each phase ends with: what was implemented, files changed, tests run, results, remaining issues, next step. Never claim something works unless it was actually tested.

| # | Phase | Done when |
|---|---|---|
| 1 | Foundation: repo, FastAPI, Postgres, Alembic, auth, Docker, minimal frontend shell | `docker-compose up` starts everything; signup/login works; migrations apply from scratch; auth tests pass |
| 2 | Profiles: CRUD, roles, skills, locations, preferences, minimal form | Profile CRUD covered by tests, including authorization (user A cannot read user B's profile) |
| 3 | Job model: companies, sources, canonical `Job`, persistence | Constraints exist in migrations; unique-violation tests pass |
| 4 | Greenhouse adapter + `FakeSource` + normalizer + dedup | **Running the fetch twice yields 0 new jobs on the second run**, proven by an automated test |
| 5 | Matching engine: hard filters, scoring, explanations, experience parser | 30+ parser cases pass; every score has matching reasons; matcher has no DB or network dependency |
| 6 | Monitoring: scheduler, runs, health, retries, new/updated/closed detection | Failed source does not close jobs; zero-job anomaly test passes; one source failing does not block others |
| 7 | Email notifications, idempotent | Re-running the pipeline creates no duplicate notifications; multi-profile match yields one notification |
| 8 | Dashboard: overview, profiles, sources, jobs, notifications | Full MVP flow (below) works end to end |
| 9 | More adapters: Lever, Ashby | Each passes the same adapter contract tests |
| 10 | Advanced: fuzzy, embeddings, cross-source dedup, evaluation comparison | `docs/evaluation.md` shows measured improvement or an honest negative result |

### MVP end-to-end flow (highest priority)

```
Sign up -> create "Software Engineer Fresher" profile -> select sources -> activate
-> scheduler runs -> jobs fetched -> normalized -> deduplicated -> matched
-> match stored -> email sent -> job appears in dashboard -> user saves/applies/ignores
```

---

## 19. Engineering rules

- Small modules, strong typing, no duplicated logic
- Explicit over clever. Dependency injection where useful
- No swallowed exceptions. Errors carry useful messages
- Transactions wherever atomicity matters
- Indexes justified by real query patterns
- Decide ambiguous design questions yourself, document the trade-off briefly in `docs/product-decisions.md`, and only stop to ask when a choice has large, hard-to-reverse consequences
- Keep changes focused. Update docs with each phase

## 20. Required docs

- `docs/architecture.md`: components, data flow, adapter and matcher interfaces, monitoring workflow
- `docs/product-decisions.md`: decisions, trade-offs, deviations from this spec
- `docs/evaluation.md`: evaluation method and results
