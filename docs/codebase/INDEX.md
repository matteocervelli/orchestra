# Codebase map

| Path | Responsibility |
| --- | --- |
| `src/orchestra/` | Python source extracted for review and reuse. |
| `scripts/` | Legacy launcher/autospawn source, inert unless explicitly invoked. |
| `tests/unit/` | Unit, contract, guard, and synthetic-fixture tests. |
| `evals/synthetic/` | Non-production evaluation cases with no live data. |
| `.forgejo/workflows/ci.yml` | Forgejo lint, type-check, security, and tests. |
| `docs/specs/` | Approved issue-derived implementation contracts. |

There is no application database, service entrypoint, deploy automation, or
runtime data directory in this repository.
