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
