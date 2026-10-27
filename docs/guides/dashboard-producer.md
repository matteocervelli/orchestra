# Dashboard producer

These helpers keep card text and provenance consistent without changing the
dispatcher, approval state or open questions. They are source for an external
runtime consumer; importing the package never starts services or discovers a
runtime directory. See the [repository boundary](../../README.md#runtime-boundary)
and the [implementation contract](../specs/2026-10-27-dashboard-card-producer.md).

## Author a new task

Supply a specific Italian title describing the subject and intended change.
Before the already-authorized spawn, invoke the installed helper with literal
arguments and the explicit runtime root:

```sh
python3 bin/dashboard-producer-title.py --root "$runtime_root" \
  --item "$task_slug" --title-it "$task_title" --phase start
```

The caller must stop that new launch if validation fails. The helper prints
`written` or `preserved`; its output is text, not JSON. It locks the notes file
for the whole transaction, fills only a missing title, and preserves an existing
nonblank `title_it` or `title` and all other note fields. Do not use a task slug,
model name or generic fallback as the title.

Ensure the actual child prompt or task explicitly requires reading COMMON.
At delivery, call the same helper with `--phase complete` and the same task ID.
This validates metadata; it neither proves successful implementation nor changes
approval or completion state. Do not modify already-running tasks to manufacture
adoption evidence. Confirm real caller adoption with new-task receipts; the
presence of this CLI alone does not provide universal prevention.

## Preserve curated text

Nonblank note titles win even without `pin`. For other text keys, a value present
in both the note and `edited_fields` wins over an older child report. Fields not
explicitly edited retain the existing card/pin precedence. An edited empty value
removes stale child text, then the ordinary title/status fallback can fill the
projected field; the final projection need not remain an empty string.

Normal heading parentheses are preserved. Only the exact legacy wrapper
`# Task: filename-slug (goal)` extracts its goal, keeping inner parentheses.
A different slug does not establish that wrapper.

`duplicate_ask_id` reports a nonempty ID repeated among open asks. It retains all
asks, does not answer them, and excludes already-answered entries from that check.

## Interpret quality evidence

A local artifact review can omit a primary PR only with valid task/note
classification and no contradictory evidence. A child report cannot declare
itself trusted; a present but invalid declaration keeps the warning. Structural
success does not prove that approvals or requests are current. A merge alone
does not satisfy an independent visual or activation request.

Published details bind the exact item ID, microsecond generation and public-board
digest. Missing, stale or mismatched detail evidence cannot grant an exemption.
Board state and asks remain authoritative. Consumers must accept the existing
timestamp field with fractional seconds.

## Compose a reviewed update

The exporter requires an explicit donor root and new output directory. It checks
the pinned donor hashes, exports the canonical package byte-for-byte and produces
an exact patch plus before/after hashes. It never applies the patch. When updating
an already-applied bundle, use `--against-applied-bundle` and hand off `delta.diff`,
not the original donor-before patch. Recheck every target hash before and after
the runtime owner's application; drift requires reconciliation, not a blind fix.

Validate generated adapters as well as canonical source: the consumer Ruff check
must add no findings. The existing `E741` on `wi_common.O` remains a disclosed
legacy finding, not a globally suppressed rule. Explicit re-exports preserve the
consumer API. Verify served curated fields and legacy task headings afterwards.

The default core does not replace identity/dedupe adapters. Their optional
candidate requires a separate identity dry run and proof that old exact-ID links,
asks, steps, priority and answers survive; retaining aliases alone is insufficient.
Launcher lifecycle hooks and real caller adoption also remain separate from a
rendering update. No bundle or draft PR authorizes merge, deploy or cutover.
