# Codebase map

Operator workflow: [dashboard producer](../guides/dashboard-producer.md).

| Path | Responsibility |
| --- | --- |
| `src/orchestra/` | Python source extracted for review and reuse. |
| `src/orchestra/security/contracts.py` | P1 immutable stdlib envelope records and strict bounded wire codec; no scanner or gate execution. |
| `src/orchestra/security/profile.py`, `request.py` | Trusted bounded profile/context/runtime records and independently recomputed request/plan admission. |
| `src/orchestra/security/inventory.py`, `lock_metadata.py`, `js_metadata.py`, `yaml_loader.py` | Pinned Git inventory and bounded uv1-r3/pnpm9/npm3 metadata/graph coverage; no resolver or host marker pruning. |
| `src/orchestra/security/process.py` | Bounded trusted Git transport/state/closure helper and separate raw-byte NativeRunner; independent stream/file limits, hashes and explicit cleanup failure; no diagnostic redaction bypass. |
| `src/orchestra/security/runtime.py` | Executable identity and exact retained capability/provisioning/interpreter binding, rechecked at spawn and cleanup; no live authority provider. Process retains compatible explicit re-exports. |
| `src/orchestra/security/artifact.py`, `bootstrap.py` | Full installed-style manifest, parser-tree/license/provenance and loaded-origin verification before producer execution. |
| `src/orchestra/security/profiles/pilot-v1.json` | A catalog only: missing B native assets intentionally prevent activation. |
| `scripts/` | Legacy launcher/autospawn source, inert unless explicitly invoked. |
| `tests/unit/` | Unit, contract, guard, and synthetic-fixture tests. |
| `tests/unit/security/test_contracts.py` | Strict wire cases and the synthetic shared producer/consumer corpus, including nested lock scopes and Bandit batches. |
| `evals/synthetic/` | Non-production evaluation cases with no live data. |
| `.forgejo/workflows/ci.yml` | Forgejo lint, type-check, security, and tests. |
| `docs/specs/` | Approved issue-derived implementation contracts. |

There is no application database, service entrypoint, deploy automation, or
runtime data directory in this repository.

Checkpoint A adds foundations, not scanner adapters or a security gate. A valid
installed-style synthetic request reaches a fixed producer-unavailable exit2;
there is no success stub. The [checkpoint spec](../specs/2026-10-23-security-envelope-checkpoint-a-issue-189.md)
retains mandatory B→D adapters, consumer/policy, fenced evidence and exact-pair
CI. Synthetic subprocess tests do not certify immutable runtime mounts, OS
isolation, scoped registry coverage or live activation.

## Dashboard producer source

`src/orchestra/dashboard/` contains inert canonical title, note-lock, task-header,
card-text, provenance and quality helpers. Identity/collapse is a separate dormant
candidate; core export does not replace runtime grouping.
`scripts/dashboard_producer_title.py` requires an explicit root/item/title/phase;
`scripts/export_dashboard_producer.py` creates hash-checked review bundles outside
the donor tree and never applies them. See the
[producer contract](../specs/2026-10-27-dashboard-card-producer.md) and
[relative donor provenance](../provenance/dashboard-card-producer-20261027.json).

Public repository projection reuses `dashboard/repository.py` from ROOT, with no new registry. The existing exporter can produce one explicitly requested producer+repository compatibility bundle. Its fixed package inventory is21 (collector plus repository plus dormant M3S included). See `docs/specs/2026-10-27-dashboard-public-repository-projection.md`.
