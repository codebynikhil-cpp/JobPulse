# Greenhouse integration contract

Verified 2026-10-01 against the [official Job Board API documentation](https://docs.greenhouse.io/job-board.html).

- Public GET: `https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`.
  Detail GET: the same jobs path followed by `/{job_id}`. Neither requires authentication.
- List response: `jobs` array and `meta.total`. The documented list returns all posts;
  no pagination parameters or continuation mechanism are documented. Do not invent them.
- Use post `id` as external identity, not `internal_job_id`, which may be null.
- Map `title`, `location.name`, `content`, and `absolute_url` to canonical fields.
  Content can contain encoded HTML and board-level introduction/conclusion text.
- List examples include `updated_at`; detail examples also include `first_published`.
  Never substitute update time for publication time. Missing publication time stays null.
- No standard employment type, work mode, or experience field is documented.
  Custom metadata varies by board; preserve it without speculative interpretation.
- No numeric Job Board rate limit is specified on this documentation page.

## Phase 4 implementation policy

The adapter fetches one complete board response and rejects incomplete/malformed
responses, and never follow arbitrary provider URLs or redirects. Configuration
accepts a board token rather than an arbitrary fetch URL. Application URLs are stored
but never fetched. Timeouts, bounded response size, and limited transient retries
will protect manual ingestion; client errors will not be blindly retried.

Provider payloads remain available in raw_data. A provider-neutral normalizer
produces canonical values and a deterministic hash; no experience inference or
provider-specific canonical fields are introduced. No work-mode inference is
performed: the documented feed does not provide a standard field. The Phase 3
canonical schema remains unchanged, including its absence of a work_mode column.

Documentation retrieval is not a live board integration test. No live job-board
request has been executed. `source_type="greenhouse"` is currently the only source
type with an implemented adapter. Stored classification remains independent from
availability. FakeSource is test-only and never a seventh persisted source type.

The production client disables environment proxies and redirects, verifies HTTPS
certificates and checks fixed-host DNS results for non-public addresses. An injected
HTTP client is trusted infrastructure for deterministic tests, never source configuration.
Only 429, 5xx and connection/timeouts receive at most two retries. Retry-After seconds
and HTTP dates are honored within a 30-second wait budget; longer guidance stops the
run for a later manual retry. Other HTTP/transport errors fail explicitly.

List records deliberately never populate posted_at, even if an undocumented field
appears in the response. Detail retrieval is not implemented in this phase.
