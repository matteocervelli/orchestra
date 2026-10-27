# Dashboard card producer: canonical source and safe runtime consumption

Status: parent-reviewed contract, corrected below; source/test GO authorized by the extended ownership ACK.
Date: 2026-10-27. Base: `2381177a7e6051f9731a0894c7f8e425593b3560`.

## Scope and authority

Scope comes from the direct producer-fix mandate, the acknowledged ownership split
`DASHBOARD-PRODUCER-OWNERSHIP-20261027`, and the orchestra-plan update/reply and
Nexus163 handoff of this date. Those are operational evidence references, not
repository fixtures or sources of credentials. The parent owns this contract and
source/test work; dashboard-cleanup alone applies a reviewed runtime patch and
curates existing notes. Launcher I1b owns a separate hook composition after its
review. Its frozen candidate is not modified here.

In scope: a small canonical card-source package, title policy and transactional
missing-title helper, compatible runtime adapters, provenance-sensitive quality
checks, conservative identity resolution, and read-only reconciliation proposals.
Tests contain invented tasks, notes and receipts only. No provider calls, live
readers, active child edits, curation, release or deployment occur here.
The final persistence mandate permits a normal source-only commit, dual-forge
push and draft PR after validation; it does not permit merge or runtime changes.

The runtime generator, dispatch, status engine, external state authority, public
Atrium schema and remaining runtime helpers stay with their existing owners.
No second generator or scheduler is introduced. This contract does not certify
current cards, counts, PR states or the semantic truth of a child's report.

## Observed source boundary and callers

Inspection was static; none of these functions was executed against runtime data.

| Observed caller | Current behavior | Required boundary |
| --- | --- | --- |
| `workitems.build` → `wi_sources.tasks()` | Reads task header; any parentheses replace the whole heading with their contents. | Keep no-argument runtime API through a root-injecting adapter; canonical reader requires an explicit root. |
| `wi_assembly.child_row` → `wi_sources.parse_card` | Parses the last JSON card; no title admission or provenance authority. | Parser stays unchanged; a report is an assertion, not an approval receipt. |
| `workitems.finish` → `curate` → `fill_text` | A card overrides an unpinned note; `fill_text` discards noncurated `title_it`. | Canonical curation preserves an existing note title even without `pin`; canonical fill preserves meaningful supplied titles. |
| `workitems.finish` → `merged_asks`/`asks` | Separate aliases, overrides, actions and answered records influence asks. | Do not add blanket completion or request-clearing rules here. |
| `workitems.publish`/`main` → `wi_quality.audit` | Every pending pipeline card without PR URL warns. | Exempt only a typed, evidenced local artifact review. Unknown/integration work keeps its warning. |
| `wi_dedupe.collapse` → `wi_identity.groups` | Identity may be inferred from numeric slugs and unqualified references. | Canonical identity cannot treat a card ID or bare number as primary PR evidence. |
| `wi_dedupe.migrate_notes` → `wi_notes.notes_lock` | Existing writers use a shared filename lock. | Reuse this exact lock path for the entire read/modify/write transaction; no migration in this change. |
| Runtime `spawn.sh` | Prompt names the task, not COMMON; no title admission. | A separate launcher-owner delta calls the canonical title hook and names COMMON. |

The repo currently has `scripts/spawn.sh`, source helpers and tests, but no
dashboard producer. The checked-in launcher differs materially from runtime;
neither is silently replaced. `wi_common` supplies repo helpers; `wi_status`
supplies only `STATUSES`/`CLOSED` needed here. The rest of the status engine,
`wi_liveness`, `wi_probes`, `pages_server` and log readers are not imported.

## Requirements

- **REQ-01 — One source authority.** Extract only the functions/symbols listed
  below into `orchestra.dashboard`. Runtime imports that package through thin
  adapters; remove the former function bodies from applied adapters. Identity
  adapters are an explicitly separate candidate, not part of the first core bundle. The runtime
  package is an exported build artifact with exact file hashes, never a separately
  maintained implementation. Importing source or running a default invocation
  must neither discover the live root nor perform I/O or start a service.
- **REQ-02 — One title policy.** Admission at start and completion calls the same
  `validate_title_it` function. A title states a specific subject/change in Italian;
  the author supplies the language, the validator checks bounded form and rejects
  known generic fallbacks. No regex claims to prove Italian or invents a title.
- **REQ-03 — Lossless notes transaction.** The helper changes only the missing
  `title_it` of the explicit task ID, with lock held before reading through atomic
  replacement. Existing titles, curated or otherwise nonblank, and every other
  field/task remain equal. No identity inference, alias migration or receipt is
  written into notes. Invalid input or invalid note data causes no replacement.
- **REQ-04 — Title selection.** Preserve meaningful task-heading parentheses.
  Preserve nonblank curated `note.title_it` and `note.title` without requiring
  `pin`, including when the card supplies `title_it`. Preserve each TEXT_KEYS field
  explicitly listed in note.edited_fields and present as a string in the note;
  nonedited fields retain their prior card/pin semantics. Preserve a meaningful
  supplied `title_it` when the curated set lacks it. Only an actual deterministic
  fallback is marked `auto: title_it`; metadata must not manufacture curation.
- **REQ-05 — Typed work provenance.** Distinguish a local artifact review from
  primary integration work using explicit subject, role and source information.
  Task names, report verdicts and pipeline states alone cannot prove that role.
  A missing/invalid/conflicting type fails conservatively to the existing warning.
- **REQ-06 — Conservative identities.** Repository, forge, resource kind, number
  and primary relationship must be established before assigning a PR. Bare
  `#324`, a canonical `pr-nexus-324` ID or an incidental dependency does not prove
  Nexus PR324. Atrium324 and Nexus207 stay separate without a documented relation.
  No network lookup is added to resolve ambiguous IDs.
- **REQ-07 — Preserve independent work.** No edits to ask IDs, choices, answers,
  steps, approvals, status, visibility or existing aliases from title/quality
  helpers. Identity resolution returns mappings without mutating its inputs;
  ambiguous evidence retains the existing card identity. Regrouping needs explicit
  primary provenance and must preserve old aliases through the existing caller.
- **REQ-08 — Structural versus semantic evidence.** The structural validator
  keeps its current purpose. Audit reports explicitly state that syntactic success
  does not prove request freshness. `duplicate_ask_id` is a structural finding
  when nonblank IDs repeat among open asks: error for your_call=true, warning
  otherwise. Ignore blank IDs and answered asks for this collision check; retain
  all original asks, answers and your_call unchanged. A reconciliation proposal requires a later
  receipt for the exact request mandate; merged PRs alone never empty asks.
- **REQ-09 — Reviewable runtime handoff.** Produce package bytes, before/after
  SHA-256 values, compatibility patches and synthetic verification evidence.
  Runtime application is dashboard-owned and remains separate from this source
  phase; launcher hook application remains I1b-owned.

- **REQ-10 — Explicit repository authority.** Display aliases are not a complete
  project registry. Keep FULL, REPOS, refs and short_repo unchanged. A separate
  explicit allowlist for owner matteocervelli includes the six existing canonical
  projects (app-himalaia, app-ratio, adlimen-ui, claude-dotfiles, nexus, atrium)
  and exactly six independently verified names: orchestra, adlimen-cicd,
  adlimen-infra, adlimen-harness, adlimen-auth and limen-assistant. Support those
  canonical names both alone and owner-qualified. Verification here is GitHub
  full_name metadata, not proof of every Forgejo namespace or PR existence; an
  alternate Forgejo owner is not authorized by this change. Do not invent infra/harness/auth
  aliases or accept unknown repositories, foreign owners, mismatched hosts/routes/
  numbers/repositories, dependency-as-primary or invalid provenance. Runtime
  delivery for this fix is only common.py against its fresh live before-hash;
  exclude the CI refactor, identity candidate and launcher.

## Architecture and extraction manifest

Keep a modular, inert Python package with explicit filesystem roots. No new
dependency or lockfile change. All intra-package imports are relative so the
identical package bytes also work as runtime `orchestra_dashboard` under `bin/`.

| Canonical module | Imported baseline / responsibility | Excluded baseline |
| --- | --- | --- |
| `common.py` | `wi_common`: `REPOS`, `FULL`, `REF_RE`, `short_repo`, `refs`; `wi_status`: `STATUSES`, `CLOSED`. | Global root/cache/output paths, I/O helpers, status computations. |
| `sources.py` | `wi_sources.tasks`, adapted to `tasks(root: Path)`; header normalization. | All child/session/log, PR fetch, review-file and page readers. |
| `notes.py` | `wi_notes.notes_lock` and the new explicit missing-title transaction. | `active_sweeps`, migration, legacy sweep inspection. |
| `titles.py` | New single title admission/selection policy, used by notes/text/curation/hook. | Translation, LLMs, retrospective live repair. |
| `text.py` | All `wi_text` constants/functions; relative imports and explicit types. | No added state/status decisions. |
| `curation.py` | `workitems.TEXT_KEYS`/`curate` and `wi_dedupe.unique`/`collapse`; title precedence, alias-preserving collapse with injected existing policy callbacks. | `build`, `finish`, `publish`, asks/status computation. |
| `quality.py` | `wi_quality` audit/findings/load helper; explicit-path CLI. | Runtime-derived default board path. |
| `identity.py` | `wi_identity` pure helpers and grouping; conservative primary-evidence rules. | No discovery/network, no state writer. |
| `provenance.py` | New validation of bounded role/subject declarations; pure reconciliation proposals. | Approval authority, fetching receipts, automatically answering requests. |

Import selected baseline statements once with donor hashes, then edit the
canonical files. Do not keep an editable baseline copy or vendor all `bin/`.
No source module imports a runtime module. Canonical titles/notes depend on the
stdlib; sources/text/curation/quality/identity depend on the canonical small
helpers. The runtime generator consumes them and retains its other duties.

### Runtime replacement, not parallel implementation

The exporter takes an explicit donor-source directory and explicit empty output
directory; it reads only named source files and rejects unexpected donor hashes.
It writes a patch bundle, never applies it. A default/no-argument invocation exits
with usage before any source/root access. It does not overwrite an existing output.
The only maintainable implementation is the package in this repository; the
export is a generated consumer artifact. Export does not extract fresh donor
logic over edited canonical files. It verifies donor hashes, then renders exact
replacement adapters around the reviewed package version. The application step
is manual and owned by dashboard-cleanup, using before/after hashes.

Each selected top-level function/constant definition is removed from its runtime
donor, including the original `workitems.curate` and `TEXT_KEYS`. Re-export each
public symbol once; only the documented root/CLI adapters have a small wrapper
body. Export validation parses the patched donor AST, rejects duplicate top-level
bindings of replaced symbols, and proves exported package bytes equal canonical
bytes. The bundle includes the exact unified patch, new package files, relative
source-to-target map and hash manifest. It cannot import all runtime modules,
copy donor data, apply the patch or preserve an editable parallel baseline.

| Runtime target | Exact change / owner |
| --- | --- |
| `bin/orchestra_dashboard/*.py` | Byte-identical export of canonical package, including `__init__.py`; dashboard applies reviewed package/hash manifest. |
| `bin/wi_text.py`, `bin/wi_identity.py` | Replace implementations with explicit compatibility re-exports of canonical public names. Preserve function signatures. |
| `bin/wi_quality.py` | Compatibility exports plus CLI wrapper passing the former default board path explicitly; canonical default requires a path. |
| `bin/wi_sources.py` | Remove local `tasks` implementation; keep `tasks()` as `return canonical_tasks(C.O)`. All other source readers remain unchanged. |
| `bin/wi_dedupe.py` | Re-export canonical `unique`; replace `collapse` with a thin call passing unchanged compute/effective_note/issue_ref policy callbacks. Preserve historical part.aliases, require proven issue identities, and filter cross-repo/forge PR candidates. No migration or other merge logic changes. |
| `bin/wi_notes.py` | Remove local `notes_lock` body and re-export canonical lock; keep `active_sweeps` unchanged. |
| `bin/wi_common.py` | Re-export extracted repo constants/helpers rather than keep competing definitions; paths and remaining I/O helpers unchanged. |
| `bin/wi_status.py` | Re-export `STATUSES`/`CLOSED`; preserve every status function and other constant. |
| `bin/workitems.py` | Re-export canonical `curate` and `TEXT_KEYS`; remove old definitions. In `finish`, resolve provenance from parsed task rows, note and selected card. Additional snapshot delta is specified below; preserve all state/ask helper calls. |
| `bin/dashboard-producer-title.py` | Explicit CLI adapter to canonical admission/missing-title helper, shared by start and completion. No independent policy body. |
| `bin/spawn.sh`, `tasks/COMMON.md` | Separate I1b owner delta only: call admission before new child launch; refer to COMMON and the same completion hook. Not patched by this source bundle. |

The `workitems` delta extends the original source-file split and must be ACKed by
the dashboard owner before its runtime composition. The extended ownership ACK
now covers all necessary producer-only source changes; no per-file ACK is needed.
It is necessary: `curate` overrides unpinned titles and ignores provenance, and
`_detail_item` does not currently stamp a publication. Exact additional runtime
functions are `workitems.curate`, `finish`, `_detail_item` and `publish`, plus the
`TEXT_KEYS` re-export and `wi_dedupe.unique`/`collapse` adapters. `PUBLIC_ITEM_KEYS` and Atrium schema remain unchanged.

Publication now explicitly changes the existing `generated` value to ISO UTC
with six fractional digits (`YYYY-MM-DDTHH:MM:SS.ffffffZ`); no board key or type
is added. A single publisher reads the previous board's generated value and uses
max(current UTC time, previous value + one microsecond), ensuring distinct
publications even in one second or after a backwards wall-clock adjustment.
`publish` uses this value consistently for board, archive and quality report;
`build` is unchanged. The existing single runtime writer assumption is required:
this change does not add a second publishing process or cross-process scheduler.

Canonical quality helpers compute SHA-256 of canonical JSON for the full compact
public board (sort_keys=True, separators=(',', ':'), ensure_ascii=False,
allow_nan=False). `_detail_item(item, ledger, *, board, snapshot_digest)` adds private
`_producer_snapshot={version:1,item_id:<id>,generated:<exact generated string>,
board_sha256:<digest>}`. `publish` constructs the final public board before these
details, computes its digest once (passed as an internal argument, never read
from payload metadata), stamps every detail against it, then writes details, archive, quality
and finally the public board. Interruption/races may temporarily withhold an
exemption; they never authorize one from a different generation.

`quality.load_board` enriches only when detail.id, stamp.item_id, stamp.version,
stamp.generated and recomputed board digest all match the loaded board. A missing,
stale, wrong-ID, malformed or unstamped detail cannot supply any exemption. The
board remains authoritative for state/asks. The canonical audit of the live full
items and load_board→audit must agree for a complete valid published snapshot.
A timestamp/digest binds a publication; it does not prove semantic freshness of
requests, task intent, approval or delivery.

Read-only compatibility evidence, Atrium source pinned at integration
`7035fdc83144c5ee965120e0164188d91a4acd56`: backend
`orchestra_state._to_dt` uses datetime.fromisoformat and schemas use datetime;
BoardHeader/orchestraFormat/BoardInsights use Date.parse; v3Actions.stamp removes
fractional digits explicitly before second-resolution action comparisons. A
synthetic Node Date.parse of a six-digit timestamp succeeds. No fixed-second
parser was found in these inspected consumers. This is static evidence plus an
isolated standard-parser check, not an Atrium build/browser test or a claim about
uninspected consumers/deployed revisions; dashboard owner verifies composition.

Donor drift causes a stopped patch build with file/hash evidence; it never
silently rebases through concurrent runtime edits. The dashboard owner checks
hashes immediately before application and coordinates the final sequence. The
source lane does not apply, refresh, restart or roll back runtime files.

### Core versus identity candidate and exact-ID consumers

The default bundle changes title/notes/task parsing/provenance/quality and the
minimal publisher metadata adapters. It excludes `bin/wi_identity.py` and
`bin/wi_dedupe.py`; their prior runtime implementations are untouched by core.
Core re-exports `refs` and `short_repo` with exactly their prior semantics, so it
cannot change grouping through the support-module move. Candidate identity and
collapse logic exists once in canonical source but is dormant until explicitly
reviewed/composed; it is not claimed active by shipping the core package bytes.

`--include-identity-candidate` builds a separately named bundle with those two
adapters included. Its manifest says `identity_candidate: true`, `runtime_ready:
false`, `applied: false`; a flag never grants apply authority. No bundle is applied
here. `identity_delta(before, after)` accepts only caller-supplied snapshots and
reports exact added/removed/changed IDs, per-shared-ID ask/steps/priority/answers/
approval/status/hide/pages/aliases equality and old exact-ID presence. It always
returns `runtime_ready: false`; no live board is read for this comparison.

Observed Atrium consumer finds exact item.id and does not carry aliases through
its parsed model. Therefore preserving aliases alone does not prove old deep
links remain valid. Preserve the opaque current ID of a curated object and
correct primary provenance independently. If a proposed grouping would remove an
existing ID, the dryrun must show it explicitly and it stays outside the first
core bundle pending owner consumer/migration evidence. Tests use an exact-ID
synthetic lookup, not an assertion of a real API 200. No alias endpoint or reader
is added here.

### Adapter Ruff follow-up and after-manifest delta

The root has separately applied the reviewed B1 core. A subsequent adapter-only
fix must not apply the original donor-before patch again. Canonical package bytes
stay unchanged except the explicitly authorized sources.tasks exact legacy-wrapper
correction described below; all other nine package hashes remain identical. Generate the complete new bundle for provenance from pinned source
backups/reconstructed original donors, plus `delta.diff` and `delta-manifest.json`
against the applied bundle's exact AFTER hashes. The `--against-applied-bundle` delta records base patch and
manifest hashes, per-target applied-before/new-after hashes, unchanged package
paths and applied=false. Reject changed/missing base artifacts, package drift outside sources.py,
extra/missing targets and an already-existing delta output. Never read notes,
auth/log data or execute the operational readers to build it.

Generated exports use explicit `as SameName` aliases, preserve module docstrings
and future imports, and place canonical imports in the initial import block.
Remove only the extracted dependency imports proven unused in wi_common/wi_notes;
never run a blind Ruff fix or add restrictive __all__ to partial modules. Test
exported files under isolated consumer Ruff: only E741 on wi_common.py's existing
O binding is allowed, with no global E741 suppression. Source quality remains the
repository profile. Verify symbol identity and unchanged retained function AST.
The root's two legacy quality fixtures are outside this implementation lane.

### Unresolved identity integration boundary

The optional identity candidate remains blocked: upstream Assembly may replace a
historical curated ID before groups receives it, losing the route to its note/pin;
the exact-ID consumer does not resolve aliases. Isolated grouping tests do not
prove end-to-end old-link or curation preservation. The CI refactor preserves that
existing behavior and does not authorize candidate application. Its full-producer
reproducer and migration/consumer remedy belong to a separate reviewed follow-up.
The operational audit `dashboard-goal-identity-compatibility-audit-20261027`
reproduces this on the real three-item pre-collapse Assembly slice; preserving
2791/2791 already-collapsed IDs is not acceptance evidence. The next contract must
bind historical raw-source owners to opaque published keys, use a same-generation
sanitized capsule supplied by the authorized producer before collapse (including
already-extracted child.card, never transcripts/session logs), and compare active
baseline versus candidate asks, steps, flags and exact-ID/action routes. This
follow-up adds no live hook, fetch, migration or identity activation.

## Data and function contracts

### Titles and notes

`validate_title_it(value: object) -> str`: trim outer whitespace; require a
single string of 12–180 characters, at least three alphanumeric words, no
control characters, Markdown heading or URL-only content. Reject case-insensitive
repository-only, ID/PR-only and the exact deterministic generic fallback forms.
The repository list and fallback tokens come from existing canonical constants.
Do not reject a specific title merely for containing parentheses or a product
name. Raise `ValueError` with a stable code (`title_type`, `title_length`,
`title_shape`, `title_generic`). Existing curated titles are preserved even if
they do not pass new admission; quality may still flag their deficiency.

`ensure_title_it(root: Path, item_id: str, title_it: object, phase: Literal[
"start", "complete"]) -> Literal["written", "preserved"]`: validate explicit
ID (`[A-Za-z0-9][A-Za-z0-9._-]{0,127}`), phase and candidate before file access.
Take `notes_lock(root)` using `.workitems-notes.lock`; load
`workitems-notes.json` inside the lock (missing file means `{}`; malformed root
or task mapping is an error). Existing nonblank `title_it` OR `title` wins without rewriting
the file (prefer `title_it` when both exist). Otherwise update only that key. Atomic replacement uses a unique
temporary file in the same directory; clean up only that helper-created temporary
file on failure. Never use shared `.tmp`, broad cleanup, or read-before-lock.
Propagate I/O errors; do not guess, replace invalid JSON, or clear non-string
existing values. Missing/blank string is the only writable title state; both note title keys
must be absent/blank before a new `title_it` is written.

Start and completion share this helper and validator. The author supplies
`title_it`; a launch with invalid/missing candidate is rejected before spawn.
The separate completion hook validates the report title and fills only a missing
note title. It does not update a valid start title to a claim of success.
Historical running tasks are not retroactively rejected or rewritten.

`tasks(root)` preserves its existing returned keys (`slug`, `goal`, `header`,
`text`, `mtime`), excludes COMMON and reads each task once. Its internal row gains
`work_provenance` (validated declaration or `None`) and `provenance_errors`
(list of stable parser codes); these are not public-board fields. `goal` removes
only the leading heading/optional `Task:` marker and keeps the whole remaining
heading, including meaningful parentheses. The sole legacy exception is an exact
`# Task: <filename_stem> (<goal>)` wrapper: extract goal, retaining its internal
parentheses. A different stem or nonmatching prefix is not a wrapper. No arbitrary
suffix stripping or generic parenthesis extraction occurs.

`curate(it, note, card)` keeps the existing text/pages semantics except for title
selection: nonblank `note.title_it` wins first, then nonblank `note.title`, then
card title fields. This applies regardless of pin or card title key. When only
`note.title` is protected, remove any card-origin `it.title_it` from the working
item and retain `title` in the curated set; do not alter the note itself.
`fill_text(it, curated, asking)` chooses curated `title_it`, then curated `title`,
then a meaningful uncurated supplied `title_it`, then the existing fallback.
Before protected-title selection, `curate` reapplies only TEXT_KEYS entries in
`note.edited_fields` that are explicitly present and string-valued in the note.
An absent field is not an override; invalid metadata is ignored. This is not an
all-note-wins rule and does not set pin or change stage/asks. Explicit blank
strings clear stale child text before `fill_text`: blank problem becomes the
selected title, blank solution uses the existing status fallback, and blank needs
uses the existing asking/blocked/status fallback. The projected blank is therefore
not byte-preserved, and the stale child text must never reappear. Existing
`merge_notes` already orders an edited canonical note after old aliases; verify
that real consumer path with synthetic aliases through final curation/projection.
Thus a card `title_it` cannot defeat a protected note `title`. `auto` includes
`title_it` only for the final fallback; other automatic fields remain unchanged.
No policy labels are written into user notes.

### Provenance and identity

Task provenance uses exactly one fenced metadata block as the first nonblank
block after the task heading (there may be blank lines, but no intervening prose):

````markdown
# Rivedere la proposta delle card (titoli e richieste)

```json orchestra-task-meta
{"schema":"orchestra-task-meta/v1","work_provenance":{"kind":"local_artifact_review","subject":{"repo":"orchestra","artifact":"review://synthetic/card-candidate"},"relation":"primary"}}
```
````

`parse_task_provenance(text: str) -> tuple[dict | None, list[str]]` belongs to
canonical `provenance.py`; `sources.tasks` calls it on the already-read text.
Absent marker means `(None, [])`. More than one metadata marker anywhere,
misplaced block, missing closing fence, block over 4096 UTF-8 bytes, malformed
JSON, duplicate JSON keys, nesting beyond 16 levels, wrong schema, unknown keys
or invalid values means
`(None, [stable_code])`; retain the task and its title. No YAML, eval, implicit
frontmatter, arbitrary JSON-card blocks or prose inference is accepted.

The outer object permits only `schema` and `work_provenance`. The declaration
permits exactly `kind`, `subject`, `relation`: kind is `local_artifact_review` or
`primary_integration`; relation is `primary` or `dependency`. Subject requires
`repo` (canonical repo name, 1–100 `[A-Za-z0-9._-]` characters) and exactly one of
`artifact` (nonblank single line, at most 500 characters) or `pr`. A PR is exactly
`{host, repo, number, url}` with host `github.com` or `git.adlimen.dev`, repository
`owner/name`, a positive integer (not bool), and a matching HTTPS PR URL. Subject
repo must normalize to the PR repository name. Known repo aliases assert only the configured owner's full repository; matching
basenames under other owners are not equivalent. Malformed URLs fail validation
without crashing the reader. There are no network lookups.

A note's optional `work_provenance` uses the same declaration schema (without an
outer task wrapper); card declarations may use that schema only as assertions.
A payload `source` key is rejected: the importer assigns source from its actual
origin, never from self-description. Normalized internal provenance adds
`source` (`task_contract`, `curated_note`, `child_report`) and validation status.

`resolve_work_provenance(note, task_rows, card)` is called by `workitems.finish`
using the selected card and all task rows named in `it.slugs`. Valid note
classification has first preference, otherwise unanimous valid task declarations,
otherwise a child declaration is retained as `unverified`. An explicitly present
invalid child declaration (including null or forbidden keys) is a conflict; an
absent child key is not. Any invalid selected note/task declaration or disagreement on kind/subject/relation between trusted
note/task origins yields `unknown` and an audit finding, not an exemption.
A contradictory child assertion is diagnostic and also withholds exemption; it
cannot establish a primary relation, promote itself to task/note authority or
supply approvals. Missing declarations yield `unknown`. Multiple identical task
origins are allowed and retained as evidence references. This selection does not
write notes, change asks, or grant dispatch/approval authority.

Task contracts and owner notes record classification/intent, not delivery or
approval. Neither an APPROVE word nor a child's arbitrary report proves that the
review is local, that a PR was integrated, or that an existing mandate was met.

A local-artifact exemption needs an explicit artifact subject and primary local
review role from task contract or curated note, with no contradictory primary
PR/integration evidence. It suppresses only `pipeline_without_pr`. Primary
integration without a verified same-repo PR URL retains the warning at every
pending stage. Neither exemption nor report verdict changes status or asks.

Identity accepts only a qualified primary PR with the known full repository
authority (configured owner plus FULL repository mapping). Unknown owners are
conservative, not aliases of matching repository basenames. The existing
GitHub canonical-ID scheme is not reused for a Forgejo number: a Forgejo-only
reference retains the existing item ID until an explicit companion relation
is separately documented. Numeric note.pr/note.issue without qualified forge
and repository evidence are insufficient. Existing issue refs also need a
qualified same-authority issue URL. A bare keyword/number,
task/card ID, directory context or repository label is not a primary relation.
Qualified dependency links are recorded as references, not primary assignments.
Do not globally alter `refs` semantics used by other runtime callers: restrict
the conservative change to canonical identity selection. Ambiguity retains input
identity and aliases; the runtime patch does not run notes migration. Grouping
uses exact proved primary identities; common root_task naming never promotes an
unproven sibling. A singleton retains its existing opaque ID even after the
primary reference is corrected. Among same-primary groups, one curated anchor
retains its ID; two or more curated objects remain distinct. Otherwise choose an
existing member ID, never synthesize a new canonical key. Canonical-name
collisions with unproven cards cannot cause a merge. Canonical collapse includes every prior part.aliases, derives
issue only from proved identities rather than an issue-shaped target ID, and
chooses only qualified same-authority GitHub PRs corroborated by an existing
primary item PR. It never invents issue aliases from coincident PR numbers.

### Semantic reconciliation

`propose_request_reconciliation(requests, receipts) -> list[dict]` is pure and
read-only. A request/receipt match requires the same explicit mandate ID,
repository, object/target, action and scope, plus a later successful receipt.
Missing fields, unrelated receipts, weak aliases, timestamps without matching
scope and PR merge alone yield `unverified`; they never retire a question.
Return request ID, result (`satisfied_candidate`, `unverified`), matched receipt
reference and reason; preserve all original requests outside the proposal.

Synthetic Nexus163 scenario: later `configure_ci_token` receipt can satisfy
only that exact configuration mandate. A later merge receipt may satisfy an
explicit integration mandate. A visual approval or activation request remains
open even when its PR is merged. Historical forge rows remain separate until
an explicit relation is proved. Retrieval of missing PR receipts is owner work,
not a guessed canonical-ID lookup.

Audit adds explicit coverage metadata: structural checks ran; semantic freshness
remains `not_verified`; standalone exact-receipt proposals are limited to their
provided inputs and do not upgrade the board-wide semantic claim. No aggregate `PASS` claims semantic freshness from zero structural
errors. Existing summary counters and findings keep their meanings.

## File Manifest

The following is the complete allowed source/test implementation manifest after
parent GO; amendments precede any additional file. No runtime path is an
implementation target.

- docs/specs/2026-10-27-dashboard-card-producer.md
- README.md
- docs/guides/dashboard-producer.md
- docs/provenance/dashboard-card-producer-20261027.json
- src/orchestra/dashboard/__init__.py
- src/orchestra/dashboard/common.py
- src/orchestra/dashboard/sources.py
- src/orchestra/dashboard/notes.py
- src/orchestra/dashboard/titles.py
- src/orchestra/dashboard/text.py
- src/orchestra/dashboard/curation.py
- src/orchestra/dashboard/quality.py
- src/orchestra/dashboard/identity.py
- src/orchestra/dashboard/provenance.py
- scripts/dashboard_producer_title.py
- scripts/export_dashboard_producer.py
- tests/unit/test_dashboard_titles.py
- tests/unit/test_dashboard_sources.py
- tests/unit/test_dashboard_text.py
- tests/unit/test_dashboard_quality.py
- tests/unit/test_dashboard_identity.py
- tests/unit/test_dashboard_provenance.py
- tests/unit/test_dashboard_runtime_export.py
- docs/codebase/INDEX.md
- docs/codebase/architecture.md
- docs/codebase/conventions.md
- docs/codebase/test.md

All test data is inline invented Python/JSON under pytest `tmp_path`; no runtime
fixture import, user note, source-root default or provider dependency. Existing
tests, launcher files, security modules, package metadata and frozen lock remain
unchanged. The provenance JSON records relative donor names, SHA-256, selected
symbols, adaptations, canonical target and exported hash; never absolute host
paths, operational notes or native runtime references.

## Donor provenance (static inspection)

| Relative donor | SHA-256 |
| --- | --- |
| `bin/wi_sources.py` | `755e7721dc5a79ece5646a8a680d280a71749f0f71330106b9d474e8b18905a1` |
| `bin/wi_text.py` | `34bf4e3101fac1fa834108e3ca16e0f5828a4aef54e0cad3f7ca1d2ce7be57fe` |
| `bin/wi_quality.py` | `a0a78bdd08b4deb9970b4ceff23dc86fc8197a99c117f25fbdf99c035f45fa0b` |
| `bin/wi_identity.py` | `6fcae367a975082525ae32f19e9395290d1032a12bd0627a60f62f7a7a80841a` |
| `bin/wi_dedupe.py` | `0d804f68f5f40b8944bdf50dc0a1d2b2d2cd6435aeec6476511ad4898feb68c1` |
| `bin/wi_notes.py` | `cc9e2c42c49c940fd39954dbee0b8100feaa9f2e36539b83ced44611f925c13f` |
| `bin/wi_common.py` | `afe8f39b1467103b26562230f160dcf5c88344ab4f85be6ab6f74924cd74a570` |
| `bin/wi_status.py` | `90455aa0162af44836acac6d19602689844e4f17126619bd5ee10af46a6b40a9` |
| `bin/workitems.py` | `54e22f44d70b9951defd542535d2041dbe6256999dd99adda9e5574975c2b9b9` |

Caller-only evidence: `wi_assembly`, `spawn.sh`, COMMON and the
single STEP_RE declaration in `pages_server` were inspected, not selected for
source import. Diagnosis handoff file was absent at inspection. Existing task
notes, logs, sessions, answers and credentials were not opened.

## Implementation phases and checks

1. Import inert canonical slices with provenance; add regression tests first.
   Verify: import under a nonexistent synthetic root performs no I/O; existing
   behavior tests stay green and new title/role/identity cases initially fail.
2. Implement titles, notes and curation. Verify REQ-02–04/07: specific parentheses,
   uncurated significant title, unpinned note.title and note.title_it against card.title_it, blank/invalid cases, start and
   completion using one validator, idempotency, multiprocessing lock race with
   another cooperating writer, atomic-write failure and full other-field equality.
   Assert the exact title precedence matrix: note.title_it > note.title > card
   titles; pin true/false; a noncurated meaningful title survives only when neither
   curated note key exists. A notes transaction with only note.title already set
   returns preserved and leaves its bytes unchanged. Regress unpinned edited
   needs/problem/solution against a stale child card, a listed-but-absent field,
   a nonedited field, explicit blank fallback, and real merge_notes old-alias to
   edited-canonical ordering followed by projected text. Pin/status/asks stay equal.
3. Implement role/identity/semantic checks. Verify REQ-05–08: local review without
   PR, true integration without PR, exact metadata parsing/placement/duplicates/limits,
   note/task precedence and conflicts, report-only spoofed role, conflicting repo,
   bare Atrium324 plus explicit Nexus207, ID-only324, explicit qualified primary,
   retained aliases and immutable approval/ask fixtures, opaque singleton IDs,
   two curated anchors, and exact-ID synthetic consumer lookup. Candidate dryrun
   reports all ID deltas explicitly without claiming live link compatibility.
   Regress duplicate IDs across open asks, answered and blank-ID exclusions,
   human/nonhuman severity and full original-question preservation. Merge alone leaves all
   requests open; matching later receipt proposes only its exact request.
4. Export and validate adapter bundle without application. Verify REQ-01/09:
   package bytes/hash equality, AST single-binding checks after old bodies are removed;
   wrapper imports resolve to canonical function
   objects; runtime no-argument `tasks` and quality CLI retain their caller
   contract; explicit synthetic source/output only; donor drift fails closed;
   public-board keys/types unchanged; microsecond generated is unique for same-second
   synthetic clocks and a backwards-clock case; bound-detail parity; stale,
   wrong-ID, missing-stamp, wrong-digest and missing-detail cases remain conservative. Default invocations produce usage without touching a runtime root.
5. Update maps from implemented source, run scoped deterministic gates and hand
   stable diff/evidence to the parent for the independent review it owns. No
   nested reviewer/provider invocation is launched by this child.

Commands, with inherited `UV_PROJECT_ENVIRONMENT` and `VIRTUAL_ENV` unset before
any uv command: frozen environment setup, `uv run ruff format --check src tests`,
`uv run ruff check src tests`, `uv run mypy --strict src`, and focused
`uv run pytest tests/unit/test_dashboard_*.py -q`; validate the two new scripts
with ruff separately. Existing repository unit tests run once after stable package
and adapters. No browser or live refresh is required for source tests. The
dashboard owner verifies composed runtime data/browser behavior after review.

## Handoff and remaining integration gates

Source decisions above are fixed for implementation. Parent GO and the extended
ownership ACK authorize source/tests without asking Matteo or requesting per-file
ACKs. Notify the dashboard owner of the exact expanded workitems/support adapter
patch before composition; runtime remains exclusively theirs. The owner has
applied the B1 core and confirmed curated field projection. The adapter/reader
delta has separate exact-after validation and requires its own consumer receipt.
Future-title prevention requires verified adoption by the real caller or both
launcher lifecycle hooks; that separate gate does not block rendering fixes.
Existing card reconciliation
and qualified alias changes remain owner-reviewed proposals, never automatic
cleanup. Source commit/push/draft PR are authorized after gates; no merge,
provider call, runtime write or frozen-candidate edit is part of this phase.

## CI source quality follow-up

The source PR keeps all public signatures and behavior while separating title
selection/fallbacks, locked note I/O, metadata parsing, qualified identities, page
projection, primary/alias assembly and audit reporting into private helpers. No
new files, framework, dependency, whitelist or threshold change is required. The
legacy known_prs argument is explicitly discarded for compatibility; qualified
primary evidence remains authoritative. Helpers and closures must stay at Radon
grade B or below; Vulture runs at the shared CI confidence of 80.

Validation includes Python 3.12 unit tests with branch-aware coverage at least 80,
contract cases for text/asks/options/references/details, and the explicit-path
quality module CLI. This is a SOURCE-only revision: no runtime bundle/delta is
regenerated or applied, and it does not supersede the operational receipt for a
previously composed runtime snapshot. A future refresh requires its own reviewed
source-to-runtime hash comparison. Existing identity/caller adoption boundaries
remain unchanged.
