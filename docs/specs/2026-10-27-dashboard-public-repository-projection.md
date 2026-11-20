# Public repository projection and SOURCE composition

Approved parent scope: composition addendum ec4ab5ccfc9a4e43c5e5277ddee69dfa17a36310e0200df8587c940c8836a5af, review1c85d621085413b378361a09c99798e99ba406e3e4d1f295078887546ee7ff0c and parent acceptance20261028. Base2c40d2a8943667942bb69b9321d6265ff1eb812e already contains collector ec33. Import M3S commit cd2148b5e38ec24424aafc2e0ea1107e83899dc7 without committing; resolve only exporter/test/provenance overlaps. Its v4 frozen18 history remains authoritative and unchanged outside those overlaps. No runtime apply, operational build/readers, provider fetch, new dependency, commit/push or cleanup.

## Requirements

- REQ-01: reuse repository.py/repository_key byte-identically from ROOT. C1 removes exactly one trailing period before exact authority lookup. No extra aliases/casefold/trim/owner inference; FULL/REPOS/refs and qualified identity unchanged. Missing repo remains missing, None remains None, invalid type raises fixed invalid_repository_type.
- REQ-02: generated workitems.publish selects raw_items after all upstream processing. Immediately then create a list of outer dict copies, replacing only an existing repo field via repository_key. Preserve nested object identity without inspecting/copying nested payloads. All projected live/terminal records feed board/detail/archive; IDs/order/cardinality/status/asks/steps/flags/routes and nested references remain unchanged. Real generation/digest bind projected board/details.
- REQ-03: keep raw_live sidecar based on unchanged status. Existing single quality_audit stays at its exact publisher position and receives raw_live with original other inputs. quality._affected_item changes only emitted repo via repository_key; findings/severity/summary/your_call remain raw. main --check unchanged. Standalone same raw agrees; canonical board is different input and may change dotted-repo qualification warnings. Tests must demonstrate this difference.
- REQ-04: exporter package inventory exactly21: __init__,common,collector,curation,history,identity,notes,provenance,quality,repository,sources,text,titles,shadow,shadow_graph,shadow_prior,shadow_probe,shadow_profile,shadow_schema,shadow_store (Python) and shadow_profile_pins.json. Source/test expected lists are independent explicit inventories. Extra py is rejected; extra JSON excluded. Preserve M3S defaultOFF, callback/body behavior and byte pins; collector is already present, never reintegrated.
- REQ-05: explicit include_repository_compat option of existing build_bundle/CLI emits one merged bundle, not sequential applications. Reuse unchanged export_repository_compat.propose/validate_donors. Require absent repository helper and existing canonical common bytes, both compat pinned donor sources, and producer expected hashes against one original donor tree. Expected vector may include approved existing package Source paths; every existing package target must be hash-bound or generation blocks. No reading operational data. Colliding proposals must have byte-identical after and before; otherwise block before output. One repository helper after, correct before hashes, original donor unchanged. Core-only behavior remains available and identity candidate stays separate/non-ready.
- REQ-06: exact frozen identity/history/curation and seven shadow modules+pinJSON remain unchanged. All Source gates run on composed contents, Python3.12 existing venv, >=80 coverage, Radon<=B, Vulture80, quality/security/export/wheel. No claim of real consumer/runtime activation or corpus proof. Legacy908f remains separate; API/UI/legacy old-URL/callchips companion proof is a rollout gate, not implied by canonical output. No M3S activation or collector wiring.

## File manifest

Incremental10:

| Path | Responsibility |
|---|---|
| scripts/export_dashboard_producer.py | terminal publisher projection, explicit21 inventory, opt-in unified bundle guards |
| src/orchestra/dashboard/quality.py | emitted affected-item repo only |
| tests/unit/test_dashboard_repository_projection.py | new real generated publisher integration, invariants/C1/partition/digest/raw audit |
| tests/unit/test_dashboard_runtime_export.py | three-way exporter composition, inventory/helper/donor guard regression |
| tests/unit/test_dashboard_quality.py | raw audit parity and canonical-board difference |
| docs/specs/2026-10-27-dashboard-public-repository-projection.md | this contract |
| docs/provenance/dashboard-card-producer-20261027.json | truthful composed Source/donor hashes |
| docs/codebase/INDEX.md | reuse map |
| docs/codebase/architecture.md | terminal/public and raw audit boundary |
| docs/codebase/test.md | regression map |

Additionally import exactly the18 paths in M3S freeze20f99874292ba2c36f4dcedcd2b7b48b73607a916d1878d3b18a2db52a891164. Only exporter, runtime_export test and provenance overlap with incremental10, total25 distinct modified/new paths. ROOT repository helper/test and compat exporter/provenance remain base dependencies byte-identical. No other files without prior manifest amendment.

## Phases and validation

1. Materialize spec/readiness; import M3S with no commit; resolve overlap explicitly and verify immutable business/shadow/helper bytes.
2. Behavioral RED through actual generated publish and quality (no separate projection implementation); GREEN for C1 matrix, all outputs, nested referents/input, raw audit once at original position. Nonempty synthetic Himalaia fixture retains YourCall9+3+0=12.
3. Exporter21 inventory and merged proposals RED/GREEN, same before vector, absent helper, drift/duplicate/conflict failure atomicity, unchanged REPOS/REPO_STEPS/outside target bytes. Temp/synthetic donor only. M3S tests remain real Source callbacks, no stubs or corpus-as-full-proof.
4. Full unit/coverage, format/lint/types/Radon/Vulture, scoped security, final offline wheel/package bytes, source freeze/patch/report. STOP for independent parent-owned composition review. No commit/push/apply.
