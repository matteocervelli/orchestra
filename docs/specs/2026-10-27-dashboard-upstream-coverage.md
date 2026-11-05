# Pure upstream PR collector — source contract

Scope: one inert module, synthetic tests and its own documentation. No adapter,
network client, publisher, identity, registry mutation, capture or scheduler.

## File Manifest

- `src/orchestra/dashboard/collector.py`
- `tests/unit/test_dashboard_collector.py`
- `docs/specs/2026-10-27-dashboard-upstream-coverage.md`
- `docs/guides/dashboard-collector.md`
- `docs/provenance/dashboard-collector-coverage-20261027.json`
- `tests/unit/test_dashboard_runtime_export.py`: only the twelfth-module inventory.

## API

`Repository(host, owner, name)` is an explicitly authorized scope entry. Only
`github.com`, owner `matteocervelli`, and literal canonical repository names are
accepted. No suffix inference, head-fork authority or dependency-text parsing.
The caller owns scope evidence and freshness; this list does not discover repos.

`collect(repositories, fetch_page, *, now, freshness, budget, clock=None, state=None,
retained=(), cutoff="2026-10-13T00:00:00Z")` returns `Collection` with normalized
`rows`, per-feed `coverage`, `issues`, `state` and `budget_remaining`.
`now`, freshness seconds and remaining shared request budget are explicit inputs.
`state` is an injected cache/resume/last-good snapshot; the function copies it and
returns a new snapshot. It never reads or writes storage. A transport callback is
the only effect, and each uncached invocation consumes one unit, including errors.
No automatic retries, PR enrichment calls or hidden budget increases.

`clock` is an optional explicit UTC-seconds callback for transport that completes
after `now`. Its value is read before cache admission, after a fetch and for the
final receipt; no system clock is called internally. Without it, `now` is a fixed
as-of frame for deterministic/cached observations. A live callback must supply a
truthful clock rather than rewriting fetched_at to fit an earlier start time.
Observations later than the validation frame cannot establish coverage.
Clock values must be valid and nondecreasing. An invalid clock may raise after
budget was spent; a future adapter must retain its actual call counter on errors.

The callback receives an immutable `Request`: generated `repos/owner/repo/pulls`
endpoint and state/base/sort=created/direction=desc/per_page=100/page query. It
returns `Page(rows, fetched_at, has_next, error=None)`. Rows use GitHub REST list
PR shape; has_next is an explicitly observed boolean, never a provider URL.
Unknown pagination, provider errors and malformed responses cannot prove completion.

GitHub reference: REST List pull requests, API version 2026-03-10,
https://docs.github.com/en/rest/pulls/pulls#list-pull-requests . Contract facts
provided for this change: state open/closed/all, base filter, created descending,
maximum 100 records per page. Tests use declared synthetic payloads; available
observed schema summaries are not complete payloads or pagination evidence.

## Invariants

Three feeds per repository: OPEN auto/integration, OPEN main without a creation
cutoff, and ALL auto/integration since cutoff. Scheduling is round-robin, one
page per feed turn, preserving its next-feed index across budget-limited calls.
Cache keys include repository/base/state/cutoff/schema/page. Partial progress and
previous complete feed snapshots are separate; errors never replace last-good.
Missing records do not delete retained rows or imply closure/deployment.

Validate every row atomically before accepting a page: positive exact-int number,
HTTPS GitHub HTML URL and api.github.com URL agree with scope/number; base.ref and
base.repo.full_name agree with query. Head.repo is never authority. Require title,
created/updated timestamps, head.ref/SHA and labels; body may be null. REST open
stays open even when merge_commit_sha is non-null; only closed with a valid
merged_at timestamp becomes merged. issue_url is not an issue association.

Validate nonincreasing created ordering within and between pages. Historical
cutoff termination requires a whole valid page older than cutoff, not one old
row. Explicit has_next=False closes an exact-100 terminal page. Unknown pagination,
empty-with-next, repeated pages, malformed rows, excessive bytes or page limit
produce incomplete receipts, never truncation-as-complete. Limit 100 pages/feed
and 2 MiB serialized payload/page; both are enforced, not implicit Search caps.

Cache timestamps must be finite, no later than now. Completion requires all
observed pages within freshness. A new invocation restarts stale/nontransient
invalid progress and drops only that feed's cached pages from its copied state;
otherwise a still-fresh old offset prefix could wedge recovery. Transient errors
and budget stops resume their valid prefix; no retry happens in the same run.
Known rows, last-good and independent feeds are preserved. Caller must
persist returned state to make progress with shared budget 25; no cadence is
invented. Cached reads consume no request units.

Deduplicate by qualified URL. Conflicting observations across feeds stay visible
as incomplete only for contributing feeds, without last-writer-wins or updating
their last-good snapshots. Errors/stale/budget keep their original diagnostics;
completed conflicting scans preserve scan_status/reason when marked partial.
Independent completed feeds can refresh last-good. Retained
rows are validated qualified references, preserved when absent from observations.
Receipts expose query fingerprint, status complete/partial/stale/error, reason,
pages, calls, row count, exhaustion and last complete time. Complete describes
only these explicit feeds, not a legacy Search total, all-owned-repo coverage,
semantic owner correctness or delivery.
Changing scope with existing retained/cache state requires an explicit caller
handoff, not automatic pruning or authority fallback. Complete exporter bundles
contain the inert twelfth module; old deltas still require matching inventories.

## Acceptance gates

RED then GREEN synthetic tests: 201/471 and >1000 rows; terminal exact-100;
OPEN main/auto and old-open rows; closed/merged distinction; fork head; hostile
URLs/types/base; ordering/cutoff; duplicate conflicts; cache/budget fairness and
resume; stale/error/empty distinction; last-good retention; input immutability.
Follow-up regressions pin isolated conflicts alongside error/stale/budget and
independent last-good refresh, plus coherent offset-prefix recovery on a normal
later run while old cached prefix pages are still fresh or have become stale.
Frozen offline Python 3.12, scoped quality/security, whole source unit/coverage,
readiness and inert import. Independent reviewer after freeze, before any commit.
No claim that synthetic tests establish the finite real PR coverage baseline.

## Requirements

- REQ-01: explicit qualified authority and injected transport/state/clock/budget;
  no storage, provider, discovery, scheduler or live integration.
- REQ-02: three exact feeds, fair resumable progress, separated last-good cache and
  known records retained without inferring closure from absence.
- REQ-03: normalize only verified REST fields with scope/base/number agreement;
  open never means merged from a provisional merge commit; head forks are not
  authority. Invalid/missing required fields reject the page explicitly.
- REQ-04: bounded pagination, validated ordering, whole-page cutoff and explicit
  exhaustion, including more than 1000 rows and exact-100 terminal pages.
- REQ-05: explicit freshness and budget at most 25; one unit per uncached callback;
  errors/stale/unknown/budget observable without replacing last complete feeds.
- REQ-06: qualified deduplication without conflicting-record last-writer-wins;
  preserve inputs and retained records; feed completeness is not semantic owner,
  historical corpus, release or runtime compatibility proof.
