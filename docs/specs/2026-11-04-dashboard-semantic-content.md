# Dashboard grounded PR descriptions

Approved SOURCE development/test/review scope from the 4 November resume and
parent assignment. Base `146aca2c0ed759fecf3265fcffeea5b71528641e` in the dedicated
semantic worktree. No runtime writes, imports, activation, merge or deployment.

## Requirements

- REQ-01: Pure bounded recovery receives already acquired PR objects. Select only
  the exact qualified current primary PR URL/number/repository; require source
  repository nameWithOwner/name consistency, reject identity conflicts and
  conflicting duplicate bodies, and reject conflicting heads when both exist.
  Dependencies, inferred item IDs and mixed reference text confer no authority.
- REQ-02: Parse at most 64 KiB UTF-8 markdown, explicit exact H2 Problem/Problema
  and Solution/Soluzione/Summary only, ignoring fenced headings. Prefer explicit
  Solution over Summary. Conflicting repeated applicable sections fail closed.
  Reject rather than truncate text beyond 1200 characters. Reject known token,
  email, credential header and environment assignment shapes; no freebody mining,
  translation, execution, raw body export or delivery/result certification.
- REQ-03: After curate, fill_text may recover only uncurated blank fields or
  exact technical-title fallbacks. Preserve meaningful and curated/edited text,
  including existing explicit-empty ordinary fallback policy. Missing PR
  evidence replaces only uncurated technical fallbacks with honest placeholders.
  Non-PR behavior stays unchanged. Authored content is visibly attributed as PR
  description, never confirmed deployment. Minimal per-field provenance contains
  current field hash, qualified URL and source-body hash only; stale provenance
  is removed. No work_provenance authority changes.
  `source_prs=None` means recovery is not wired and preserves ordinary behavior;
  an explicit empty list means wired without evidence. Blank fields without
  evidence keep ordinary fallbacks. Only exact-title fields get placeholders.
- REQ-04: Read-only quality reports technical title duplicates, missing grounded
  description and invalid/stale description provenance without changing cards.
- REQ-05: Narrow exporter changes only Ctx's default source_prs, build's metadata
  wiring, finish's fill_text keyword, canonical text/quality and new helper.
  Preserve the acquired list before existing all_prs last-wins deduplication as
  description input; preserve acquisition calls/order and assembly deduplication.
  Body-absent matching rows supply no evidence and do not shadow valid bodies;
  explicit bodies, identity and head conflicts still reject. Keep status/settle
  source byte-identical; suppress only generated empty-needs partial asks in the
  text layer after settle, retaining curated closure and genuine human signals.
  Bind copied current runtime and separately planned R1 donor
  hashes, preserve all other caller AST/bytes including publish and curation.
  Export is inert and rejects unknown vectors before creating output.
- REQ-06: Synthetic RED/GREEN tests exercise canonical and ordinary exported
  caller behavior, identity negatives, sensitive inputs, precedence, immutability
  and both donor compositions. Frozen offline Python3.12 deterministic quality,
  tests and security checks precede parent's independent Opus review.

## File manifest

| Path | Change |
| --- | --- |
| docs/specs/2026-11-04-dashboard-semantic-content.md | This SOURCE contract |
| src/orchestra/dashboard/descriptions.py | Pure bounded authored descriptions and field provenance |
| src/orchestra/dashboard/text.py | Post-curation recovery integration |
| src/orchestra/dashboard/quality.py | Read-only content findings |
| scripts/export_dashboard_semantic.py | Narrow pinned inert composition |
| scripts/export_dashboard_producer.py | Closed inventory addition only |
| tests/unit/test_dashboard_descriptions.py | Pure recovery, precedence and privacy cases |
| tests/unit/test_dashboard_semantic_export.py | Actual copied selected caller and status behavior |
| tests/unit/test_dashboard_semantic_boundaries.py | Acquisition/fixture pins, inert output preservation and adapter guards |
| tests/unit/test_dashboard_runtime_export.py | Exact inventory increase only |
| tests/unit/test_dashboard_ownership_caller.py | Exact module count increase only |
| tests/fixtures/dashboard_semantic/selected.py.txt | Selected static caller functions only |
| tests/fixtures/dashboard_semantic/status.py.txt | Static status source only |
| tests/fixtures/dashboard_semantic/manifest.json | Synthetic-fixture/source AST pins |
| tests/fixtures/dashboard_semantic/acquisition.py.txt | Selected static acquisition source with body/repository fields; never fetch |
| docs/provenance/dashboard-semantic-content-20261104.json | Relative before vectors, selected quality and both qualification implementation/dependency pins |
| docs/provenance/dashboard-card-producer-20261027.json | Refresh only current canonical text/quality hashes and new description helper; preserve acceptance and historical pins |
| docs/guides/dashboard-producer.md | Inert description composition contract |
| docs/codebase/INDEX.md | Module map |
| docs/codebase/test.md | Test map |
| CHANGELOG.md | Inactive SOURCE behavior |

## Phases and verification

1. Canonical recovery/text/quality → focused synthetic RED then GREEN.
2. Narrow adapters → copied current and R1 caller/status RED then GREEN,
   untouched AST and donor bytes, unknown vector rejection before output.
3. Documentation and deterministic checks → focused/unit, format/lint/type,
   security and diff checks; hold stable for parent's independent review.

The consumer preserves description text but currently ignores producer-only
`description_provenance`. Exact-title matching intentionally excludes clipped
titles and triage-augmented prose. Runtime quality is adapted only at findings()
and its import, preserving the reviewed older quality implementation.

Review amendment: explicit empty Solution remains authoritative over Summary
(absence is not inferred as permission to fall back). A single exact technical
field is sufficient for a read-only duplicate finding. Content findings retain
the existing severity rule: error for human-facing cards, warning otherwise.
The Ctx addition is incompatible with dormant closed shadow schema/callable pins;
shadow remains OFF and requires separately reviewed schema/profile updates.
Acquisition and fixture byte/AST pins are enforced locally without provider calls.
Export asserts untouched source/AST outside the declared edits before output.

Second review amendment: the finite credential filter includes generic token keys
in colon/equal forms and optional quoted credential keys. Both donor vectors must
also bind the exact read-only `bin/wi_sources.py`, `bin/wi_health.py` and
`bin/wi_release_links.py` source hashes from the copied acquisition evidence;
output remains four files. Synthetic tests independently inspect adapted build
ordering/deduplication and canonical app-ratio acquisition with a foreign-repo
negative. Qualification stays strict. No additional provider calls are made.

Third review amendment: add only `secret[_-]?key` to the finite credential-key
alternation, without arbitrary suffix matching. Prove identical acquired search
and merged-source bodies remain usable. Divergent raw body bytes still reject;
comparison of one real paired sample remains a preactivation check with no new
fetch authorized in this SOURCE task.
