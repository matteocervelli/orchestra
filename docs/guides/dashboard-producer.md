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


### Explicit historical ownership (F1 SOURCE milestone)

The inert canonical `groups` and `collapse` APIs accept keyword-only
`historical_bindings`. Omit it to retain the previous API behavior. Pass an
explicit sequence (including `[]`) to preserve new raw IDs and apply only
reviewed source ownership, for example:

```python
bindings = [
    {"kind": "task", "key": "employee-task", "owner": "opaque-old-card"},
    {"kind": "pr", "key": verified_primary_url, "owner": "opaque-pr-card"},
]
mapping, identities = groups(items, notes, tasks, pr_issues,
                             historical_bindings=bindings)
```

`verified_primary_url` must be the exact qualified source PR URL with verified
host/owner/repository/number. These records come from a coherent previous public
snapshot supplied by the caller; task prose, bare numbers and dependencies do
not establish ownership. The package never loads bindings itself. Same-source
multiple owners, unrelated target collisions, conflicting primary/protected
values or aliases reaching another curated owner raise
`HistoricalBindingConflict` before assembly mutation. The exception exposes
`reason`, `source` and `owners`; callers must retain that diagnostic and block
activation rather than catch it and fall back to inference. Different published
owners remain separate even with the same PR, and an absent raw target is created
so its historical note and exact-ID link remain reachable.

This SOURCE milestone does not activate identity, wire a runtime caller, migrate
notes, normalize repository filters or project qualified result metadata. The
bounded frozen Nexus replay proves324/207 ownership and note reachability only.
Full same-generation pre-collapse child-card/ask/step/flag and live/archive action
compatibility still require a separately reviewed sanitized capsule. Capture is
not implemented and no live hook is installed.

## Explicit shadow handoff (SOURCE only)

The default exporter does not wire the observer. `shadow_adapter` prepares an
explicit dormant transformation of a reviewed already-core caller, including
its existing main. Applying or invoking that caller requires ROOT's separate
hash, ownership and one-run approval; this Source API is not activation.

`main(shadow_request=None, shadow_prior=None, shadow_witness=None)` keeps the
normal CLI OFF. True/False are invalid requests, not flags. `--check` never
creates an observer or consumes a request. There is no requestfile/env watcher
or boolean CLI switch. In a requested run, the same observer reaches build and
publish, actual loaded profile admission happens after consume at the real
asm/ctx boundary, baseline/publish each run once, and main returns the original
seal CommitResult privately. Capture does not replace normal producer output.

ROOT supplies two complete verified preceding public publications and their
byte lengths/SHA plus canonical board digest. `project_prior_publications`
projects only ownership metadata to PriorBindingInput; it does not read files,
verify byte claims or create a witness. ROOT constructs PriorWitness referencing
that exact object after its independent verification. Missing slugs, unknown or
conflicting owners, foreign PRs, stale/incomplete prior and forbidden fields
block; current expected output, pr_no/links/children are not surrogate authority.
Known rich fields are ignored without reading their values; this metadata
projection does not claim that a rich postgraph or consumer has been replayed.

Keep the first actual CommitResult in the same process. Only COMMITTED with its
original capability may enter `read_receipt(request.directory,result.receipt)`;
JSON or dataclasses.replace without that capability is rejected. A shallow copy
that retains it is not promised rejection. NOT_COMMITTED/COMMIT_UNKNOWN never
become PASS from file presence; no retry, overwrite or cleanup. Generation and
digest come from the successful final publish. Shared metadata must first pass
ROOT's local schema/privacy scan. No roots, report/tasktext, secrets or native
paths are emitted. See the [M4 amendment](../specs/2026-10-27-dashboard-shadow-m3s.md).
