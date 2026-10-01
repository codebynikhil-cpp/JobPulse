# Official company career acquisition (Phase 6)

The product monitors official company career sites selected by users. ATS/platform classification is an implementation detail of acquiring jobs from those company sites.

## Review of the completed baseline

Phases 1-2 authentication and owned profiles need no rewrite. Phase 3 already keeps
companies/sources/canonical jobs globally, and source-scoped identity supports
shared ingestion for many users. Phase 4 Greenhouse remains a valid HTTP acquisition
adapter returning RawJob. Its normalizer/upsert pipeline is reused unchanged.
Phase 5 Matcher stays deterministic and free of infrastructure dependencies.
Phase 6 current state, recovery work, source isolation and profile/company selection
are retained. The genuine mismatch found during review was scheduling unselected
companies; due selection now requires an active subscribed profile as well.

## Company, career source, platform and acquisition

A company is a global organization. Its career source records the official
`career_url`, `source_type`, `acquisition_method`, `adapter_key`, configuration,
activation and polling state. ProfileCompany connects owned profiles to these shared
companies. Multiple users select the same company without duplicating company,
source or canonical jobs; each profile receives its own current MatchResult.

Migration **0006** adds three source fields:
- career_url: nullable URL (2048 characters).
- acquisition_method: `http` or `browser`, required and defaulted to `http`.
- adapter_key: optional explicit registered implementation key.

Browser sources require a career URL in Pydantic and PostgreSQL. Existing HTTP
sources retain null URL as unknown legacy metadata, so Phase 4 records/configs remain
valid; no official URL or company/platform affiliation is invented in a backfill.
Catalog configuration is trusted internal tooling: verify that URLs/endpoints actually
belong to the company before enabling them. URL syntax alone does not prove that.
The illustrative United Airlines example does not certify a Workday adapter or a
live extraction path for that company.

The six platform classifications remain exactly greenhouse/lever/ashby/workday/api/
custom. HTTP is not a seventh platform, browser is not a platform, and Browserbase
is not a source type. Runtime capability is the tuple of registered adapter key,
platform classification and acquisition method. A Greenhouse/browser source is
unsupported until an appropriate browser adapter exists; it cannot silently fall
back to HTTP. Unknown explicit keys are unsupported. The only production
registration remains Greenhouse/http. No new production company adapter is added.

## Acquisition and adapter resolution

AdapterRegistry contains explicit small registrations. Scheduler SQL uses those
registrations, active source/enabled company state, due time and the existence of an
active subscribed profile. Eligibility is rechecked after acquiring the source lock.
Manual `app.monitor run` remains diagnostic and can run an enabled supported source
without subscriptions; matching still loads only active subscribed profiles.

The resolver selects a provider-neutral JobSourceAdapter. Ingestion constructs it
inside the existing HTTP-client lifetime and calls fetch_jobs, then follows the
same normalizer/canonical upsert/transaction hook/matcher path. Source configuration
checks now include URL, acquisition method and adapter key, so a change during fetch
cannot commit against stale acquisition metadata.

Greenhouse uses its existing fixed public host/board-token endpoint. career_url is
company-domain metadata, not an instruction to redirect Greenhouse HTTP requests.
HTTP is preferred where a reliable official structured endpoint exists. Browser
rendering is reserved for company adapters that require it. There is no giant
configurable production scraper, generic arbitrary-URL HTTP adapter or automatic
platform discovery.

## Browser adapter foundation

BrowserSourceAdapter is abstract. A concrete company adapter implements extract_jobs
and advance (pagination/load-more/search as actually needed). It can override
prepare_page to attach company-specific request/response observation before initial
navigation. Network discovery is opt-in adapter logic; no arbitrary response-body
capture or generic interception is implemented.

BrowserSourceConfig contains only career URL, explicit readiness selector, timeout,
page bound and job bound. The base opens the URL, checks navigation status, waits
for readiness, collects provider-neutral RawJobs and closes the context. It validates
required row identity/title/URL; exact repeats are coalesced for overlapping pages/
load-more, while conflicting identities fail. Exhausted pagination bounds or any
partial extraction failure fail the entire fetch. Empty successful batches require
an adapter's explicit ready-and-complete result; missing DOM is never inferred empty.
Normalization, persistence and matching remain outside the browser adapter.

## Browser providers and lifecycle

BrowserProvider supplies a scoped Playwright Page and hides execution location.
LocalPlaywrightProvider launches a bounded local Chromium session and creates an
isolated, nonpersistent context. BrowserbasePlaywrightProvider creates a session
through the official API, connects Playwright over CDP, creates the same isolated
context, closes it/browser, then requests session release in finally. Capacity is
bounded per provider instance; the monitoring worker also remains sequential.
Create/connect/extraction failures and cancellation release resources. A cloud
session whose creation response is lost may survive only until its bounded timeout.

Browserbase is optional. Settings use environment-only SecretStr API credentials,
project ID, provider selection (local default) and maximum sessions. No credentials,
CDP URL or remote response bodies are persisted in source config/run logs. Provider
errors expose safe error types/messages. Captcha solving and advanced stealth are
explicitly disabled; no proxies, evasion, authentication or persistent storage state
are configured. This follows the official [create-session API](https://docs.browserbase.com/reference/api/create-a-session)
and [release-session API](https://docs.browserbase.com/reference/api/update-a-session).

Local production launch requests Chromium's sandbox. Deterministic local fixture
tests explicitly disable that browser sandbox within the non-root Docker test
container because default container kernels may not permit nested sandboxing. This
exception is in fixture code, not source configuration or an environment switch.
A production local browser deployment must support Chromium sandboxing and restrict
network egress. Browserbase live sessions were **not** verified in this work.

## Browser network/access boundaries

A trusted company adapter supplies BrowserURLPolicy's hostname allowlist. HTTP(S)
URLs must be credential-free, and all resolved IPs must be public. The provider
routes context requests through this guard, including redirects and XHR, blocks
service workers, WebSockets and popups, and disables downloads. Attempts to leave
the allowlist invalidate the fetch; no partial-success fallback. Fixture policy
permits only the exact local server origin and lives solely in tests. There is no
persisted private-network exception.

DNS validation and request guards are defense in depth, not a replacement for a
public-only egress policy: browser/cloud DNS resolution is separate from Python's
preflight resolver. No production browser adapter is currently runnable. Future
adapter deployment must enforce provider/container public-network egress as well
as this application guard. Only publicly accessible career information is in scope;
access-control/CAPTCHA/anti-bot barriers must yield unsupported/failure rather than
bypass. Extraction details remain site-specific and must be maintained when sites
change.

## Deterministic verification and live provider path

Normal tests launch real local Playwright against an ephemeral local HTTP server.
Company A renders jobs through JavaScript/XHR with pagination or load-more; Company B
serves structured JSON. Their adapters are test-only injected registry entries,
never production classifications/capabilities. The scheduler-to-canonical-to-matcher
acceptance scenario verifies both methods, shared jobs for two users, identical
repeat idempotency, one changed job, and isolation of a partial browser failure.
Browser tests also cover timeout, 503, malformed DOM, repeated/conflicting records,
page bounds and private job URLs. Provider protocol tests mock Browserbase API/CDP,
including cleanup, cancellation, capacity and invalid CDP URLs; they need no account.

Docker installs the locked Playwright package plus Chromium/system libraries.
Host setup: `uv sync --project backend`, then `uv run --project backend playwright
install chromium`. The full PostgreSQL/browser suite runs in the backend container.

Optional **live/paid** Browserbase provider verification, explicitly invoked with
credentials and a public allowlisted probe URL:

```sh
# From repo root, with DATABASE_URL and BROWSERBASE_* in the process environment.
uv run --project backend python scripts/verify_browserbase.py https://example.com/
```

This only checks provider connectivity/navigation/cleanup; it does not certify any
company adapter. It is excluded from ordinary tests and was not executed here.
Run JSON now identifies company, source, acquisition method and effective adapter
key alongside all existing counts/status/timing/errors. See phase-6-validation.md
for exact final results and phase-6-files.md for the complete file inventory.
