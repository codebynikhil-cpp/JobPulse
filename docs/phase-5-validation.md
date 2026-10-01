# Phase 5 verification

Verified 2026-10-01 against the final rebuilt Docker Compose stack.

| Command | Result |
| --- | --- |
| `docker compose up --build -d --wait --wait-timeout 120` | Exit 0; all three services healthy |
| `docker compose exec -T backend pytest -q` | **274 passed, 1 warning in 32.51s** (188 existing + 86 Phase 5) |
| `docker compose exec -T backend pytest -c /app/pyproject.toml --confcutdir=/tests/unit /tests/unit -q` | **86 passed in 0.35s**; parent database fixtures excluded |
| `uv run --project backend pytest -c backend/pyproject.toml --confcutdir=tests/unit tests/unit -q` | **86 passed in 0.46s**; independent local verification |
| `docker compose exec -T backend python -c "from app.matching.examples import verify_examples; print('PASS:', len(verify_examples()), 'acceptance examples')"` | PASS: 10 acceptance examples |
| `docker compose exec -T backend alembic check` | No new upgrade operations detected |
| `docker compose exec -T backend alembic current` | `0004 (head)` |
| `uv run --project backend ruff check --config backend/pyproject.toml backend tests scripts` | All checks passed |
| `uv run --project backend ruff format --check --config backend/pyproject.toml backend tests scripts` | 57 files already formatted |
| `uv lock --project backend --check` | Exit 0; 50 packages resolved |
| `uv run --project backend pre-commit run --all-files` | Ruff check, Ruff format and frontend ESLint passed |
| `npm.cmd --prefix frontend run lint` | Exit 0 |
| `npm.cmd --prefix frontend run typecheck` | Exit 0 |
| `npm.cmd --prefix frontend run build` | Exit 0; compiled successfully in 2.3s |
| `python scripts/smoke_stack.py` | PASS: auth/pages/dashboard/session revocation |
| `python scripts/smoke_profiles.py` | PASS: profile CRUD/preferences/activation/authorization/pages |
| `git diff --check` | Exit 0; only Git line-ending notices |
| `docker compose ps` | Backend/frontend/PostgreSQL healthy; PostgreSQL has no host port |

The parser checks include 31 realistic numeric/wording cases, eight unknown-text
cases, eight uncertain title cases, structured-bound precedence, multiple/reversed
requirements, and three standalone numeric phrases. Broader tests verify required
skill zeroing, every hard filter, configurable thresholds/weights, alias precedence,
seed opt-out, exact skill boundaries, explicit negation, unknown optional fields,
conservative title scoring, unchanged canonical schema, explanation evidence,
repeatability and package import purity. The import test inspects the actual
installed matching package in both environments and allows only stdlib and
`app.matching` imports. The separate Phase 5 suite excludes database fixtures.

Ten hand-authored synthetic examples assert the following final results:

| Example | Score | Decision |
| --- | --- | --- |
| Graduate fit | 100 | matched |
| Custom alias | 100 | matched |
| Seed supplement | 100 | matched |
| Missing required skill | 0 | rejected |
| Explicit skill negation | 0 | rejected |
| Excluded seniority | 0 | rejected |
| Explicit senior experience | 0 | rejected |
| Unknown location/employment/experience | 70 | matched from other positive evidence |
| Unknown role, insufficient positive evidence | 25 | rejected below threshold |
| Uncertain senior title | 85 | matched; no numeric rejection or experience points |

Initial checks exposed partial parsing of an oversized duration and loss of .NET
punctuation. Both were fixed and their regressions pass. One early full-suite run
was interrupted by a container rebuild, and an intermediate image reproduced the
two parser/skill failures. Early smoke checks also overlapped restart and failed;
reruns after health readiness pass. Final results above are from the completed
final image, not the intermediate runs.

The full suite retains the existing Starlette TestClient/httpx deprecation warning.
No live career-site test or real-job precision/recall evaluation was run. Lexical
matching and the conservative parser have the documented prose limitations in
matching.md. Aliases and threshold overrides are matcher inputs only; existing
profile persistence/API/UI are unchanged. No remaining failing checks. Phase 6
has not started and requires a separate instruction.
