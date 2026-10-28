# Repository keys at preview and action boundaries

Pure SOURCE preparation only. No runtime apply, preview, process, action, provider,
registry edit or publication. The isolated checkout starts at ec33bdb.

## File Manifest

- `src/orchestra/dashboard/repository.py`: shared pure key and boundary adapters.
- `scripts/export_repository_compat.py`: bounded three-target proposal exporter,
  reusing the existing AST replacement utility without editing that exporter.
- `tests/unit/test_dashboard_repository.py`: finite-domain and adapter tests.
- `tests/unit/test_repository_compat_export.py`: synthetic donor/delta tests.
- `tests/fixtures/repository_compat/preview_recipes.py`: original normalizer and
  full new_entry function AST, with explicit synthetic recipe/dependency data.
- `tests/fixtures/repository_compat/action_dedupe.py`: original scope/matching
  function AST, with explicit synthetic index/activity dependencies.
- `tests/unit/test_dashboard_runtime_export.py`: only module inventory 12→13.
- `docs/specs/2026-10-27-dashboard-repository-runtime-compat.md`: this contract.
- `docs/provenance/dashboard-repository-runtime-compat-20261027.json`: own receipt.

The existing producer export inventory assertion gains only the additional
inert module count 12→13, after the isolated inventory RED and root approval.
No common/FULL/REPOS, producer exporter, other worktree or runtime edits.

## API and invariants

`repository_key(value: str | None) -> str | None` delegates only to the existing
common.repository_authority, after removing at most one final period. Known
authority becomes its bare canonical name. Unknown/foreign/case/whitespace and
qualified short aliases remain their original literal values. None/empty remain
unchanged; other types raise the fixed invalid_repository_type error. No copied
registry or table and no inference from URLs, item IDs, PRs or free text.

`preview_item(item, recipes)` returns the original item when absent, malformed or
unsupported; otherwise a shallow outer copy with only repo replaced. The supplied
recipe allowlist is unchanged. Existing four runtime recipes remain four; this
normalization grants no additional recipe, variant or lifecycle operation.

`normalize_action_scope(step, scope)` canonicalizes a repo: suffix only for the
existing promote/release intents. Item scopes and release_prepare/deploy snapshot
digests remain literal. Runtime scope_of uses the same key for repo scopes;
find_active normalizes the requested comparison scope in memory, preserving old
records, item IDs, text/status/answers and lifecycle checks.

The exporter reads explicit static donor files only, requires the dependency
common bytes to match SOURCE, and emits before/after hashes plus a patch for
exactly bin/orchestra_dashboard/repository.py (new), bin/preview_recipes.py
(normalize_item only), and bin/action_dedupe.py (scope_of/find_active only).
Existing helper target, unexpected function shape or authority drift fail closed.
Before transformation or output creation, both complete donor modules must match
the exact before_sha256 pins in this SOURCE provenance receipt. This also binds
the original REPO_STEPS and REPOS keys/name/gh relationships without a new table
or runtime import. Any body, global or unrelated donor-byte drift is rejected as
runtime_donor_drift. The pure propose utility can use approved synthetic donors
in tests; build_bundle/CLI always validate the donor pins before calling it.
All bytes and AST outside target functions must remain identical. No application
or import of live modules; output is a proposal for root review and future pins.

## Acceptance

REQ-01: test the existing twelve canonicals, four bare aliases, same-owner
qualified canonicals and one period, idempotence, literal unknown/foreign,
qualified aliases and multiple periods; no input mutation.

REQ-02: reproduce preview short-alias failure before code, then prove real
proposed normalizer and synthetic new_entry consume canonical recipes without
processes; preserve allowlist and recipe conditions.

REQ-03: reproduce raw versus canonical promotion/release mismatch, then test both
comparison directions, old action records and exact item IDs; preserve special
shipping snapshot scopes, unrelated steps, timestamps and records.

REQ-04: hash-bound three-target export with dependency/source hashes, rejection
on whole-module donor or dependency drift, exact outside-function bytes/AST,
synthetic adapters only; no apply. Regression mutations cover normalizer and
matching bodies, REPO_STEPS extension and recipe owner changes before any output.

REQ-05: frozen offline Python 3.12 TDD, focused then full relevant unit suite,
quality/security/readiness, freeze and independent review before persistence.
