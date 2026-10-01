# Frontend redesign validation

Date: 2026-10-02. Scope: approved frontend redesign after Phase 8.

## Implementation

- Shared authenticated `(app)` server layout; existing URLs preserved.
- Responsive sidebar, mobile Radix navigation sheet, active links, user dropdown,
  unread indicator, job search, skip link and consistent page headers.
- Restrained light design tokens, semantic badges, Lucide icons, accessible dialogs,
  live toast feedback, skeletons, empty/error states and reduced-motion support.
- Shared job rows/actions across dashboard, Jobs, Saved and Applied; official Apply
  links remain separate from explicit Mark applied actions.
- URL filters, document navigation for query-only controls, current-page
  score/company sorting and readable match
  reasons; descriptions remain text rather than rendering external HTML.
- Structured profile forms and CRUD, profile-specific company monitoring, four
  user-facing source health states, notification tabs and read actions.
- Central typed server reads/browser mutations; existing proxies and backend
  authorization, schemas, matching, monitoring and delivery behavior preserved.

## Dependencies

Added only `lucide-react`, `@radix-ui/react-dialog` and
`@radix-ui/react-dropdown-menu`. No Next/React upgrade, state framework, table
framework, production fixture data or backend migration.

## Verification

| Check | Command | Result |
| --- | --- | --- |
| Frontend ESLint | `docker compose exec -T frontend npm run lint` | Passed |
| TypeScript | `docker compose exec -T frontend npm run typecheck -- --incremental false` | Passed |
| Production build | `docker compose build frontend` | Passed: Next.js 15.5.27 |
| Backend regressions | `docker compose exec -T backend pytest -q` | 404 passed; one existing Starlette/httpx deprecation warning |
| Authentication HTTP smoke | `python scripts/smoke_stack.py` | Passed |
| Profile HTTP smoke | `python scripts/smoke_profiles.py` | Passed |
| Production Chromium smoke | Copy `scripts/smoke_dashboard.py` to `/tmp` in backend; run with `PYTHONPATH=/app` | Passed |
| Browser script Ruff | `ruff check` and `ruff format --check` against smoke script | Passed |
| Repository hooks | `backend/.venv/Scripts/python.exe -m pre_commit run --all-files` | Ruff check, Ruff format and frontend ESLint passed |
| Compose | `docker compose ps` | PostgreSQL, backend and frontend healthy |

Typecheck disables only incremental cache writing in the running read-only
application directory; it does not disable type validation. Normal local
`npm run typecheck` also passed. Docker production build performs its own lint
and type validation. No errors were suppressed or rules disabled.

Chromium uses isolated users and persisted FakeSource data, with cleanup. It
verifies browser signup/login/logout and invalid-password feedback; monitoring,
matching and notification creation; save/applied/ignore/restore; owner-isolated
interactions and unchanged canonical job records; profile creation/editing,
activation/deactivation and confirmation deletion; company toggles; all four
health labels and hidden health for unmonitored companies; notification read
state independent of email delivery; read filters/read-all; URL filter persistence;
and actual multi-page jobs, notifications and profiles.

Ten authenticated screens are checked at 390x844, 768x1024, 1280x800 and
1920x1080. The checks assert visible page headings and no horizontal overflow.
Mobile navigation and deletion dialogs receive focus, dismiss with Escape and
return focus correctly. No browser `pageerror` events occurred during the
responsive screen checks. This is a Chromium smoke and keyboard check, not a
full assistive-technology or cross-browser certification.

## Screenshots

Screenshots contain isolated browser fixture data, not application seed data:

- [Dashboard](screenshots/redesign-dashboard.png)
- [Mobile](screenshots/redesign-mobile.png)
- [Job detail](screenshots/redesign-job-detail.png)
- [Profile form](screenshots/redesign-profile-form.png)
- [Companies](screenshots/redesign-companies.png)

## Contract limitations

- Backend pagination stays newest first. Alternate sorting is clearly labelled
  within the current page; global alternate sorting needs an API extension.
- Profile notification preferences are not exposed by the current profile API.
- Subscription coverage refers to active profiles; inactive coverage is not
  fully available from the existing endpoint.
- Company match counts represent matching open jobs, not a recent time window.
- Saved/applied counts are current state, not a fabricated historical timeline.
- Account settings expose existing identity/session functionality only.

No backend files, migrations or API contracts changed. Existing Phase 1-8 history
is preserved. The full changed-file manifest is in frontend-redesign-files.md.
