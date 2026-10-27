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

## Declare the task's primary subject

Place exactly one metadata block immediately after the task heading, with only
blank lines in between. Do not supply `source` or `validation`: the reader assigns
origin. For a local review, name the actual artifact being reviewed. This example
refers to the existing producer contract in this repository:

````markdown
# Rivedere il contratto del produttore delle card

```json orchestra-task-meta
{"schema":"orchestra-task-meta/v1","work_provenance":{"kind":"local_artifact_review","subject":{"repo":"orchestra","artifact":"docs/specs/2026-10-27-dashboard-card-producer.md"},"relation":"primary"}}
```
````

Use that role only when the primary deliverable is this artifact review. Do not
relabel integration work to suppress a missing-PR warning. Classification does
not certify review, merge, delivery or an independent approval.

For primary integration, first obtain a current, checked PR receipt with exact
host, owner/repository, integer number and matching URL. The following builds the
same accepted task block from that verified object, without inventing a PR:

```python
import json

from orchestra.dashboard.provenance import parse_task_provenance, qualified_pr

# canonical_repo and verified_primary come from the checked receipt.
primary = qualified_pr(verified_primary, canonical_repo)
if primary is None:
    raise ValueError("Receipt does not match the configured repository authority")
metadata = {
    "schema": "orchestra-task-meta/v1",
    "work_provenance": {
        "kind": "primary_integration",
        "subject": {"repo": canonical_repo, "pr": primary},
        "relation": "primary",
    },
}
task_text = (
    "# Integrare la correzione dei titoli delle card\n\n```json orchestra-task-meta\n"
    + json.dumps(metadata, ensure_ascii=False)
    + "\n```\n"
)
_, errors = parse_task_provenance(task_text)
if errors:
    raise ValueError(errors)
```

The qualifier validates shape and the explicit configured owner/project list; it
does not fetch a repository or prove PR existence, approval or completion. A
Forgejo repository under another namespace is a separate relationship requiring
its own verified scope; this registry does not rewrite or authorize that owner.
Display aliases and bare task/card numbers remain insufficient primary evidence.

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
Verify the whole assembly → note merge → exact-ID consumer path: grouping tests
alone do not prove that an upstream assembly retained a historical curated ID or
its note/pin. The identity candidate remains blocked on that integration proof.
The operational identity compatibility audit reproduced a loss before collapse;
a positive check on already-collapsed cards cannot replace that baseline. A next
review needs an authorized, sanitized pre-collapse capsule with extracted cards
only (never session logs) and baseline/candidate ask, step and route comparisons.
Launcher lifecycle hooks and real caller adoption also remain separate from a
rendering update. No bundle or draft PR authorizes merge, deploy or cutover.

## Validate a source revision

Shared CI checks Vulture at confidence 80, Radon grade B or below (including
closures), and Python 3.12 unit tests with at least 80% branch-aware coverage.
Tests distinguish text fallback, explicit choices, qualified references and bound
detail enrichment; a structural pass still does not establish semantic freshness.

A source refactor does not rewrite an installed runtime package. Previously
reviewed runtime composition remains a separate snapshot with its own hashes;
source CI or PR approval does not authorize a new runtime export/application.
