# Phase 1 validation

Validated on 2026-10-01 using Windows PowerShell and Docker Desktop's Linux engine. Phase 2 has not been started.

## Commands and observed results

| Command | Result |
| --- | --- |
| `git init` | Initialized repository as the first implementation step. |
| `uv lock --project backend --check` | Lock is current; resolved 50 packages. |
| `docker compose up --build -d --wait --wait-timeout 120` | Exit 0; backend, frontend and PostgreSQL healthy. Next.js production build compiled, checked types and generated routes. |
| `docker compose exec -T backend pytest -q` | Exit 0; **16 passed**, 1 dependency deprecation warning, 8.63 seconds. Every run creates a new PostgreSQL database and applies both migrations from empty. |
| `docker compose exec -T backend ruff check . /tests` | All checks passed. |
| `docker compose exec -T backend ruff format --check . /tests` | 19 files already formatted. |
| `docker compose exec -T backend alembic check` | No new upgrade operations detected. |
| `docker compose exec -T backend alembic current` | `0002 (head)`. |
| `npm.cmd run lint` (frontend directory) | Exit 0; no warnings/errors after config fixes. |
| `npm.cmd run typecheck` (frontend directory) | Exit 0. |
| `npm.cmd run build` (frontend directory) | Exit 0; production compilation and route generation succeeded. The final Docker build independently verified the final frontend source. |
| `npm.cmd audit` (frontend directory) | Found 0 vulnerabilities after the PostCSS patch override. |
| `uv run --project backend pre-commit install` | Installed Git hook. |
| `uv run --project backend pre-commit run --all-files` | Ruff check, Ruff format and frontend ESLint passed. |
| `python scripts/smoke_stack.py` | Passed home/login/signup pages, anonymous redirect, signup, authenticated server-rendered dashboard, logout, wrong password, login and revoked-session dashboard access through the actual frontend proxy/backend/database stack. |
| `docker compose ps` | All three services healthy; only frontend/backend ports are bound to localhost; PostgreSQL has no published port. |
| `docker compose exec -T <service> id -u` | backend 10001, frontend 1000, postgres 999; all non-root. |
| `git check-ignore .env frontend/node_modules frontend/.next backend/.venv` | All ignored. |

## Test coverage

Signup and stored Argon2id hashes; 256-bit token digests; login session rotation; logout revocation; wrong-password and unknown-user generic responses; dummy Argon2 verification; NFKC/trim/lowercase duplicate emails; unauthenticated/invalid/expired cookies; password length bounds; failed-attempt counts; email isolation; ignored/default and explicitly enabled forwarding headers; successful attempts excluded from counters; duplicate-signup throttling; origin checks; opportunistic expiry cleanup; HTTPS Host cookie flags; migration constraints; simultaneous failures respecting the limit; session identity isolation.

## Failures resolved during implementation

Docker initially was stopped and was started. The first Compose build began before npm finished producing its lockfile; it was rerun after dependency installation. Two test fixtures initially failed: the Argon2 method spy targeted a read-only instance attribute, and PowerShell altered a Unicode literal; both were corrected and the entire suite rerun. Cross-environment import classifications were made explicit to fix Docker Ruff findings. The pre-commit formatter initially touched a fenced Python example in the specification; that change was reverted and hooks restricted to Python files. `docs/spec.md` remains unchanged. The smoke assertion was corrected to recognize Next.js streamed meta-refresh redirects and check that protected content is absent. A smoke run overlapped frontend recreation and was rerun after health checks passed.

## Remaining limits

No failing tests or functional issues observed. Starlette's TestClient emits an httpx deprecation warning; the existing httpx test path still passes. ESLint 9 emits an installation-time support deprecation notice. No warnings were suppressed. The proxy's default socket IP behavior and production trusted-ingress requirements are documented in README. HTTPS cookie flags are covered by tests; local Compose runs HTTP. HTTP checks exercise the frontend routes and server-side session gate, without browser automation. Smoke checks create randomly named local accounts; pytest uses and removes isolated databases.

The stack is left running at http://localhost:3000. Production migrations must run separately, as documented in README. The next step is review of Phase 1; Phase 2 requires a new instruction.
