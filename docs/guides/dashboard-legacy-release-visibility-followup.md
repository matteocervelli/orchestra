# Legacy release visibility follow-up

## Bounded implementation contract

Base: accepted SOURCE `908f01c`. The accepted alias/call-chip artifacts and
currently served baseline remain separate and unchanged.

Manifest: add `src/orchestra/dashboard/legacy/release-visibility.patch` and
`release-visibility-manifest.json`; extend the existing real-module Node test;
add an exact whitespace attribute for this generated patch; this short guide.
No new fixture, dependency, registry, exporter, data projection or Native change.

Change only `cb-state.js::releaseItem`: remove the ID/slugs regex branch. Preserve
`release_operation === true`, the existing five kinds
`release/tag/promotion/deploy/release_prepare`, and `releaseVisible` search reveal.
No status, ID, PR, ask, step, note, grouping or Rilasci rendering changes.

## Test matrix before implementation

1. Reproduce missing `hima19-beta-final-deploy-sol61-20261025` (Backlog/feature)
   and `pr-adlimen-cicd-40` (PR fix/fix), then retain both with default/repo/status
   filters. Their public rows have no ask/steps fields; tests do not invent those
   as real evidence.
2. Missing/false explicit flag plus ordinary feature/fix kind stays visible for
   release/tag/promotion/deploy prefixes and internal name tokens in IDs/slugs.
3. Explicit true flag and each of the five release kinds remain hidden for empty
   or whitespace-only q, and are discoverable by matching explicit search.
4. Synthetic evidence fields prove unchanged bytes/references for IDs, asks,
   steps, PR, flags, status and memberships. Clearly distinguish synthetic
   evidence from the two real public rows.
5. Replay all twenty accepted alias/chip/scope regressions and zero-fuzz/output
   hashes. Check JavaScript deltas with Git default whitespace rules.

Deliver a separate hash-bound source delta/freeze for independent review. No
commit, push, runtime application, service, process restart or cleanup.

## Result and reproducible local gate

```sh
node --test tests/js/dashboard-repository-aliases.test.mjs
LEGACY_RELEASE_VISIBILITY_BASELINE=1 node --test tests/js/dashboard-repository-aliases.test.mjs
```

Candidate: **26 PASS**. The second command applies the accepted alias/call-chip
patches without this fix: **22 PASS / 4 FAIL**, with zero skips in either run.
The twenty previous regressions and explicit release/search positives already
pass before the fix; the four failures reproduce ordinary-card visibility loss.
This is a local manual JavaScript gate, not a claim of JavaScript execution in
the existing Python CI workflow.

The [new manifest](../../src/orchestra/dashboard/legacy/release-visibility-manifest.json)
requires the exact reviewed prerequisite patches and binds `cb-state.js` after
R2 to its exact new output. Tests validate those bytes before and after zero-fuzz
application to fresh fixture copies. The generated helper, original alias and
call-chip patches/manifests, source fixtures and other JavaScript outputs are
unchanged. The only runtime code difference is the removed name-regex branch.

This does not edit or rebuild the separately served frozen browser baseline.
Source review does not authorize runtime application; the owner must recheck
the manifest's exact prerequisite/target hashes and run a separate served
candidate read-flow before claiming the visibility finding resolved live.
