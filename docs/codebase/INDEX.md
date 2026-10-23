# Codebase map

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
