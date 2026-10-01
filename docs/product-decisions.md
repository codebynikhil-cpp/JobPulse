# Product and engineering decisions

## Phase 1

- Use opaque database-backed sessions rather than JWTs. Immediate logout/revocation and simple first-party cookie handling justify one database lookup per authenticated request.
- Argon2id hashes passwords. Unknown-email logins verify a process-initialized dummy Argon2 hash and return the same 401 detail as wrong passwords. Password inputs are bounded to 12-128 characters.
- NFKC + trim + lowercase email normalization precedes validation and is reapplied afterward. The stored normalized value has a PostgreSQL unique constraint. All accounts treat the email local part as case-insensitive; no provider-specific dot/plus rewriting.
- Signup starts a session; login/signup replace any session presented in the current browser. Other devices remain signed in. Tokens are generated with `secrets.token_urlsafe(32)` and persisted only as SHA-256 digests. HTTPS cookies use `__Host-`, Secure, HttpOnly, SameSite=Lax, Path=/, and no Domain.
- Same-origin Next.js proxying plus explicit Origin checks protects cookie-based mutations. Server-side dashboard validation uses an uncached `/api/auth/me` request forwarding the cookie.
- Failed auth attempts use PostgreSQL fixed-window counters keyed by a hash of IP + normalized email, separated by route. Advisory transaction locks prevent parallel requests bypassing the threshold. This adds database writes and serializes same-identity requests but avoids adding Redis. Invalid schemas are validated before auth; logout needs an allowed origin and is idempotent without password hashing.
- Expired sessions and rate windows are deleted only opportunistically during login/signup. No scheduler, worker or background cleanup.
- X-Forwarded-For is ignored unless explicitly enabled. The default frontend-proxy peer identity is shared for a given email. Production original-client-IP throttling requires a trusted sanitizing ingress and restricted backend access.
- Local Compose applies migrations before backend startup; production must migrate separately. Containers run non-root and PostgreSQL has no exposed port. The bootstrap DB user is local-only; separate least-privilege production roles are required.
- `uv.lock` and `package-lock.json` pin resolved dependencies. The Next.js 15 maintenance release uses the latest available security patch selected during implementation; official advisory: https://nextjs.org/blog/september-2026-security-release.

No product deviations or Phase 2 work.

The frontend overrides PostCSS to patched 8.5.28 to resolve audit findings in the framework's nested dependency, while retaining the current Next.js 15 maintenance release.

## Phase 2

- The user's approved Phase 2 instructions expand the spec's minimal form to a
  usable profile management section, including list/details/edit/activation/deletion.
  All work remains limited to user profile configuration.
- Use four normalized child tables. The requested profile_exclusions replaces the
  spec's starting-point profile_keywords table for excluded keyword/role terms.
  Inclusion keywords, score thresholds, notification preferences, company selection,
  role-group aliases and matcher behavior are deferred to their applicable phases.
- Required/preferred skills use an explicit kind; excluded terms have a separate
  table and keyword/role kind. Preferred/excluded locations share a unique identity
  so conflicting location settings cannot be stored through the API.
- Names are unique per user after NFKC, whitespace collapse and casefold. Child
  uniqueness uses the same normalization; display names retain casing. Free-text
  role titles are supported now without implementing future role expansion/matching.
- PATCH treats supplied lists as complete replacements, with omission preserving
  existing data. This keeps the API small and makes all child authorization depend
  on a verified parent, without arbitrary child-id mutation endpoints. Internal
  child IDs may change during replacement and are intentionally not exposed.
- Inactive drafts can be incomplete. Activation requires at least one target role.
  Empty preference lists mean any; experience null bounds mean unrestricted; remote
  preferences may still specify locations. Exact selected-role/exclusion conflicts
  and required/preferred duplication are rejected, without trying to perform matching.
- Experience uses decimal years (0-60, one fractional digit). Database-backed
  responses return decimal strings consistently. API inputs accept numeric values.
- Parent-row locks serialize updates; related replacements and timestamp changes
  are atomic. Invalid merged preferences and database uniqueness conflicts roll back
  rather than partially deleting configuration. Collection reads use select-in loading.
- Database cascades remove owned configuration on profile/user deletion; deleting
  child rows never deletes their parent. All new mutable tables have timestamps.
- No dependency or infrastructure additions. No Phase 3 implementation.

## Phase 3 source classification constraint

- The persisted `job_sources.source_type` field must accept exactly `greenhouse`,
  `lever`, `ashby`, `workday`, `api`, and `custom`. These values classify a source;
  they do not declare an implemented integration or monitoring capability.
- Persistence validation must enforce this fixed set independently of adapter
  availability. A valid classification must not be rejected because its adapter
  is absent. For example, `source_type = "workday"` can be stored without claiming
  that Workday monitoring is supported.
- Adapter availability is a separate runtime capability, to be introduced in the
  applicable later phase. A stored classification alone must never enable fetching
  or be presented as evidence that monitoring is supported.
- Phase 3 adds no adapters or provider-specific fetching logic. Phase 4 implements
  the Greenhouse adapter only (with FakeSource for tests, as specified). The other
  five persisted classifications do not become supported integrations in Phase 4.
- Phase 3 now implements this user requirement in migration 0004, the source model
  and Pydantic schema. No adapter-availability registry or integration is implemented.

## Phase 3 persistence decisions

- Keep company name/slug/enabled metadata in companies. Classification and source
  configuration live only in job_sources, refining the spec's starting-point
  redundant company ats_type/source_config fields. A company can have several sources
  with different classifications; no duplicated source configuration can drift.
- Enforce the six source values using a named PostgreSQL CHECK constraint and a
  matching Python string enum. No native database enum migration lifecycle is needed.
  FakeSource is a later test adapter, never a seventh persisted source classification.
- Source health defaults to unknown, active to false. Health/check/poll fields are
  persisted for future phases only; no availability is inferred or checking scheduled.
  Source configuration accepts generic JSON objects, without provider-specific logic.
- Source UUID is its identity: multiple sources per company and type are allowed.
  Job uniqueness is scoped to source UUID plus opaque external id. Inserting an
  existing identity raises a database uniqueness error; automatic upsert, change
  detection, URL normalization and cross-source deduplication wait until later phases.
- Jobs redundantly store company_id for company filtering; a composite source/company
  foreign key prevents inconsistency, including direct SQL writes. The supporting
  unique source id/company tuple exists for this referential constraint.
- Company/source deletion uses RESTRICT to preserve job history. Explicitly remove
  jobs before sources and sources before companies if deletion is actually intended.
  Disabled companies and inactive sources retain their records. No user-profile
  associations to companies, source administration endpoints or job UI are added yet.
- Canonical jobs store lifecycle open/closed, separate from future per-user
  new/saved/applied/ignored actions. Closed records require closed_at >= last_seen_at;
  first_seen_at <= last_seen_at. Stored closed status never runs closure detection.
- Unknown employment/experience are nullable. Canonical experience allows 0-100 years,
  one decimal place, with ordered bounds; parsing remains Phase 5. Content hash is
  nullable until a normalizer supplies it; supplied hashes must be lowercase SHA-256.
  URL syntax is validated but never fetched. External content is stored but not
  rendered or emailed; later consumers must sanitize it before those operations.
- Required indexes support source identity lookup, content-hash lookup, company/closed
  filtering and first-seen sorting. Source/company FK indexes also support referential
  checks. No speculative monitoring-run indexes or infrastructure are added.
- Services flush and leave commit/rollback to callers, allowing an atomic multi-table
  transaction. No provider-specific fetching or adapter availability checks exist.

## Phase 4 decisions

- Only Greenhouse has a production adapter. FakeSource is test-only. Valid persisted
  Workday/Lever/Ashby/api/custom sources remain representable; trying to execute one
  reports unavailable adapter explicitly without rejecting or deleting its record.
- The documented Greenhouse list endpoint returns the complete board. No pagination
  is invented; meta.total must agree with the array length. Duplicate post IDs and
  malformed/incomplete batches fail the run instead of becoming successful empty data.
- List updated_at is preserved in raw_data, never copied into posted_at. Employment,
  experience and publication remain null; location text such as Remote is not treated
  as an authoritative work-mode signal. No canonical schema migration is necessary.
- Normalized description is plain text extracted with stdlib HTMLParser after at most
  two entity-decode passes. Script/style contents are omitted. Original provider content
  remains in raw_data; this is not an HTML-rendering sanitizer. Later HTML consumers
  must still sanitize or escape external content.
- Text uses NFKC and collapsed whitespace. URLs lowercase scheme/host, remove fragments,
  trailing path slashes and utm_*/gclid/fbclid parameters, and sort remaining parameters.
  Identity-bearing parameters such as gh_jid are retained. URLs are stored, never fetched.
- SHA-256 hashes compact, sorted-key, UTF-8 JSON containing normalized title, description,
  location, employment_type, experience_text and application_url. Case is preserved.
  Fetch times, publication times, IDs and raw metadata do not enter the hash. Hash changes
  classify updates; metadata-only changes refresh raw_data but count as unchanged.
- Source-scoped external post identity is authoritative. Normalized URLs/content hashes
  support stable change detection; they do not merge distinct external IDs or sources.
  Cross-source/fuzzy deduplication remains Phase 10.
- PostgreSQL uniqueness and ON CONFLICT make retry insertion safe. Existing row updates
  preserve UUID/first_seen_at, refresh canonical/provider fields, advance last_seen_at,
  and reopen a returned closed job. Absent jobs are never closed in this phase.
- One ingestion call owns its transaction. Failed normalization or persistence commits
  no jobs; failure metadata is recorded separately, and the error is raised with a
  structured result. The last_error_at remains historical after recovery; successful
  checks reset consecutive_failures. Full health escalation/anomaly rules wait for Phase 6.
- Source locking serializes writes; an older fetch cannot overwrite a later completed
  check, whether successful or failed. No database lock is held during network access. Manual runs ignore
  scheduler activation flags intentionally. No source admin endpoints are exposed.
- httpx moves from dev-only to runtime dependencies without adding a new library/version.
  HTTP/DNS are mocked in ordinary tests. The mandatory fixture scenario creates five
  jobs, repeats with zero new rows, then updates one job while retaining all five IDs.
