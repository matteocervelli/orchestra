# Codebase map

| Path | Responsibility |
| --- | --- |
| `src/orchestra/` | Python source extracted for review and reuse. |
| `src/orchestra/security/contracts.py` | P1 immutable stdlib envelope records and strict bounded wire codec; no scanner or gate execution. |
| `scripts/` | Legacy launcher/autospawn source, inert unless explicitly invoked. |
| `tests/unit/` | Unit, contract, guard, and synthetic-fixture tests. |
| `tests/unit/security/test_contracts.py` | Strict wire cases and the synthetic shared producer/consumer corpus, including nested lock scopes and Bandit batches. |
| `evals/synthetic/` | Non-production evaluation cases with no live data. |
| `.forgejo/workflows/ci.yml` | Forgejo lint, type-check, security, and tests. |
| `docs/specs/` | Approved issue-derived implementation contracts. |

There is no application database, service entrypoint, deploy automation, or
runtime data directory in this repository.
