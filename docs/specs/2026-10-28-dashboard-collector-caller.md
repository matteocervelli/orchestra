# Collector caller — approved pure Phase A

Scope source: Parent Phase-A GO and full contract review, 2026-10-28. Sole author
handle /root/card_content_audit, dedicated branch fix/dashboard-collector-caller-
phase-a-20261028, exact base ec33bdb39d5950b2686ffe8b1810afbc2c9f4a37.
Core collector SHA1944831ec5e73bfea0f5f86934dec1eae125ca6748d0b818338417bbe4d6a97c
remains unchanged. This spec authorizes only pure helpers, callbacks and synthetic
storage; Phase B, exporter/Probes/workitems/M3S, provider or filesystem integration
and production publication remain outside the implementation.

## File Manifest

- `src/orchestra/dashboard/collector_caller.py`
- `src/orchestra/dashboard/collector_checkpoint.py`: bounded core-state codec,
  Snapshot and qualified-reference validation extracted from the actual667/854
  line WIP; no new authority, I/O or behavioral surface.
- `tests/unit/test_dashboard_collector_caller.py`
- `tests/unit/test_dashboard_collector_precedence.py`
- `tests/fixtures/collector_caller.py.txt`
- `docs/specs/2026-10-28-dashboard-collector-caller.md`
- `docs/provenance/dashboard-collector-caller-20261028.json`
- `tests/unit/test_dashboard_runtime_export.py`: only fixed inventory12→14 for
  the two inert SOURCE modules; all other byte/AST assertions preserved.

Parent amendment A7 authorized inventory12→13. Root internal-refactor GO after
measured667/854line complexity adds the codec path and changes only that counter
to12→14 after RED. Final eight-file result requires Parent acceptance before
commit/push; Parent documents/WIP remain untouched.
Existing maps are read; no map/exporter/common/core edits are authorized here.

## Public contracts

`Budget(remaining, attempts=0)` validates exact integers within the shared25
domain. Its allowance is min(20,max(0,remaining-5)). The charged callback decrements
remaining and increments attempts immediately before the injected actual attempt;
cache hits charge zero and failures never refund. Core remaining reconciles calls,
never charges a second time. No process, clock or provider is chosen by the module.

`Snapshot(state, lineage, clock)` holds the complete accepted CollectionState,
qualified known-row evidence and last observed clock. `encode_checkpoint` and
`decode_checkpoint` accept explicit repositories/now and a limit no greater than
64MiB. Their JSON schema pins scope and core hash. All Page, Progress, LastGood,
cursor, known, invalidated and lineage fields roundtrip exactly. JSON data is
bounded UTF8, depth16, finite numbers and exact object keys; no duplicate keys,
arbitrary Python objects or bool-as-int. Digests are canonical unique lists on
wire and sets in memory. Qualified references, prefix consistency and timestamps
are validated without running collect to repair values. Existing security codecs
reject float timestamps, so their incompatible envelope codec is not reused.

`prepare_collection` receives Budget, attempt, explicit now/nondecreasing clock,
bounded read callback and atomic commit callback. Read receives only the two
fixed logical names prs-rest-v1.json and prs.json and at most limit+1. Commit
receives fully encoded checkpoint bytes and an optional fully encoded mirror;
its declared contract is all-or-none staged replacement. Phase-A tests implement
that contract in memory with faults before/after staging; no real multi-file
filesystem atomicity is claimed. A future Phase B must implement/review it.

Missing checkpoint may start with the prior LIST as retained rows of unknown
freshness. Corrupt checkpoint or prior is explicit error, never repaired as empty
complete. Codec/clock/commit failure returns an explicit error and previous bytes;
attempt counters remain spent. A valid partial checkpoint may advance; the mirror
remains unchanged unless every feed is complete, fresh and nonconflicting.
Ordinary exceptions from the injected read/commit boundaries become only the
existing load_error/storage_error result, without callback text or retries.
SystemExit, KeyboardInterrupt and BaseException cancellation propagate. An unread
prior remains unknown (None in Prepared), while storage bytes stay unchanged;
no callback that publishes partially and then raises is repaired by this helper.
Progress.last_created must be None or a finite nonfuture numeric timestamp whose
type is not bool before it is compared with the prefix witness; False cannot
stand for epoch0 and no timestamp is normalized to make the comparison pass.
The legacy LIST ingress has one explicit ABI exception verified by ROOT: exact
closedAt="0001-01-01T00:00:00Z" on exact state="open" becomes None in a private
working copy. The original LIST bytes remain available for fallback and unchanged
through partial/error rounds; only complete/fresh/nonconflicting collection may
replace the mirror. This creates no observation time, approval, head or other
missing field. createdAt/updatedAt/mergedAt, other strings and closed/merged states
retain their existing guards. This exception is not applied to checkpoint state;
strict codec dates and prefix validation are unchanged. Every LIST member must be
a JSON object before calling the core; null/bool/int/string/list members yield
fixed load_error, not AttributeError or empty-complete. V2 review remains scoped
to B1/NB1; this new legacy ingress requires its own follow-up acceptance.
Freshness900, cadence120 unchanged, cap64MiB apply to complete documents including
duplicated state, not just row payload. Limits never increase automatically.

`decode_page(stdout, returncode, observed_at)` is an inert decoder of the approved
gh --include response shape; CRLF/LF supported. Only status/body/next-link presence
are used. No next URL following or header/stderr persistence. Malformed responses
return fixed Page errors. The caller alone owns transport and charges attempts.

`select_prs(candidates, prior, now)` validates full host/owner/repo/number agreement.
Candidates carry row/observed_at/source; identity comparison does not assert new
repository authority. Different owners/forges never collapse. Fresh900 beats stale
and unknown, then updatedAt and true observed_at. Incompatible same-version
state/head observations conflict, retaining prior or omitting a new URL. Never
combine stale provider fields into a newer whole row; input records remain intact.

`bulk_meta(rows, cached, now)` keys metadata by the full qualified identity, emits
only present fields and real merged facts. Missing reviewDecision/mergeable/issue
refs remain absent. Optional cached review fields require exact qualified PR and
head and observation age<=300; no refresh callback exists. Reseeding from selected
rows is testable here; real Probes memo wiring remains Phase B.

## Requirements and test waves

- REQ-01: shared25 accounting for budgets0/4/5/6/25, cache hits, failures and
  clock/codec exceptions after attempts; default/import remains inert.
- REQ-02: lossless strict bounded codec across all core state fields, row lineage,
  prefix invalidation and cursor; reject invalid JSON/types/scope/core/time/state.
- REQ-03: full-document64MiB and depth bounds, encoding before any commit; fake
  staged failure retains prior bytes/counters; mirror only global complete fresh.
- REQ-04: actual core synthetic normal-cadence/resume/stale/offset recovery;82calls
  under allowance20 can need5runs but long requests can exceed900 and stay partial.
- REQ-05: qualified freshness precedence under permutations, explicit conflicts,
  foreign owner/forge isolation, prior retention and no arbitrary field merging.
- REQ-06:525 synthetic bulk rows with no provider fanout; unknown fields stay
  unknown, cache qualification/head/TTL enforced and selected metadata consistent.

Wave1: spec/readiness, tests RED then codec/callback/budget/storage GREEN.
Wave2: precedence/bulk meta RED→GREEN and shared regression tests. Run scoped
quality/security, then complete source suite with the inventory caveat reported
until actual amendment. Freeze exact manifest and stop for Parent-owned independent
review. No commit/push before acceptance.

## Boundaries after Phase A

No actual normal-caller feasibility or ownership claim is made. Remaining probes
historically22/25 do not fit a five-call reserve by assertion: Phase B must measure
the residual real caller demand after no-fanout and expose partial/degraded truth
or allocate fewer collector calls within25. B needs composed base/sole exporter
writer, updated M3S callable/memo/root profile, full snapshot-size measurement and
F1/consumer parity for scope27, known44 and104references (not104new cards).
No status, ask, answer, step, owner, cache, runtime or task is modified in A.

Subsequent read-only residual-demand inventory already finds cold15 requests
(health1 + five release projects/two bases10 + priorities4), or14 even if health
were covered by bulk. This is still >5, not a transport replay or permission to
change the approved A profile. Missing release-main/files/base/review/issue facts
must not become false, empty or approved values; the normal-caller contract stays
open for B and no prior M3S profile is claimed compatible.
