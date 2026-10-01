# API reference

FastAPI OpenAPI is available at `http://localhost:8000/docs` and `/openapi.json`.
The browser accesses auth and profiles through the same-origin Next.js `/api` proxy.
Cookies must be forwarded when using another HTTP client. All writes require `Origin`
equal to `APP_ORIGIN`. Authentication and profile ownership are checked on the backend.

## Authentication (Phase 1, unchanged)

- `POST /api/auth/signup`: email/password, 201 + session cookie.
- `POST /api/auth/login`: email/password, 200 + rotated session cookie.
- `POST /api/auth/logout`: 204, deletes the current session.
- `GET /api/auth/me`: 200 with account id/email, or 401.

## Profiles (Phase 2)

| Method | Endpoint | Success |
| --- | --- | --- |
| POST | `/api/profiles` | 201, complete saved profile |
| GET | `/api/profiles?limit=50&offset=0` | 200, array of owned profiles |
| GET | `/api/profiles/{id}` | 200, complete profile |
| PATCH | `/api/profiles/{id}` | 200, complete updated profile |
| DELETE | `/api/profiles/{id}` | 204, profile and child records deleted |

List limits are 1-100 (default 50), offsets nonnegative. Results order by newest
creation time, then id. Inactive profiles remain visible. There is no global profile
lookup or related-record endpoint accepting arbitrary owner/child IDs.

Example creation body:

```json
{
  "name": "Software Engineer - Early Career",
  "description": "Backend opportunities in India",
  "active": true,
  "exp_min": 0,
  "exp_max": 2,
  "employment_types": ["full_time", "internship"],
  "work_modes": ["remote", "hybrid"],
  "roles": [{"name": "Software Engineer"}, {"name": "Backend Developer"}],
  "skills": [
    {"name": "Python", "kind": "required"},
    {"name": "SQL", "kind": "preferred"}
  ],
  "locations": [{"name": "India", "excluded": false}],
  "exclusions": [{"term": "Senior", "kind": "keyword"}]
}
```

Only name is mandatory for creation. Active defaults to false; description to an
empty string; all lists to empty; experience bounds to null (unbounded). Active
profiles require at least one role. Employment values: full_time, part_time,
contract, internship, temporary. Work modes: remote, hybrid, onsite. Empty lists
mean no restriction. Remote work can coexist with geographic preferences.

PATCH sends only changed fields. A supplied list replaces that entire list, including
an empty list to clear it. Omitted lists stay unchanged. Experience bounds can be
cleared with null; other fields cannot be null. Activation/deactivation uses
`{"active": true}` / `{"active": false}`. Empty PATCH is an authorized no-op.
Every update is validated against the complete saved state, so changing only a
minimum cannot bypass range validation. All parent and child changes commit atomically.

Response includes id, created_at, updated_at and all profile fields, but excludes
user_id, child IDs and internal normalization keys. Experience numbers are returned
as decimal strings with one fractional digit, e.g. `"2.0"`. Configuration list order
is canonical database order, not insertion order. Treat roles/skills/locations/exclusions
as sets; display text casing is preserved after normalization.

Names: 1-100 characters after NFKC/whitespace normalization. Description: up to
2000 characters. Each child list: up to 50 entries; each name/term: 1-120 normalized
characters. Experience: 0-60 years with at most one decimal place and min <= max.
Duplicate child entries are rejected after NFKC, whitespace collapse and Unicode
casefold. A skill cannot be both required/preferred, a location cannot be both
preferred/excluded, and an exact selected role cannot also be an exclusion.
Profile names are unique per owner under the same normalization. Null characters in
text are rejected before PostgreSQL writes.

Errors: 401 missing/invalid/expired session; 403 invalid write Origin; 404 nonexistent
or foreign-owned profile; 409 duplicate profile name; 422 invalid payload/ID/preferences.
Unknown fields (including user_id/profile_id/child IDs in bodies) are rejected.
No request can transfer ownership. Standard Pydantic validation errors have a detail
array; business validation also returns a detail array; other errors use a detail string.

## Phase 3 internal persistence contracts

Phase 3 adds no HTTP endpoints or browser-facing source/job management. The approved
scope is storage: app.schemas.catalog exposes CompanyCreate/CompanyOut and
SourceCreate/SourceOut; app.schemas.job exposes JobCreate/JobOut. Internal catalog
services create/get companies and sources and list a company's sources. Job services
create/get jobs, look up a source/external id, and list a company's jobs (bounded to 100).
Callers supply a SQLAlchemy Session and own commit/rollback; writes flush and propagate
constraint errors. These are trusted backend operations, not user/admin APIs.

SourceCreate accepts company_id, source_type, generic config object, active (default
false) and poll_interval_sec (default 3600). Exactly six source types are allowed,
independent of adapter availability. For example source_type="workday" persists
without a Workday integration; no supported/adapter_available field is returned.
Health metadata in SourceOut starts unknown, never healthy merely because a type exists.

JobCreate accepts the canonical fields documented in database.md. company_id must
match its source. application_url is required and syntax-validated; unknown employment,
experience, posted date, source URL and content hash can be null. first_seen_at defaults
to now; last_seen_at defaults to first_seen_at. External IDs remain opaque: no matching,
URL stripping, content-hash computation, re-alert logic or automatic duplicate handling.
