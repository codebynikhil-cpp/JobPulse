# Monitoring (Phase 6)

## Running it

The worker is a sequential asyncio loop in the modular monolith, started explicitly
as a supervised process. No new dependencies, distributed queue or Compose service
is required. It does not auto-start inside FastAPI: multiple web workers should not
spawn implicit schedulers. Production should supervise `python -m app.monitor
worker` with the same environment/image as the backend and restart on process or
database failure. SIGINT stops the CLI; cancellation releases source locks. A lost
process's unfinished run is marked abandoned when that source is next acquired.

Commands (real configured Greenhouse sources make network requests):

```sh
# Configure a profile's company subscription; caller must provide its actual owner.
docker compose exec -T backend python -m app.monitor subscribe USER_UUID PROFILE_UUID COMPANY_UUID
# Run one enabled source immediately, ignoring only its due time.
docker compose exec -T backend python -m app.monitor run SOURCE_UUID
# Run one bounded batch of due sources.
docker compose exec -T backend python -m app.monitor due
# Repeat bounded due batches until interrupted.
docker compose exec -T backend python -m app.monitor worker
# Inspect the 20 latest persisted runs for one source.
docker compose exec -T backend python -m app.monitor status SOURCE_UUID
```

The existing `app.ingest` CLI remains a low-level ingestion diagnostic: it bypasses
activation and monitoring hooks. Use `app.monitor` for scheduled/manual monitoring.
Both paths share per-source locking. No live worker or provider fetch is run by
automated verification; tests use FakeSource, mocked HTTP and real local Playwright
against deterministic fixture career sites.

## Selection, ownership and bounded work

A scheduled source must be active, have an enabled company selected by at least
one active profile, resolve a registered classification/acquisition/adapter tuple,
and be due at `last_checked_at + poll_interval_sec <= now`.
Null last_checked_at means immediately due. Only Greenhouse HTTP is registered in
production. Persisted
Lever/Ashby/Workday/api/custom remain valid classifications but are excluded from
scheduled work; a manual monitoring attempt reports unsupported without fetching
and records unsupported health. Manual runs respect activation/company/adapter
eligibility; explicit diagnostic runs also allow unselected companies and bypass
polling time. Disabled/unsupported/not-due runs are
recorded; lock-busy attempts return a structured result without creating a run.

The oldest checked eligible sources run first, up to a configured source batch per
tick. This bounds result memory; subsequent ticks process remaining due sources.
Eligible source selection is rechecked after acquiring a lock. Profiles and jobs
use UUID keyset pages with configured limits, not offsets or unbounded collections.
Relationships are select-in loaded per profile page; every active subscribed
profile, regardless of its user, is evaluated independently against its own config.

Migration 0005 adds profile_companies as explicit subscriptions. No association
means no matching, avoiding implicit monitoring of every company by every user.
`subscribe_company` validates the supplied owner and profile before idempotent
insertion; the CLI is trusted developer/admin tooling, not an authenticated API.
No new HTTP endpoints, company picker or user-facing UI. Profile deletion cascades
subscriptions/matches. `list_current_matches` filters by owner, active profile,
current subscription, open job, current content hash and profile update time.
Profile edits hide stale positive states immediately. On the next successful
source observation, unchanged open jobs are queued when an active subscribed
profile is new or has changed since its evaluation. Jobs absent from that
observation are not automatically backfilled.

## Transactions, recovery and idempotency

The source lock is a PostgreSQL session advisory lock on a dedicated connection,
held through fetch/ingestion/evaluation/final result persistence. It is released in
finally, and an uncertain unlock invalidates the connection before pool return.
No row lock or open database transaction is held across network I/O. Advisory locks
are cooperative; both ingestion and monitoring follow the same protocol. Existing
source-row locking and stale-observation guards remain. This uses PostgreSQL's
[session lock behavior](https://www.postgresql.org/docs/17/explicit-locking.html#ADVISORY-LOCKS).

Monitoring calls Phase 4 `ingest_source` with a transaction callback. The callback
records clean-board observations, missing-job counters and pending evaluation flags
in the same transaction as canonical job upserts. Failed normalization, persistence
or callback work rolls back jobs and evaluation work together. The matcher is
unchanged: ORM profile preferences are materialized into MatchingProfile before
calling it; no matching rules are copied into the worker.

New jobs and any Phase 4 content-hash changes enqueue evaluation. The hash covers
title, description, location, employment, experience text and application URL;
raw metadata/publication-only updates do not enqueue. Reopened jobs count as updated.
Unchanged jobs are skipped unless recoverable work is pending or an active
subscription has no evaluation/current profile evidence for a returned open job.
New subscriptions and profile edits therefore refresh on successful acquisition
without treating identical canonical content as a new job.

JobMonitorState.pending is durable work, not a notification event. Evaluations are
committed per job transaction. Profile errors use savepoints, so other profiles
continue. A failed profile leaves the job pending. Successful identical evaluations
are skipped on retry using job content hash, a normalized input profile hash, and
matcher version/config identity. Recovery can therefore complete after ingestion
commits and the worker fails, without re-fetch being treated as a new job.

JobMatch is **current state**, keyed uniquely by (profile_id, job_id). It stores
matched/rejected or error, score, the complete JSON MatchResult evidence, hashes,
matcher identity and timestamps. Changed inputs update the existing row; identical
retries preserve it. A matcher exception is unknown (`matched=null`, `score=null`),
not a rejection. Its safe error type is recorded and retried on the next source run.
This is not evaluation history or a notification outbox. MonitorRun records run
history/counts/status; Phase 7 must introduce transactional notification intent and
its own deduplication policy. Current matches alone must not be interpreted as a
stream of unsent alerts. No notifications are created here.

## Health, anomalies and closure

Successful fetch/persistence updates checked/success times and resets transient
failure count/health. Historical last_error_at is retained after recovery. Failed
fetch/validation/transaction updates checked/error time, preserves last_success_at,
and escalates degraded (1-2) to failing (3+). At the configurable pause limit
(default 5), source.active becomes false; explicitly reactivate after investigation.
Profile evaluation failures mark the run partial but do not turn successful source
fetch health into a provider failure. A source timeout bounds the async ingestion
fetch with [asyncio.timeout](https://docs.python.org/3.13/library/asyncio-task.html#timeouts);
it does not claim to preempt synchronous matcher/DB execution.

An anomalous complete fetch is zero after a nonzero clean baseline or a drop
strictly greater than MONITOR_ANOMALY_DROP_FRACTION (default 0.5). On first monitoring
observation, existing open jobs provide a conservative baseline. Returned jobs may
be persisted/evaluated, but missing counters and closure do not advance. The clean
baseline is retained; repeated anomalies degrade/escalate/pause the source. A first
empty board with no history is a legitimate success. last_success_at reflects
successful fetch/persistence even on a count anomaly; run status records distrust
of absence evidence separately.

On each clean complete fetch, observed jobs reset their missing counters; absent
open jobs increment them. Two clean missing observations close a job. Failed or
anomalous runs never advance absence counters or close jobs. Counters are separate
from canonical Job; its schema remains unchanged. Reappearance resets counters and
reopens the canonical job with stable identity/first_seen_at.

## Results and configuration

MonitoringResult contains source/run IDs, start/completion timestamps, total
duration, reused IngestionResult, evaluation/match/failure/closure counts, status,
and safe stage/error type. The CLI and durable JSON expose ingestion counts both
inside ingestion and as top-level fields. MonitorRun is durable for started runs;
control-plane failure when the database cannot record a run remains visible in
logs and the returned cycle result. No provider payload, SQL values or raw exception
message is persisted in error reporting.

`.env.example` lists tick/timeout/batch/anomaly/pause defaults. Existing `.env` need
not change: settings supply defaults. Scoring uses Phase 5 ScoringConfig and its
configurable threshold/weights. No fuzzy, embedding or LLM matching.
