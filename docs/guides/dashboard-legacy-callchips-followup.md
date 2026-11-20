# Legacy Your call repository chips follow-up

Authoring manifest (before implementation): add one runtime target,
`assets/v3/callchips.js`, as a separate hash-bound patch and manifest under
`src/orchestra/dashboard/legacy`. Add only its two static donor modules
`v3/callchips.js` and `v3/ui.js` to the existing fixture dependency closure,
extend the actual-module Node test and document the action-payload call chain.
The R2 runtime patch, generated helper and original manifest stay unchanged.

Verification: run the existing R2 patch without this follow-up and reproduce the
9 canonical / 2 short / 1 single-dot split; apply the follow-up only to fixture
copies and verify one count-12 chip, canonical toggle/pressed/summary semantics,
multi-membership deduplication and unchanged cards/asks/action scopes.

Bulk inspection is read-only and hash-bound: inspect the actual scopeOf → local
Map → buildAction → plan.payloads → sendAction caller chain. Do not POST or add
action modules to the test closure unless required by these chip tests.

## Result and local gate

The separate [manifest](../../src/orchestra/dashboard/legacy/callchips-manifest.json)
binds the one target, two donor dependencies, new patch and the actual unchanged
caller sources inspected. The existing generated helper is reused unchanged.

```sh
node --test tests/js/dashboard-repository-aliases.test.mjs
LEGACY_CALLCHIPS_BASELINE=1 node --test tests/js/dashboard-repository-aliases.test.mjs
```

The first command runs R2 plus this patch: 20 PASS. The second applies R2 only:
14 PASS, 6 FAIL, including the mixed 9/2/1 chip-count regression. Neither command
skips tests. The `LEGACY_BASELINE` switch remains the original whole-donor test.
These are explicit local JavaScript checks, with no claim that Python CI ran them.

Repository chip counts, selected/pressed state, summaries and click toggles use
canonical comparison keys. Counts follow the existing board filter's membership
rule: use `repos[]` when nonempty, otherwise the primary `repo`, counting each
logical key once per card. This makes a chip's count match the cards its click
shows. It does not change primary ownership, grouping, raw memberships, asks or
action records. Kind chips retain their own existing matching rules. Unknown and
foreign repository names remain literal. Existing raw selections are projected
only into local comparison values during render; an actual click canonicalizes
the repository selection before toggling its logical key.

The Node harness verifies original donor hashes, applies each patch with zero
fuzz, and verifies exact outputs. It also checks donor-to-candidate whitespace
deltas for all four JavaScript targets and the whole generated helper. The exact
new generated-patch path has the same limited unified-diff context exception as
R2; no fixture/source code path receives an exception.

## Actual unchanged caller paths

`v3/board.js:260` renders `callChips(pool, state)` for Board/Table.
`v3/groups.js:103` passes the clicked data attribute into `chipClick` inside the
existing update callback. Those caller files are unchanged and hash-bound.

For action planning, `v3/bulk.js:33` obtains a scope through the shared
`scopeOf`/`blockFor` helpers. It uses that scope only as a local `seen` map key,
then calls `buildAction("dispatch", it, "")` with the original card. The returned
`plan.payloads` are selected from those action results. In
`cb-actions.js:33`, default `buildAction` returns `kind`, original `item.id` and
`text`; attachments are an optional existing field. It does not return scope.
`v3/bulk-ui.js:123` forwards each planned payload to `sendAction`, optionally
adding selected attachments. `cb-actions.js:131` calls `recordRequest`, and
`answer-editor.js:217` serializes the supplied record without synthesizing a
repository scope. Thus the R2 normalization changes comparison/deduplication,
not the action payload shape. No POST, dispatch or live action was performed.

The static hashes record what was inspected; they do not replace post-application
browser/HTTP checks or authorize rollout. Independent review and an owner hash
recheck remain required. The R2 frozen deliverable remains a separate prerequisite.
