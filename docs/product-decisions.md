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
