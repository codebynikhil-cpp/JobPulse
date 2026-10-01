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
starting point. No companies, job sources, jobs, matching or notification tables exist yet.
