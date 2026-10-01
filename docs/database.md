# Database schema

Alembic is the schema authority. Phase 1 migrations 0001 and 0002 and all auth models
are unchanged. Phase 2 adds 0003_profiles; it upgrades an existing foundation database
and can apply with 0001/0002 from empty. Downgrading to 0002 removes only profile tables.
Production migrations must run as a separate deployment step.

## Foundation

- users: UUID id, unique normalized email, Argon2 password hash, created_at/updated_at.
- auth_sessions: UUID id, user FK CASCADE, unique token hash, created_at, indexed expiry.
- auth_rate_limits: UUID id, hashed key/route/window unique tuple, count, timestamps.

## Profiles

| Table | Fields and constraints |
| --- | --- |
| profiles | UUID id; user_id FK users ON DELETE CASCADE; name varchar(100); normalized name_key varchar(400); description text; active boolean; exp_min/exp_max numeric(3,1), nullable; employment_types varchar(24)[]; work_modes varchar(16)[]; timestamps |
| profile_roles | UUID id; profile_id FK; name varchar(120); normalized_name varchar(480); timestamps |
| profile_skills | Same base fields; kind required/preferred checked in DB; unique normalized skill across both kinds |
| profile_locations | Same base fields; excluded boolean; unique normalized location across included/excluded |
| profile_exclusions | UUID id; profile_id FK; term varchar(120); normalized_term varchar(480); kind keyword/role checked in DB; timestamps |

Each child FK uses ON DELETE CASCADE. Each normalized child key is UNIQUE with
profile_id, also providing an index for loading/deleting that profile's configuration.
UUID child keys are internal; API updates address the verified parent aggregate.
ORM relationships additionally use delete-orphan when replacing supplied lists.
Deleting a profile removes every child; deleting a user removes their profiles and
sessions. No cascade goes upward from a child to its profile or user.

Profiles have UNIQUE(user_id, name_key) and an index on (user_id, created_at, id)
for owned, paginated lists. DB checks enforce nonblank names/terms, experience
bounds/order, description size, supported employment values and supported work modes.
Pydantic additionally checks array/list duplicates, lengths, cross-list conflicts
and active-role requirements. Cross-table semantic validation lives in the service,
not in database triggers. All mutable profile tables have timezone-aware creation
and update timestamps; replacing any configuration also updates the parent timestamp.

Display names use NFKC + whitespace collapse; identity keys additionally Unicode-casefold.
Key columns allow expansion during casefold. Roles, skills, locations and exclusions
are relational rows, never comma-separated strings or JSON blobs. PostgreSQL arrays
are used only for finite employment/work-mode preference enums, following the spec's
starting point. Phase 3 adds the catalog/job tables below; matching and notification tables remain deferred.

## Phase 3 migration 0004_catalog_jobs

| Table | Persisted fields |
| --- | --- |
| companies | UUID id, name, unique lowercase slug, enabled, created_at/updated_at |
| job_sources | UUID id, company_id, source_type, config JSONB object, active, poll_interval_sec, last_checked_at/last_success_at/last_error_at, consecutive_failures, health_status, timestamps |
| jobs | UUID id, company_id, source_id, external_job_id, title, description, location, employment_type, experience_text, min_exp_years/max_exp_years, posted_at, first_seen_at, last_seen_at, closed_at, application_url, source_url, raw_data JSONB object, content_hash, status, timestamps |

job_sources.source_type accepts exactly greenhouse, lever, ashby, workday, api, custom.
A stored Workday source is valid without an implemented Workday adapter. No stored type
or active flag declares adapter support. Initial health is unknown and check times null.
Poll intervals are at least 60 seconds; failure counts nonnegative. Health metadata
values are unknown/healthy/degraded/failing/unsupported, not adapter availability.

Company/source foreign keys are restrictive. Jobs have a direct company FK and a
composite (source_id, company_id) FK to job_sources(id, company_id). That tuple has a
supporting unique constraint; it prevents cross-company source/job combinations.
UNIQUE(source_id, external_job_id) is enforced in PostgreSQL. Company slug is unique.
Indexes: jobs(content_hash), jobs(company_id, closed_at), jobs(first_seen_at),
jobs(source_id), job_sources(company_id). Existing auth/profile constraints are unchanged.

Database checks cover nonblank company/job identifiers and titles, slug format,
valid source/health/employment values, JSON object shapes, experience bounds/order,
seen timestamp order, closed status/time consistency and optional hash format.
Pydantic also validates URL syntax, timezone-aware timestamps, lengths, JSON safety
and rejects null characters/nonfinite JSON numbers before writes. No URLs are fetched.

0004 upgrades from 0003 or applies with previous migrations from empty. Downgrading
0004 drops only jobs, job_sources and companies in dependency order, preserving
profiles/authentication. Round trips are tested only in disposable test databases.
