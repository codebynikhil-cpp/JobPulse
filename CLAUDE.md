# CLAUDE.md

## Project
JobPulse: a profile-based job monitoring platform. Users create job-search profiles, select companies to monitor, and get alerted only when a newly posted job matches their profile. This is not a scraper.

## Source of truth
Read `docs/spec.md` before starting any task. It defines the product decisions, stack, data model, adapter and matcher interfaces, phases, and each phase's definition of done. If code and spec disagree, flag it and update one of them. Do not drift silently.

## How to work
- Work on **one phase at a time**, only the phase I name. Do not start the next one.
- Before large changes: inspect the repo, propose the approach briefly, and wait for approval.
- Make small, focused changes. Keep modules small and strongly typed.
- Run the tests after each meaningful step. Fix failures instead of hiding them.
- **Never claim something works unless you actually ran it.**
- Decide minor design questions yourself and note trade-offs in `docs/product-decisions.md`. Stop and ask only when a choice is large and hard to reverse.
- Update docs as you go (`docs/architecture.md`, `docs/product-decisions.md`).

## Non-negotiable rules
- Modular monolith. No microservices.
- Keep the stack lean: no Redis, Celery, or Playwright until the spec's phases call for them or a documented need arises.
- No business logic in API route handlers.
- Matching logic lives only in the matching service, never in adapters, routes, or the scheduler.
- Source adapters only convert source data into `RawJob`. The rest of the system must not know how a specific career site works.
- Idempotency: `UNIQUE(profile_id, job_id)` on matches, and a match plus its notification are created in one transaction.
- A failed fetch is never the same as "zero jobs", and it never closes jobs.
- No LLM or paid API is required for the MVP.
- Tests never hit live career sites. Use `FakeSource` and fixtures.

## Security
- Secrets only via environment variables. Never hardcode or log credentials. Keep `.env.example` committed and `.env` ignored.
- Enforce per-user authorization on every resource.
- Validate all input. Sanitize all external HTML before rendering or emailing.
- SSRF protection: adapters call only allowlisted hosts, block private and loopback ranges, never fetch user-supplied URLs directly.
- Only use publicly accessible career data. Never bypass CAPTCHAs, authentication, access controls, anti-bot protections, or robots rules. Mark such sources `unsupported`.

## Commands
Phase 1 commands:
```
# run stack:      docker-compose up
# backend tests:  docker compose exec backend pytest -q
# lint backend:   docker compose exec backend ruff check . /tests
# lint frontend:  npm --prefix frontend run lint
# migrations:     docker compose run --rm backend alembic upgrade head
```

## Reporting format
At the end of every task, report:
1. What was implemented
2. Files changed
3. Tests run
4. Results
5. Remaining issues
6. Next step
