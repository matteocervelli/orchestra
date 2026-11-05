# Dashboard project ownership — inactive SOURCE implementation

Base: `6d9969e46b8056e1e1b792d883a7c25a365ddbab`.
This contract changes display ownership only. No runtime activation, identity
resolution, card grouping, bookmark, alias, PR object, question, pin, workflow
state, collector, provider, database or Atrium authority is changed.

## Evidence and minimum manifest

`tests/fixtures/dashboard_ownership/manifest.json` pins the two selected code
donors and their extracted AST fixtures. The reproduction executes only selected
pure assignments/functions from `wi_repos` with canonical `common` constants,
and the two selected `finish` ownership boundaries with synthetic arguments.
It never imports a donor module or executes operational build/publish/export.
Synthetic emitter/composition tests build inert bundles in test directories.

Implementation paths:

| Path | Minimum responsibility |
| --- | --- |
| `src/orchestra/dashboard/ownership.py` | Canonical pure ownership helper derived from the pinned donor |
| `scripts/export_dashboard_producer.py` | Existing exporter: canonical compatibility adapter and guarded `finish` edits |
| `tests/unit/test_dashboard_ownership.py` | Synthetic semantic regressions and input preservation |
| `tests/unit/test_dashboard_runtime_export.py` | Synthetic exported-caller compatibility; no live exporter call |
| `tests/unit/test_dashboard_ownership_caller.py` | Complete emitted finish with selected real page/link/curated-ask functions |
| This spec and the ownership fixtures | Contract, selected donor evidence, test receipt |

Do not create another exporter, registry or identity authority. Do not edit
runtime `bin` files. Do not compose another lane's exporter changes in its WT.

## Ownership evidence

The proposed order preserves the donor's existing explicit declaration order:

1. Latest positive child `card.repos`, then positive current `card.repos`, then
   positive curated `note.repos`; preserve order, aliases and deduplication.
2. Legacy positive explicit `card.repo` or `note.repo`, as in the donor.
3. A structurally qualified primary PR object in `it.pr`: reuse `qualified_pr`
   and existing repository authority. URL host, owner, repository, PR number
   and any supplied host/repo fields must agree. This is local validation of
   supplied evidence, not a network verification or promotion of a cited URL.
4. A positive task source assignment matching the bounded grammar below.
   A `Repo(s):` heading is sufficient, but is not necessary: an assigned
   source worktree or named source directive also establishes ownership.
   A mathematical use of `ratio` outside a declaration contributes no
   ownership. Collect positive declarations in task/line order.
5. Otherwise UNKNOWN: return `[]`.

Parent adjudication preserves that declaration precedence. The 24 curated
`note.repos` values persist when child/card do not declare another scope; do
not resolve a new explicit conflict by inferring ownership. No curated note
is mutated. Promoting notes above all explicit child/card declarations would
be a separate precedence decision.

Dependency/reference URLs, issue objects, non-primary `it.prs`, child
`repo_refs`, ledger notes/gates, generic task prose, a launch directory and the
pre-existing scalar `it.repo` do not establish display ownership. Preserve the
reference extraction API for consumers that display citations; stop using its
results as ownership evidence. Explicit `Repo: orchestra` remains valid.
An artifact path or “no repo changes” does not by itself assert Orchestra.

## Bounded task source grammar — implemented revision 3

The parent supplied already audited, sanitized evidence forms: positive source
worktree assignments/resumes, canonical-source declarations, source-review
directives and a named Atrium instruction to create a dedicated worktree.
These are source ownership evidence, not launch-directory inference. The
synthetic tests preserve these explicit forms. They do not claim a complete
parser for every audited task or authorize reading additional task bodies.

Inspect non-quoted, non-fenced clauses at line or sentence boundaries. A sentence
boundary requires `.`, `!` or `?` followed by whitespace; internal path dots do
not create clauses. Mask quoted code/prose; permit inline backticks around a
declared repo/path value, never around a declaration. Permit whitespace and an
optional Markdown list marker before a line, with case-insensitive labels and
existing canonicalization. A reference/negation/example/other-owner clause
excludes the remainder of that line. Ambiguous or unsupported prose remains
UNKNOWN; this is a bounded grammar, not linguistic interpretation.

```text
Repo: <repo-token-or-path>[, <repo-token-or-path> ...]
Repos: <repo-token-or-path>[, <repo-token-or-path> ...]
Worktree: <repo-path>
Source target: <repo-token-or-path>
Same privacy author/isolated worktree <repo-path>
Authorized worktree is NEW <repo-path>
Resume ONLY <repo-path>
Resume SAME <repo-path> after author terminal
Canonical repo <repo-path>
Worktree <repo-path>
Source worktree <repo-path>; HEAD <commit>
Read-only app worktree: <repo-path>
Review only committed source delta <commit> in your dedicated detached worktree <repo-path>
<existing-repo-alias>: nuovo worktree dedicato sotto .worktrees dalla <branch> corrente
```

The commit is a single hexadecimal token of 7–40 characters. An imperative
worktree/resume declaration may terminate with a comma; a resume or unlabelled
`Worktree <path>` declaration may append an operational continuation after
that comma. Parse only the complete anchored assignment clause, not names or
paths in that continuation. Quoted/example/dependency prefixes never match.
The `Source worktree` production accepts only the indicated HEAD metadata
suffix, not an arbitrary sentence containing a path.

The named directive may end with a period or with `, verificando <operational
tail>`. Ownership comes only from the anchored alias and complete positive
directive before the comma; do not extract names, paths or links from its
operational tail. The branch is a single token of letters, digits, dots,
slashes, underscores and hyphens, not a repository candidate.

For the labelled forms, the entire declared value must match. A repo token is a
bare repository/alias or an owner-qualified repository accepted by the existing
`canonical` contract; a path must start at the existing project/service/library
root, identify its repository ancestor, and may include `.worktrees/<branch>`
and descendants. Accept balanced inline backticks and one terminal sentence
period, but not trailing prose or role annotations. This parses the value of
an explicitly assigned field; it does not scan all task paths. No new alias
registry, free-text name inference, linguistic classifier or external lookup
is introduced.

`Reference:`, `Read-only reference:`, `Dependency worktree:`, `Example:`,
`Do not modify ...`, `Nessuna modifica ...` and `Nessun ...` do not match these
positive declarations. Nor does an embedded declaration after those prefixes,
a negated named directive or a field value containing a negative/prose clause.
For example `Worktree: <path> (read-only reference)` is not an assignment.
Exclusion is local to the remaining line tail: a later negative Nexus clause must not
erase an affirmative Atrium source directive, and a read-only task mode does
not invalidate an explicitly assigned source-review target.

In particular `Read-only app worktree: <path>` and the committed-source review
directive explicitly target the source and establish its ownership; `Read-only
reference: <path>` only cites another location. One audited case relied on an
earlier report and a relative path: do not guess a repository from that evidence
or claim complete recovery. Existing structured card/note metadata takes
precedence, and unresolved text remains UNKNOWN without a new registry.

Positive evidence fixtures include these synthetic shapes:

```text
Same privacy author/isolated worktree /data/dev/projects/app-himalaia/.worktrees/synthetic-source
Atrium: nuovo worktree dedicato sotto .worktrees dalla auto/integration corrente, verificando la base.
Task coordinati da Orchestra; nessun cambiamento a exporter Nexus o allowlist.
```

The first declares Himalaia; the second declares Atrium; the third contributes
no owner. Also exercise an assigned Himalaia source plus a Nexus reference
path and Ratio dependency URL: only Himalaia remains display owner.

## Caller and UNKNOWN boundary — implemented SOURCE candidate

Parent-approved representation is `repos=[]`, `repo=''` for an unowned item without a
bound PR/issue. It preserves the existing string contract without inventing
Orchestra ownership. `repository_key('')` already preserves the empty string.
Parent reports static evidence that the Atrium candidate schema accepts it,
unfiltered summary retains it, and StatusLanes includes and filters the empty
repository key. ROOT prepared the empty-label follow-up separately; it is not
part of this SOURCE change. Empty repo keys cannot currently be selected in
the repository facet or API repo filter. Do not fabricate an owner to compensate.
This is static compatibility evidence, not a full consumer contract or browser
PASS. No consumer writer or Atrium change belongs to this SOURCE lane.

The donor `finish` currently has two incompatible boundaries:

1. After `wi_repos.derive`, `it['repos'][0]` raises for UNKNOWN. Guard it and
   assign the empty scalar for unbound items, rather than preserving a stale
   guessed scalar from launch/runtime assembly.
2. Later `it['repo'] = it['repo'] or 'orchestra'` invents ownership again. Remove
   only this automatic fallback in the generated SOURCE caller.

For an already bound PR/issue, preserve the scalar association and PR/issue
objects used by identity and links even when display `repos` differs. Example:
curated `note.repos=['app-himalaia']` and a Ratio primary PR retain both the
curated display declaration and the original PR scalar/URL. Do not rekey or
merge cards. An invalid primary URL must not become a trusted display owner.

The complete emitted `finish` body is exercised with synthetic fixtures and
selected actual `identify`, `match_pages`, `classify_page`, `links_of`, file-link
helpers, `asks`, `merged_asks`, `enrich_asks`, `owned`, `ask_kind`, `ask_answered`,
`steps_of`, `ui_of` and canonical `ask_of`/normalization. All file reads stay in
test-created page directories. Curated ask IDs, question, recommendation,
link/options/answer flags and note pin survive UNKNOWN and bound PR/issue cases.
The step regex is supplied explicitly by the synthetic fixture. Status
computation and unrelated callbacks remain simulated: this does not establish
invariance of the complete runtime lifecycle or every inferred ask branch.

UNKNOWN preserves already bound pages and legitimate unscoped exact-slug page
matches; no blanket page gate is added. Known foreign Nexus/Ratio scoped pages
do not attach to UNKNOWN. For bound PR/issue, scalar, pages and links equal the
selected donor baseline despite different display `repos`. Orchestra is not in
the existing page alias map, so a name containing Orchestra alone remains an
unscoped exact-slug match. That pre-existing matcher limit is preserved without
inventing a registry. Do not treat this synthetic proof as a UI/runtime PASS.

Exporter changes must recognize each expected AST boundary exactly once and
reject missing/duplicate/unexpected ownership shapes. Keep existing donor hash
verification and manifest behavior. If synthetic export fixtures lack the
ownership boundary, update those fixtures explicitly; do not silently skip it.

## Export admission and provenance

Ownership is disabled by default. The existing exporter accepts
`build_bundle(..., expected=<complete reviewed vector>, include_project_ownership=True)`.
The CLI requires both `--include-project-ownership` and `--expected-source <vector.json>`;
the vector is a path-to-SHA256 object covering all effective rewritten donors
and every existing emitted canonical package file. Missing ownership donors,
unbound existing package files and hash drift reject before output. The output
contains the canonical helper and a `wi_repos` compatibility import adapter.
Missing, changed or duplicate caller ownership boundaries reject; the only
ownership caller edits are the empty-list guard and removal of the late
Orchestra fallback. Page matching remains unchanged.

Identity candidates and the historical applied-delta path cannot be combined
with ownership. Synthetic tests exercise the current repository-compat exporter
composition and show donor bytes preserved. This is not an operational
before-vector admission or an apply-ready package.

Only `project_ownership` is appended to the existing producer provenance JSON;
all historical keys/pins remain unchanged. Its prior SHA256 is
`1699b7a5824224d6ab68257a0756532076f3e3f45ad60dc42950a291d9057fc5`.
The ownership-specific source pins do not replace the historical global vector.

## RED receipt

Python 3.12.13 and pytest 9.1.1 from the already existing project toolchain;
no environment sync or install. Focused donor reproduction:

```text
PYTHONPATH=src <existing-venv>/bin/python -m pytest tests/unit/test_dashboard_ownership.py -q --tb=line
37 failed, 18 passed in 0.13s
```

Expected RED failures: six incidental/negative text cases; explicit scope
losing to a dependency; seven reference/directory/stale-scalar cases; three
invalid primaries; prefix IndexError; late Orchestra fallback; named source
contaminated by excluded Nexus; a canonical-source path with sentence punctuation;
15 source-reference/exclusion cases; assigned source contaminated by reference/
dependency. Passing controls: three positive Repo(s) declarations; ten explicit
worktree/source/review declarations; qualified primary; three structured
declarations; input preservation. The revision adds 28 cases (18 failing, ten
passing) to the original 27-case receipt. Ruff format/check and diff whitespace
checks pass after fixing two long test literals; no test was weakened.
The paragraph follow-up produced 48 failures / 18 passes before GREEN, adding
four paragraph-positive and seven negated/quoted/path-ambiguity cases.

## Validation and limits

Python 3.12.13: the full unit suite passed 916 tests; ruff checked/formatted 77
files, strict mypy checked 39 source files, and the scoped security scan found
zero findings. After strengthening curated-ask downstream coverage, the 14
caller/vector/composition tests passed again. The final focused ownership/exporter/
repository-projection selection passed 112 tests after the CLI guard and real ask
coverage updates. Docs-coverage skipped because this
repository has no coverage manifest; the SOURCE feature is documented here and
linked from README. Independent review remains the parent's next gate.

No runtime import/build/publish, provider, DB, raw task/ledger/session read,
environment sync/install, live mutation, commit, push, merge or activation.
No claim of complete audit-corpus recovery, selectable UNKNOWN facet, browser
proof, operational before vector or lifecycle/state-machine invariance.
