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

## Phase 5 decisions

- The approved constraints supersede the spec's staged fuzzy matching suggestion:
  Phase 5 uses deterministic exact phrases only. No additional dependencies.
- User role names and explicit aliases precede optional seed evidence. Existing
  profile/API storage is unchanged; aliases and thresholds are matcher input only.
- Required skills are mandatory positive evidence. Missing/explicitly negated
  skills fail a hard filter and force final score zero, even with strong unrelated
  evidence. Unknown optional fields earn no points and do not hard-reject.
- Default threshold 60 and initial weights 35/25/10/10/15/5 live in ScoringConfig.
  Missing/unconfigured components earn zero; weights are never redistributed.
- Canonical Job is unchanged. Work mode remains unknown; no location-text guess.
- Experience precedence: structured bounds, explicit numeric text, cautious wording,
  cautious titles. Only structured/numeric requirements can hard-reject above the
  profile maximum; ambiguous titles cannot reject or earn experience points.
- MatchResult includes hard-filter statuses, all component points/evidence,
  positive/negative evidence, experience provenance and final score/decision.
  Pre-filter component scores remain diagnostic when final score is forced to zero.
- The full lexical contract and limitations are in docs/matching.md. Ten synthetic
  hand-authored acceptance examples supplement 30+ realistic parser cases. No
  real-job evaluation metrics are claimed. No Phase 6 work is included.

## Phase 6 decisions

- The approved monitoring flow uses a sequential asyncio worker process and existing
  PostgreSQL session advisory locks. No scheduler library, queue, new service or
  adapter. Worker startup is explicit, separate from web-worker startup.
- Both monitored/manual source runs and low-level Phase 4 ingestion share the same
  source lock. Row locks/transactions are held only during persistence/evaluation,
  not while fetching. Due checks respect company enabled/source active, polling,
  and AVAILABLE_ADAPTERS independently from persisted source classification.
- Add explicit profile_companies subscriptions with an owner-checked internal helper
  and CLI. No selections means no applicable profiles, not all companies. This fills
  the Phase 3-deferred association needed for correct profile selection, without UI.
- Extend ingestion with an optional transaction callback. Monitoring uses its existing
  classifications and atomically records durable matching work with job writes.
  New/hash-changed/reopened jobs evaluate; unchanged jobs do not, except recovery work.
- JobMatch is current job/profile state with a composite primary key, complete matcher
  evidence and job/profile/config identities. It is not historical evaluation or
  a notification event. Matcher errors are unknown, not rejects, and leave work
  pending. Phase 7 must add its own transactional notification intent/deduplication.
- Use per-job transactions, profile savepoints and keyset pages to bound datasets and
  isolate profile failures. Identical successful evaluations preserve their rows on
  retry. Current-state reads are owner scoped and hide stale profile/job evidence.
- MonitorRun persists start/completion/counts/status/safe error context. Interrupted
  running records become abandoned on the next acquired source run. Busy attempts
  return structured results without creating an additional run record.
- Implement the source-of-truth Phase 6 closure/health policy: two clean missing
  observations close jobs; failures/anomalies do not advance missing counters.
  Zero after a nonzero baseline or a drop over configurable 50% is anomalous.
  Failure/anomaly health escalates at 3 and auto-pauses at configurable 5. Historical
  error timestamps survive recovery. Canonical Job and pure Phase 5 matcher unchanged.
- Settings/environment configuration owns tick/timeout/batch/anomaly/pause values.
  A bounded due batch runs per tick; one failure does not stop other sources.
- No notifications, new user-facing UI, embeddings/LLMs/fuzzy matching, new adapters,
  microservices or Phase 7 implementation. See docs/monitoring.md for the full contract.

## Phase 6 company-career architecture correction

The product monitors official company career sites selected by users. ATS/platform classification is an implementation detail of acquiring jobs from those company sites.

- Review confirms Phases 1-5 remain compatible: global companies/source-scoped jobs,
  Greenhouse RawJob acquisition, canonical normalization/upsert and the pure matcher
  are reused. No additional production company adapter or completed-phase rewrite.
- Add migration 0006 source career_url, acquisition_method (http/browser) and optional
  adapter_key. Legacy HTTP rows retain an unknown null career URL; no URL is invented.
  Browser rows require a URL; the existing six source classifications are unchanged.
- Runtime registration checks adapter/platform/acquisition together. Greenhouse/http
  remains the sole production entry; browser source classification never implies
  implemented extraction. Explicit unknown keys or mismatched methods are unsupported.
- Correct scheduled selection to require an active user profile's company subscription.
  Manual diagnostics may run enabled supported unselected sources. Canonical jobs and
  companies remain shared globally, while match state remains profile-owned.
- Add abstract BrowserSourceAdapter and Local/Browserbase Playwright providers with
  bounded sessions and deterministic fixture tests. Browserbase is optional infrastructure,
  environment configured, with create/connect/release protocol tests and a separate
  unexecuted live provider probe. No CAPTCHA solving, stealth, AI browser agents or
  generic production scraper.
- Browser requests/redirects use trusted host/public-IP guards; production public-only
  network egress remains required. Local fixture exceptions exist only in test code.
- See docs/company-career-sources.md for configuration, provider lifecycle, test strategy
  and explicit unverified live behavior. Phase 7 remains unimplemented.

## Phase 7 Notification Outbox, User/Job Deduplication, Email Delivery, Retries, and Changed-Job Alert Policy

- **Transactional Outbox:** Evaluated matches and notification outbox records (`notifications`) are written atomically within the per-job monitoring database transaction. Delivery is strictly decoupled and executed asynchronously by the database-backed notification worker.
- **User/Job Notification Deduplication:** If multiple active profiles of the same user match the same job, exactly ONE notification is produced. All matching profiles, individual match scores, and explanation evidence are aggregated in the single JSON payload. Different users each receive their own independent notification.
- **Changed-Job Policy:** Only material changes to canonical fields (`title`, `description`, `location`, `employment_type`, `experience_text`, `min_exp_years`, `max_exp_years`, `application_url`) trigger changed-job notifications. Unchanged jobs or non-material updates (such as `last_seen_at` or upstream scrape metadata) produce zero notifications. Configurable policy modes (`material`, `newly_relevant`, `off`) control whether already-matching candidates receive alerts on material updates.
- **Worker Claiming & Concurrency:** PostgreSQL row locking via `SELECT FOR UPDATE SKIP LOCKED` guarantees that concurrent notification workers never claim or deliver the same outbox item. Leases are bounded (`lease_seconds`), and stale orphaned records are safely recovered unless they exceed the maximum recovery window (`recovery_window_seconds`).
- **Email Provider Abstraction & Security:** `NotificationProvider` -> `EmailNotificationProvider` isolates the application from email vendors. `ResendEmailProvider` sends structured emails with `Idempotency-Key` headers matching `jobpulse-<notification_id>`. All user-controlled text is HTML-escaped with strict URL protocol sanitization (`http://` and `https://` only) to protect against injection/SSRF. Email credentials are kept in environment variables and never logged or persisted in outbox payloads.
- **Delivery Semantics:** Honest at-least-once delivery with provider-side deduplication. Because public email networks cannot guarantee strict exactly-once delivery, idempotency keys are used to prevent duplicate delivery on worker crash/recovery scenarios.
- **Bounded Retries:** Differentiates transient failures (network timeouts, 429 rate limits, 5xx server errors) from permanent rejections (invalid recipients, 401/403 authorization failures, 400/422 invalid payload errors). Transient errors retry with bounded exponential backoff (`delay = min(cap_seconds, base_seconds * 2^(attempts-1))`) up to `max_attempts`, after which the record transitions to `permanently_failed`. Permanent errors fail immediately without retry.



## Phase 8: personal dashboard and ownership

The authenticated workspace contains Dashboard, Jobs, Saved, Applied,
Notifications, Profiles, Companies and Account. There is no admin role or admin
workspace. The original spec's administrative/debug endpoints do not apply to
this phase. Next.js proxies forward session cookies and origin; backend mutation
routes use the same origin validation as profile mutations.

Canonical `jobs` remain shared. `user_job_interactions` has a unique
`(user_id, job_id)` identity and saved/applied/ignored states. An absent row means
new; restore deletes only that user's row. Status updates never write canonical
jobs. Feed, detail and status access require an evaluated positive match through
an active profile owned by the authenticated user. A job appears once regardless
of how many profiles match; all matching profiles and persisted reason strings
are displayed. Deactivating a profile removes its matches from current feed
access; interaction history remains stored and counted in the overview.

`notifications.read_at` represents UI read state independently of email/outbox
status. Public serialization omits provider errors and internal payloads.
Notifications and delivery aggregates are owner scoped; read-all only updates
that user's unread rows. Application links come from the persisted application
URL. Read changes leave delivery state untouched.

ProfileCompany remains the subscription identity. Company discovery lists enabled
companies, with subscription status and official career URL. Subscribing without a
profile ID targets all active owned profiles; a specific profile must be owned.
Source IDs, health, check timestamps and acquisition metadata are returned only
for monitored companies. The health endpoint requires an active owned subscribed
profile. No canonical company/job editing API is added for ordinary users.

Source health uses current scheduler state, not historical last_error_at:
missing/inactive source, disabled company or unsupported status -> unsupported;
3+ consecutive failures or active failing state -> failing; 1-2 failures or
active degraded state (including acquisition anomalies) -> degraded; otherwise
healthy. A successful normal run resets active failures; old error timestamps
never permanently mark a source failing. Never-checked healthy sources still show
last checked/last success as unavailable, not an invented check time.

Jobs use SQL filtering for profile/company/location/open or closed status,
interaction status, score, employment type, title/description/company search and
first discovery timestamp. Pagination defaults to 20, capped at 100. A distinct
job query counts before LIMIT/OFFSET; matching profile data is fetched only for
that page. Ignored jobs are hidden by default. Saved/applied views include closed
jobs. Sort is posted/discovered timestamp then job ID. Notifications use bounded
limit/offset, sorted by creation time and ID. Indexes support user/status lookup,
user/read lookup and user/created_at/id notification ordering. No search engine.

Migrations 0008 and 0009 add interactions/read state and notification ordering.
0009 is separate because the inherited development database already had 0008.
Browser verification uses persisted FakeSource data and local Chromium; it does
not depend on Browserbase, live company access or an email provider.

Disabled companies remain visible to current subscribers as unsupported. For a
company with multiple sources, the company health card uses the most severe
source state (unsupported > failing > degraded > healthy), with source ID as a
deterministic tie-breaker. Its timestamps/method refer to that representative
source; the health API remains individually scoped by source ID. Migration 0010
repairs inherited development column drift to Phase 7's Text contract without
truncating stored errors.
