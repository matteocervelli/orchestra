# Dashboard history publisher R1

Approved SOURCE implementation amendment for accepted interface R1 SHA256
`2774d05a3b1be326ae2d3d6b1f4bf0c3ce00e9ac2c8c7deea269df2b4797463f`.
The 4 November development resume authorizes development, test and review only.
R1 remains unchanged. No runtime application, merge, deploy, cleanup, identity,
curation or historical business launch is authorized.

The dedicated worktree uses approved SOURCE composition base
`152ccfe30a776c807cb7c858c3072380dfd3ab14`, rather than the generic integration
default, to preserve the already accepted producer stack. The operational donor
is inspected as static source only; tests and exports use isolated copies.

## Requirements

- REQ-01: Add fixed `work-items-history-index.json`, version exact integer 1,
  canonical UTC microsecond generated, canonical public-board SHA256, statuses
  and ordered terminal items. Terminal status membership is case insensitive.
- REQ-02: Project through the existing `_public_item`, then restore all present
  `id,title,status,repo,kind,issue,pr,priority,priority_src,order,updated,your_call,
  call_kind,ask,steps,links,gates,blocked,agent,taken,child,slugs` and hidden/hide
  values exactly, including empty/None/False values. Absent fields stay absent.
  Terminal `your_call` must be explicitly boolean; no inference or normalization.
- REQ-03: Before any directory creation or write, validate generation, statuses,
  all active/terminal/detail IDs, uniqueness, disjointness, exact public/detail
  membership and stamps, and index schema. Every active and terminal card must
  contain a string status; missing and non-string statuses are rejected before
  any directory creation or write. The statuses metadata remains list[str].
  All details and the index must fit
  10*1024*1024 inclusive bytes in actual compact UTF-8 writer serialization;
  reject cap+1, nonfinite JSON and malformed inputs. No file is deleted.
- REQ-04: Preserve full raw archive and rich stamped details, using the same
  generated/digest as public. Preserve detail → raw archive → quality → index →
  active write order. Default publisher entrypoint remains `publish(data,out)`.
- REQ-05: New narrow inert exporter binds exact copied current caller and quality
  dependency hashes, verifies reviewed publish shape and canonical digest/stamp
  helper compatibility, changes only publish plus a helper import, and exports
  only caller plus byte-identical canonical history helper. Unknown/unsafe donor
  vectors and preexisting new helper fail before output. No donor is executed,
  imported or modified. Broad exporter is not used for runtime composition.
- REQ-06: Deterministic synthetic RED/GREEN tests, source lint/type/security and
  documentation; parent coordinates mandatory independent review and combined
  proof against the published Atrium consumer. No SOURCE tests claim activation.

## File manifest

| Path | Change |
| --- | --- |
| `docs/specs/2026-11-04-dashboard-history-publisher-r1.md` | This approved SOURCE-only amendment |
| `src/orchestra/dashboard/history_index.py` | Canonical projector and publication preflight |
| `scripts/export_dashboard_history.py` | Narrow hash-bound inert caller adapter/export |
| `scripts/export_dashboard_producer.py` | Add helper to closed package inventory only |
| `tests/unit/test_dashboard_history_index.py` | Projection/schema/byte bounds regressions |
| `tests/unit/test_dashboard_history_export.py` | Ordinary exported publisher and export boundaries |
| `tests/unit/test_dashboard_runtime_export.py` | Extend existing exact inventory assertion to 25 |
| `tests/unit/test_dashboard_ownership_caller.py` | Extend composed Python-module count from 23 to 24 for the new helper |
| `tests/fixtures/dashboard_history/workitems_selected.py.txt` | Static selected donor code, no runtime data |
| `tests/fixtures/dashboard_history/manifest.json` | Fixture source hash and selected symbol provenance |
| `docs/provenance/dashboard-history-publisher-r1-20261104.json` | Relative static donor pins |
| `docs/guides/dashboard-producer.md` | Review/export workflow and finite cap |
| `docs/codebase/INDEX.md` | Helper/export map |
| `docs/codebase/test.md` | Focused validation map |
| `CHANGELOG.md` | Inactive SOURCE behavior |

## Phases and verification

1. Canonical projection/preflight → focused synthetic tests RED then GREEN.
2. Narrow ordinary-caller export → isolated copied-donor tests RED then GREEN,
   exact outside-publish byte preservation, failure before writes and bundle output.
3. Docs and deterministic validation → focused and unit suites, ruff, strict mypy,
   security and diff checks. Parent runs independent review and combined consumer proof.
