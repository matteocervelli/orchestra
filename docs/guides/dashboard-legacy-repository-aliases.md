# Legacy repository alias compatibility

This inert companion makes historical repository aliases select the same cards
as canonical repository keys in the legacy dashboard. It does not install or
activate itself. The [manifest](../../src/orchestra/dashboard/legacy/manifest.json)
binds the exact donor code, patch, generated JavaScript and Native TypeScript
source. No producer, grouping, dependency or workflow changes are included.

The finite key domain has twelve canonical repositories, four bare aliases,
the registered owner's qualified canonical names, and exactly one trailing dot
on each registered key. Unknown owners, qualified short aliases, case changes,
whitespace and multiple trailing dots remain literal. URL CSV parsing retains
its existing whitespace trimming. Text queries retain their existing lower-case,
accent-insensitive, all-terms semantics; a whole registered repository query
additionally matches equivalent repository memberships.

The patch changes three consumer files:

- `cb-state.js`: URL repository selection, matching, deduplicated facet counts
  and repository sorting compare canonical keys.
- `cb-toolbar.js`: options include secondary memberships, combine equivalent
  repository keys, and use the same comparison for their total denominator.
- `cb-dedupe.js`: promotion/release scope comparisons normalize repository
  keys, including existing `repo:` scopes, without changing action rows.

The actual call chain is board `setTakenTest` → `blockFor` and `activeBlocks`;
bulk planning also consumes `scopeOf` and `blockFor`. These callers, grouping
algorithms and action payload builders are unchanged. Repository arrays, exact
card IDs, asks, steps, flags and evidence are never projected or rewritten.
Existing text caches are preserved; the pre-existing lazy `_hay` creation on
ordinary text queries remains unchanged.

## Local behavior gate

From the repository root, with Node 24 and `patch` available:

```sh
node --test tests/js/dashboard-repository-aliases.test.mjs
LEGACY_BASELINE=1 node --test tests/js/dashboard-repository-aliases.test.mjs
```

The first command must pass. The second intentionally reproduces the original
failures against the same pinned donor modules. Each run creates a fresh copy
under the repository's ignored `.pytest_cache`; it verifies hashes before
applying the patch with zero fuzz, then verifies candidate hashes. All eleven
dependency modules are static source, with no runtime data or HTML snapshots.
The `cb-toolbar.js` donor has an existing blank line at EOF; its fixture is stored
as a lossless JSON string in `assets/cb-toolbar.js.json`. The test decodes that
one file and verifies its original JavaScript digest before applying the patch.
The toolbar test substitutes only the DOM boundary and runs its real render,
options, counts and predicates.

The exact generated patch path has a `.gitattributes` whitespace exception for
blank end-of-line/end-of-file checks: unified-diff context represents an empty
source line as a single space. The Node gate checks the donor-to-candidate
JavaScript deltas and the whole generated helper with Git's default whitespace
rules. This does not certify inherited donor whitespace as clean. No source
code, fixture or other patch path receives that exception.

This is a **manual local JavaScript gate**. The current Forgejo workflow invokes
shared Python jobs and does not establish availability of Node. No pytest
wrapper, skip, new dependency or workflow has been added. Python CI passing
does not claim that this JavaScript suite ran in CI.

## Reproduce the generated helper

`tests/fixtures/dashboard_legacy/repositoryFilter.ts` is a byte-identical pinned
copy of the reviewed Native helper named in the manifest. It is upstream source
evidence, never a separately maintained mapping. Refresh it only from a reviewed
Native revision and regenerate the JavaScript; do not hand-edit either registry.
Use an explicitly supplied TypeScript 5.9.3 compiler:

```sh
node "$typescript_cli" tests/fixtures/dashboard_legacy/repositoryFilter.ts \
  --target ES2022 --module ES2022 --strict --skipLibCheck \
  --outDir .pytest_cache/legacy-ts-reproduce
node --input-type=module <<'JS'
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const generated = readFileSync('src/orchestra/dashboard/legacy/repository-filter.js', 'utf8');
const emitted = readFileSync('.pytest_cache/legacy-ts-reproduce/repositoryFilter.js', 'utf8');
assert.equal(generated.split('\n').slice(3).join('\n'), emitted);
JS
```

The three generated header lines record origin, source SHA-256 and compiler
options. The manifest also binds the complete generated artifact digest.

## Separately authorized rollout

Before composing a runtime candidate, its owner must compare the three donor
hashes **and all pinned dependency hashes** with the actual target, and recheck
the Native helper source hash against its final reviewed freeze. Drift requires
reconciliation and another review. The patch paths are relative to the target's
static-page directory (`assets/...`); the helper destination is recorded in the
manifest. Neither this guide nor running the tests authorizes applying them.

After a separately reviewed application, verify old and new repository URLs,
Board/Table filters, facet totals, exact-ID drawer links and taken/action scope
behavior through the served consumer. No live browser or HTTP proof is provided
by this source companion. Source publication projection remains separate.
