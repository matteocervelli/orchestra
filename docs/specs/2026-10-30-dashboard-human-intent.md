# Dashboard author intent (inactive SOURCE)

Base: `12bebeb5a3f1ea718ff42b07ead08f13ec292d52`.

## Contract

- REQ-01: A note/card author may attach `needs_intent: {"kind": "information",
  "text": "<exact needs>"}` or kind `request`. Select this metadata from the
  same source that wins `needs`, including pin and `edited_fields` precedence.
  Missing, malformed or stale metadata retains legacy behavior. Never infer
  information from rejection words, status, child exit, or an answer.
  Accept exactly these two scalar fields; unknown keys reject the declaration
  rather than projecting arbitrary payload into a public card.
- REQ-02: A matching information declaration removes only the needs-derived
  question and its caller fallback. Explicit asks and decisions retain order,
  IDs, kind, links, options, owners and answer semantics. Do not write `ask=[]`
  to a note or change lifecycle state. Changed needs and later explicit asks
  remain eligible without clearing old metadata. Independent open PR
  `needs-human` and triage `done?` gates retain the existing concrete request
  text from `needs_of`, not the informational needs text.
- REQ-03: Move the existing caller's ask classifier and its CALL_KINDS/ACTION_RE
  dependencies to canonical text helpers. Keep explicit kind, decision call,
  merge, action and UI precedence. Infer mockup approval only from a bounded
  positive approval request in the question; recommendations and an incidental
  mention of mockup do not establish approval. A rejection may precede a real
  question about a new mockup. Unsupported wording remains an answerable decide
  ask; authors can supply the explicit kind. Inference accepts sentence-start
  approvi/approvate/approvare, confermi/confermate/confermare,
  accetti/accettate/accettare, validi/validate/validare with optional il/questo/un
  and nuovo before mockup. At most 2000 characters and 16 sentence fragments;
  longer text retains decide without partially scanning a truncated question.
- REQ-04: Export only hash-bound donors, fail on missing/duplicate classifier
  bindings, and test the emitted finish/asks/enrich/classifier path. No runtime
  reads beyond source code, runtime apply, fetch, lifecycle normalization or
  changes to unrelated SOURCE lanes.

## File manifest

- `src/orchestra/dashboard/text.py`
- `src/orchestra/dashboard/curation.py`
- `scripts/export_dashboard_producer.py`
- `tests/unit/test_dashboard_ownership_caller.py`
- `tests/unit/test_dashboard_runtime_export.py`
- `tests/unit/test_dashboard_human_intent.py`
- `docs/provenance/dashboard-card-producer-20261027.json`
- `docs/guides/dashboard-producer.md`
- `docs/specs/2026-10-30-dashboard-human-intent.md`
- `CHANGELOG.md`

## Validation and activation boundary

RED regression first, then focused unit/export/caller checks, formatting, lint,
strict types and security checks. Parent owns the independent review handoff.
Expected semantic runtime delta from SOURCE V2: canonical text/curation and the
wi_fields adapter (three files). Existing V2 workitems asking plumbing is reused.
SOURCE alone cannot retroactively classify the
three unmarked Ratio rejection notes or clear the nineteen reported human-card
errors. Their current author/root must adopt exact-text metadata separately.
