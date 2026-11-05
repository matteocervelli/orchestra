# Pure PR collection

`orchestra.dashboard.collector` implements collection logic only. Importing it
does not contact GitHub, inspect configuration, load a cache, or publish cards.
The caller supplies explicit repository authority, transport, observation time,
freshness window, remaining request budget and the previous state snapshot.

```python
from orchestra.dashboard.collector import Page, Repository, collect

# Synthetic transport example: three validated empty, exhausted feeds.
def example_page(request):
    assert request.query["per_page"] == 100
    return Page(rows=[], fetched_at=1000.0, has_next=False)

result = collect(
    [Repository("github.com", "matteocervelli", "synthetic")],
    example_page,
    now=1000.0,
    freshness=300.0,
    budget=25,
)
assert result.rows == []
assert all(feed["status"] == "complete" for feed in result.coverage)
assert result.budget_remaining == 22
```

## Caller contract

The repository list is an authorized scope, not discovery or proof of ownership.
Verify scope evidence before constructing it. Names are literal; this module
does not consult or modify legacy aliases or infer scope from head forks.

The callback receives generated request parameters and returns a `Page`. It must
report actual pagination evidence as `has_next`, plus the original observation
timestamp. It cannot supply a next URL. Unknown pagination and provider failures
remain incomplete. Recognized provider codes include `rate_limit`, `timeout`,
`unavailable` and `invalid_json`; arbitrary exception text is never emitted.

For a real callback that completes after the initial `now`, inject `clock` as an
explicit callable returning current UTC seconds. The collector checks observation
times against that frame and uses its final value for freshness. It does not call
a hidden system clock or rewrite provider timestamps. The fixed-now default is
for deterministic observations/cache snapshots; it rejects later fetched_at.
The clock must return valid, nondecreasing values. A bad clock can raise after a
transport call has already spent budget; an adapter must preserve its actual
request counter even on exceptions. The collector does not promise no-throw.

`Collection.state` contains copied page cache, per-feed progress, last-good
snapshots, known qualified rows and the next-feed cursor. The caller owns its
persistence and scheduling; no storage format, retries or scheduler are installed.
Pass the returned snapshot on the next invocation to resume a shared budget of
at most 25. Cache reads consume no request units. The first budget-blocked feed
retains priority even if earlier caches expire between calls.

Budget and transient transport failures retain their resumable prefix. A later
invocation restarts a stale or invalidated traversal and logically invalidates
only that feed's cached pages in the copied snapshot, so still-fresh old pages
cannot recreate an offset-boundary conflict. There is no retry in the same run,
extra budget, filesystem deletion, or loss of known rows/last-good snapshots.
Changing the authorized scope with previous retained/cache state requires an
explicit caller handoff; incompatible qualified references fail closed. No
automatic pruning or authority fallback is provided.

Inspect every coverage record, not just the row count. `complete` means a valid,
fresh traversal of that exact feed; `partial` exposes budget/conflicts, `stale`
exposes old observations, and `error` exposes rejected pages/provider failures.
`fallback_stale` marks old last-good data retained after a failed refresh.
`oldest_observation_at` never becomes fresh merely because a cache was reused.
The independent `last_good` feed snapshot is not overwritten by partial scans.
Known rows survive later empty scans: absence does not establish closure.

A conflicting URL is excluded from new observations, preserving a prior known
row if available. Only contributing feeds carry `conflicts` and cannot update
last-good. A completed conflicting scan becomes `partial/conflicting_records`,
with its original `scan_status` and `scan_reason` retained; error/stale/budget
diagnostics keep their original status/reason. Independent completed feeds still
refresh last-good. The next invocation reacquires affected feed prefixes.

Normalized rows keep the existing repository/number/url/title/state/body/labels,
createdAt/updatedAt/closedAt and bulk headRefName/headRefOid shape. Closed PRs
become merged only from valid `merged_at`; open `merge_commit_sha` is ignored.
`issue_url` and body references do not create issue associations. This module
neither resolves a dashboard owner nor verifies review, CI, release or deployment.

## Source-only boundary

Synthetic tests cover pagination beyond 200 and 1000, historical ordering/cutoff,
strict authority/state/type handling, budgets, cache expiry, progress and conflicts.
They do not prove a real PR inventory, retained historical owner compatibility or
safe publication. A future adapter, receipt sidecar, caller integration and replay
must receive separate review; none is wired by this module or its exporter.
Complete exporter bundles include this inert twelfth dashboard module. A delta
made against an older module inventory still rejects a different inventory;
exporting source does not authorize applying that delta or wiring this collector.
