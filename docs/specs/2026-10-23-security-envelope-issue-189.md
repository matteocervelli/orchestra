# Executable security envelope — Nexus issue 189

Status: design for root review; no implementation or activation authorization.
Date: 2026-10-23. Scope: the OSA-6 / security-envelope slice of
[Nexus #189](https://github.com/matteocervelli/nexus/issues/189), OPEN, no comments
at inspection. This document does not complete issue 189.

## 1. Authority, baseline and scope

Requirements below come from issue 189, the accepted Nexus
`docs/specs/2026-10-17-orchestra-promotion-safety.md` (OSA-6), and Matteo's recorded
decision “Confermo profilo e HIGH bloccante per Orchestra”. The decision authorizes
Gitleaks and SAST always; native Python/JS dependency audit plus OSV for applicable
lockfiles; Trivy wherever the repository's trusted CI policy requires it. Missing,
failed, timed-out, truncated or overflowed required components block. HIGH and
CRITICAL changed-file findings and uncertain attribution block, including JS.
The stronger existing Python dependency/Bandit gates remain in force. The general
JS policy outside Orchestra is not changed.

Verified source baselines:

| Repository/source | Immutable baseline and relevant source |
| --- | --- |
| Orchestra | `b6de3879e29df7cf4c01c5acaedaa434274c0430`, freshly fetched `origin/auto/integration`; `AGENTS.md`, issue-184 spec, `pyproject.toml`, architecture/codebase docs and `.forgejo/workflows/ci.yml`. Main has only the initial stub. |
| Nexus | `b1a254cb7b6ec1fcdcd8f36da3ccde1a77376737`, freshly fetched `origin/auto/integration`; `orchestra/{gates,procs,config,service,models,worktree,attempts,queue,forge,finalization}.py`, config example, gate/pipeline tests and promotion safety spec. |
| Portable pattern SAST | Source commit `c3adea75ed912c9a756883a53c96ed8e69ce9510`, `skills/security-verify/scripts/security_verify.py`, SHA-256 `b7c6ac535abd87878cb9ffc33eddc8e52cb3d1c8d8966286549812a4f4979291`. Read as source only. |
| Legacy multi-tool producer | Source commit `5b3cbebe6707f812051320f88fcef41f313ae59e`, `skills/security-verify/lib/scanner-runner.sh`, SHA-256 `a694a0425416f89441d4051008a0e5d9b439e8b3d06cb4782bc632dbf801f352`. Read as source only. |

In scope: versioned Orchestra producer, trusted scan plan/profile, supported
native adapters, complete bounded envelope, Nexus validation/decision, reuse of
Atrium evidence persistence, producer-to-consumer contract fixtures and a phased
implementation manifest. Out of scope: new scheduler/engine/database, full SDLC
workflow/restart implementation, dual-forge publisher replacement, live scanner
execution, installation, shared skill edits, activation, merge/tag/release/deploy.
Coordination confirms this task owns design; central Orchestra owns subsequent
independent review and integration.

Design choices, rather than additional user requirements: the exact adapter pins,
bounded supported formats, receipt/error enums, limits, immutable scan-plan
representation and module split below. Unsupported inputs block; supporting more
stacks or pins is a later reviewed profile revision, not a fallback.

## 2. Existing behavior and reuse

Nexus `run_security_gate` currently invokes `bash <scanner_path> .`, recognizes
Markdown headings and intersects grep paths with changed files. `run_capture`
retains at most 65,536 bytes separately for stdout/stderr and records truncation.
It already blocks large output, malformed reports, HIGH/CRITICAL changed paths
and unscoped blocker sections. Preserve those protections.

The legacy producer clips pattern results at 20 lines, swallows some errors,
uses shared `/tmp` paths, skips tools based on installation and may interpret
missing/invalid OSV JSON as success. The portable Python scanner supplies a
smaller reusable rule table and structured findings, but has no dependency
adapters and permissive read/exclusion behavior. Neither is a complete producer.
Reuse the reviewed portable rule definitions and matching logic by bringing the
bounded SAST subset into Orchestra source with provenance; do not execute/import
the mutable shared skill or retain its CLI discovery, `nosec` suppression,
decode-error swallowing, raw evidence or DAST paths.

Nexus already has per-attempt lease/fencing, structured `result`, Atrium CAS
`queue.set_stage`, exact remote-head checks and durable dual-forge PR checkpoints.
Extend them; do not build another publisher or evidence store. Full publication
and recovery acceptance in issue 189 remains separate.

## 3. Architecture and trust boundary

Use a small producer/consumer boundary within existing packages:

| Owner/component | Responsibility |
| --- | --- |
| Orchestra `security` package | Fixed scanner adapters, trusted installed profile assets, strict inventory verification, isolated native scratch, normalization and one JSON envelope. No promotion decision or durable state. |
| Nexus profile/config and plan builder | Select approved profile by repo allowlist; verify installed producer and scanner identities; capture immutable base/head and trusted inventory; derive expected receipt keys. Never load the candidate branch's policy as authority. |
| Nexus security consumer | Validate envelope against the retained trusted request and independent process observation, recompute attribution/severity rules, decide fail-closed, persist evidence before publication. |
| Atrium existing work-item result | Own the complete safe envelope, its digest, gate decision and attempt/SHA correlation through the existing fenced stage write. Local native scratch is disposable, not an alternate authority. |

The producer is an explicitly installed, reviewed artifact outside the candidate
worktree, launched from Nexus's configured interpreter with isolated module
loading (`<trusted-python> -I -S -B <trusted-artifact>/bootstrap.py --request-stdin`). Do not
resolve tools through the worktree, `uv run`, package scripts, Corepack, `npx`,
shell strings or candidate `PYTHONPATH`. Nexus checks the producer artifact's
SHA-256 and revision and each configured executable digest/version against the
trusted profile; a version string alone is not provenance. Profile data never
contains a report-supplied executable or arbitrary command. Deployment of those
artifacts is a separate operation, not part of this implementation slice.

`producer_digest` is SHA-256 of canonical JSON
`{format:"orchestra.producer-artifact/v1",revision:<git40>,files:[...]}`;
each sorted file entry is `{path:<relative POSIX>,sha256:<hex64>,size:<int>}`.
The exact file list includes bootstrap, `orchestra/__init__.py`, every security
module, all profile/config/rule assets, the complete pure-Python module trees
and licenses of packaging26.3 and PyYAML6.0.3, and a source-provenance file. It excludes
only the artifact manifest itself (to avoid self-reference); the manifest's
canonical bytes are what Nexus pins. Extra/missing files, symlinks, extension
modules, bytecode, `.pth` files or content mismatches reject. Rule/config files
are covered even if not imported as Python. No editable install or repository
symlink is a valid artifact. This is a reviewable file artifact assembled from
source; no package publication is necessary for this slice.

Nexus verifies the artifact against its configured digest before launch. The
audited bootstrap derives its artifact root from its own fixed location,
verifies the same manifest, replaces `sys.path` with that root plus the trusted
interpreter's stdlib paths, then loads `orchestra.security` and checks every
loaded non-stdlib module origin (orchestra, packaging or yaml) is an exact
manifest-listed file. Optional LibYAML bindings are absent; use Python SafeLoader.
`-I -S -B`
removes candidate cwd/PYTHONPATH/user-site and site/.pth startup and suppresses
bytecode creation; plain `python -I -m` alone is insufficient. Python itself
and its stdlib are a separate configured trusted runtime identity with a pinned
provisioning-manifest digest; they are not falsely represented as producer files.
Artifact paths/owners must be inaccessible for writing by the candidate runtime,
with no concurrent deployment while scanning. Nexus verifies hashes again after
completion. Filesystem immutability/isolation must be proved by the #170 runner
capability before activation; hash-before/hash-after does not alone prevent an
adversarial race. A report's self-claimed digest is never that proof.

`build_scan_request(repo: RepoConfig, attempt: AttemptRef, head: GitHead,
base: GitHead, profile: TrustedProfile) -> ScanRequest` captures the trusted plan.
`run_scan(request: ScanRequest, profile: TrustedProfile, runner: NativeRunner)
-> SecurityEnvelope` runs it. `validate_security_envelope(raw: bytes,
process: CapturedProc, expected: ScanRequest, profile: TrustedProfile)
-> SecurityGateDecision` is the Nexus consumer. Typed immutable records and
stdlib JSON/TOML and two existing locked parser libraries suffice in Orchestra;
Nexus uses existing Pydantic v2 strict models, `extra=forbid`. Declare
`packaging==26.3` and `PyYAML==6.0.3` as runtime dependencies: both versions
already occur in Orchestra's dev lock. They replace a homegrown requirement
grammar and YAML parser, not the scanner engine. Promote those exact existing
pins to runtime in the implementation lock; no dependency update/install is
performed by this design.

Nexus sends exactly one bounded JSON request on stdin, then closes stdin. The
request contains schema version, repo allowlist key, work-unit/attempt IDs,
fresh scan UUID, base/head/merge-base commits, profile ID/digest, inventory and
changed-set digests, and the derived units. A private absolute repo root is
supplied by Nexus's allowlist only and never echoed into public evidence.
The producer resolves profile ID from its installed catalog and refuses a
digest mismatch; it verifies the supplied tree/plan before scanning. The consumer
trusts its retained request, not profile/required/applicability claims in output.

Rejected: Markdown completeness; self-declared required scanner lists; trusting
the candidate's profile/config; treating missing binaries as non-applicability;
larger capture caps to hide clipping; shared temporary files; a new scan engine.

## 4. Immutable scope, discovery and applicability

1. After implementation/tests, Nexus requires a clean worktree, captures full
   40-character commit IDs for head and the integration base, and computes one
   immutable merge base. Record the result head, not the implementer's input
   `executed_head`, as the scanned commit. No mutable ref is used thereafter.
2. Enumerate tracked entries using `git ls-tree -r -z <head>` and changed paths
   with a NUL-delimited diff of merge-base to head. Disable external diff,
   textconv and rename detection; a rename is delete+add and includes both names.
   Never split filenames on colon, whitespace or newline. Require UTF-8,
   relative POSIX paths with no empty, dot, parent, control/NUL or backslash
   components; bound each to 512 encoded bytes. Unrepresentable names block.
3. Inventory all tracked manifests/lockfiles at every depth, including tests and
   fixtures. Only profile-pinned exclusions (initially `.git`, `.worktrees`,
   dependency/cache/build outputs) apply; exclusions with tracked source or
   manifest changes produce a blocking coverage gap. Do not inherit gitignore,
   hidden-directory, `tests/` or `backend/frontend` heuristics from legacy scans.
4. Read blob content from the pinned tree into a unique runner-owned directory,
   using exclusive creation and no symlink following. Bound inventory to 10,000
   regular files, 256 manifest/lock inputs, 64 workspace roots and 128 receipts;
   each source/blob <=4 MiB, aggregate source <=64 MiB. Limits are profile data;
   excess blocks `scope_overflow`, never drops a path. All inputs include blob
   IDs and content SHA-256. Mutable worktree content must match before and after.
5. A tracked gitlink/submodule is `unsupported_nested_repo` and blocks until a
   separately approved pinned child scan contract exists. An untracked nested
   repository or any untracked file fails the clean-tree precondition. Ordinary
   nested projects are supported recursively. Do not traverse another `.git`
   directory, follow symlinks or scan external local dependencies; a relevant
   symlink/non-regular input or escaping workspace glob is a blocking gap.

Canonical digests use UTF-8 JSON with sorted keys, separators `,`/`:`, no floats,
and arrays sorted by defined path/receipt key; SHA-256 is lowercase hex64. The
scope digest covers repo key, base/head/merge-base, profile digest, sorted
path/mode/blob/content hashes, changed paths, workspace ownership and expected
units. Nexus builds this inventory from the tree independently of the report.
Producer and consumer compare digests and keys; neither hashes only filenames.

| Scanner family | Expected units and proof |
| --- | --- |
| Gitleaks | One repository unit always, covering merge-base..head committed history with all range objects available. Empty commit range is a documented complete empty scan, not missing execution. |
| Pattern SAST | One repository unit always; supported text suffixes are the portable rule-table suffixes. Every applicable tracked regular source is checked; zero matching sources yields complete `scanned_count=0`, with input digest. |
| Bandit | One repository unit when any tracked `.py` source exists; all such files are explicit targets, batched deterministically if argv limits require. Each batch is an expected unit. Otherwise a single `not_applicable/no_python_sources` family receipt names the verified inventory digest. |
| Python native + OSV | For each `uv.lock` workspace root, one export stage, one pip-audit and one OSV unit. Initially support uv lock version 1, revision 3 (the Orchestra baseline); all other revisions block pending fixtures. All uv workspace members must resolve to in-tree manifests covered by the same lock. Independent nested roots get separate units. |
| JS native + OSV | For each pnpm lock v9 or npm lock v3 root, one native audit and one OSV unit. Validate all `importers`/workspaces and nested independent roots. A member's lack of its own lock is accepted only when its manifest maps to a parent lock importer/workspace. Multiple competing lock managers for one root block ambiguity. |
| Trivy | One repository unit iff required by the trusted per-repository CI coverage declaration. That declaration includes reviewed workflow/called-workflow revisions, scanner set and digest. Absence/ambiguity of this declaration blocks planning; `not_applicable/ci_does_not_require_trivy` needs the trusted declaration, never grep of candidate CI. A CI-policy change invalidates the profile and requires review. |

The initial dependency formats are deliberately bounded: uv workspace v1,
pnpm v9 and npm v3 locks. `requirements*.txt`, pylock-only, Poetry, Yarn, Bun,
Cargo, Go, Maven/Gradle, composer and other manifests are detected and block as
`unsupported_stack_or_lock`, rather than silently going green. A Python/JS
project/source scope lacking a governing lock blocks `missing_lockfile`, even
for documentation-only changes in that repo. A dependency-free source-only scope
requires an explicit reviewed profile declaration bound to its inventory; it is
never inferred from absence of a lock or an installed executable. No private
package namespace is silently removed. Unqueryable indexed/private packages,
unversioned external dependencies and unsupported source types block coverage.
In-tree workspace members are source-scanned and are not registry dependencies.

Known-inapplicable families have one family receipt and no workspace units.
Applicable families have precisely the units in the trusted plan and no family
N/A substitute. Every required family is represented; arbitrary `skipped` is not
a success state. Plan failure returns a bounded failure envelope and no green
gate, even if another family completes.

## 5. Bounded versioned envelope

The wire version is `orchestra.security-envelope/v1`. It is one JSON object,
UTF-8, no BOM, trailing documents, duplicate object keys, NaN/Infinity or invalid
encoding. Maximum depth 16; 65,536 bytes for the complete stdout document;
stderr also retains at most 65,536 bytes. Both Nexus and producer reject
oversize/truncated capture. Producer stdout contains no progress text.

All fields are required, nullable only where stated; no extra keys:

| Record | Fields and invariants |
| --- | --- |
| Envelope | `schema`, `scan_id` UUID, `work_unit_id` UUID, `attempt_id` UUID, `repository` allowlist key <=100, `producer_revision` git40, `producer_digest` hex64, `profile_id` <=100, `profile_digest` hex64, `context_digest` hex64, `head_sha/base_sha/merge_base_sha` git40, `scope_digest/changed_digest/plan_digest` hex64, `complete` bool, `receipts` <=128, `gaps` <=128 typed entries. No authoritative aggregate `passed` field. |
| Receipt | `key` with exact family/scope/batch contract below; `adapter_id` nullable enum below; `tool_version` nullable string of1..64 ASCII characters matching `[A-Za-z0-9][A-Za-z0-9._+-]{0,63}`; `input_digest` hex64; `applicability` enum required/not_applicable; `applicability_reason` nullable enum below; `state`; `exit_code` nullable integer in[-255,255]; `timed_out` bool; `stdout_bytes/stderr_bytes` nonnegative integers; `stdout_truncated/stderr_truncated` bool; `native_digest` nullable hex64; `scanned_count` nullable nonnegative integer; `finding_count` nullable nonnegative integer; `findings` <=128; `omitted_count` nonnegative integer; `error_code` nullable enum. N/A has no execution and proves the trusted reason/digest. |
| Finding | `rule_id` <=100, `advisory_id` nullable <=100, `severity` enum UNKNOWN/INFO/LOW/MEDIUM/HIGH/CRITICAL, `path` nullable valid relative path, `line` nullable positive int, `package` nullable `{ecosystem,name,version}` (32/200/100 bytes), `attribution` enum changed/unchanged/unknown, `attribution_basis` enum source_path/dependency_lock/none. No code, snippet, match, secret, native message, full URL, author/email, absolute path, raw stderr or remediation command. |
| Gap | `code` enum, nullable receipt `key` using the same contract, nullable valid relative `path`; no free-form native text. |
| Nexus decision | `schema=orchestra.security-decision/v1`, scan/SHA/profile/envelope digests, `passed` bool, bounded typed reason codes, receipt keys and safe offending finding identities. This is computed by Nexus and persisted with the original safe envelope. |

`adapter_id` identifies an Orchestra parser contract, not an invented native
schema version. Tools without a native schema version are pinned by exact tool
release, adapter ID and checked fixture shape; unknown versions block. Native
fields may be ignored only when the pinned parser explicitly lists them as
non-authoritative metadata. Required coverage/error/result fields cannot be
absent or change type. Reject unknown finding severity and structural changes.

Terminal states: `complete`, `not_applicable`, `missing_binary`, `unsupported_version`,
`error`, `timeout`, `invalid_report`, `overflow`, `not_run`. All except complete
and justified N/A block. A completed scanner may contain findings and still
block policy: execution completeness and publication eligibility are separate.
`complete=true` requires exact expected receipt keys, no gaps, all required
states complete, all N/A reasons independently valid, no truncation/omissions,
native parse/error/coverage checks satisfied, and all counts equal actual lists.
N/A cannot appear for always-required families.

The request uses `orchestra.security-request/v1` and carries the same identity
and digest fields plus the private repo root, immutable inventory/changed-path
arrays, trusted units and execution context. Context contains the trusted CI
declaration digest and, when Trivy applies, DB artifact digest and acquisition
UTC time (maximum age 24 hours at scan and consumption). No arbitrary map of
scanner flags is accepted. Request <=2 MiB, depth16, and the inventory limits in
§4 apply; the 64KiB capture limit applies to report output, not request input.
Context is canonical-digested independently of the static profile so DB updates
do not require changing the profile; it must match Nexus's retained request.

Receipt `key` is exactly `{family,scope,batch}`. `family` is the enum in this
table; no arbitrary string or other scanner family is accepted. `scope=null`
is the repository unit sentinel, never `.` or an empty path. Dependency unit
scope is the exact governing lockfile path, including its filename, e.g.
`uv.lock` or `dashboard/pnpm-lock.yaml`; it obeys the §4 path/512-byte rules.
`batch` is a strict integer0..127, zero for every unbatched/N/A unit. Only
Bandit may use multiple batches; they are contiguous starting at zero and
exactly equal the trusted plan's batch list. Booleans are not integers in any
wire field; all numeric fields use strict JSON integers.

| key.family enum | Required scope / adapter_id enum |
| --- | --- |
| `gitleaks` | null / `gitleaks-json-8.30.1` |
| `patterns` | null / `portable-patterns-v1` |
| `bandit` | null / `bandit-json-1.9.4` |
| `python-export` | governing uv.lock path / `uv-pylock-0.13.5` |
| `python-audit` | governing uv.lock path / `pip-audit-json-2.10.1` |
| `javascript-audit` | governing pnpm/npm lock path / `pnpm-json-10.34.8` or `npm-json-11.21.1`, exactly the planned manager |
| `osv` | governing supported lockfile path / `osv-json-2.7.0` |
| `trivy` | null / `trivy-json-0.76.1` |

All adapter IDs are bounded by this enum (maximum32 ASCII bytes), not free-form
versions. A required receipt has its planned nonnull adapter ID even on failure;
tool_version is null if the version could not be safely identified. A N/A
receipt has scope=null, batch=0, adapter_id=null and tool_version=null.
For `applicability=required`, `applicability_reason=null`; for
`applicability=not_applicable`, a nonnull reason is mandatory. Allowed N/A
reasons are `no_python_sources` for Bandit, `no_python_dependency_scope` for
python-export/python-audit, `no_js_dependency_scope` for javascript-audit,
`no_supported_dependency_scope` for OSV, and `ci_does_not_require_trivy` for
Trivy. Every reason must match the independently verified inventory/profile;
gitleaks/patterns cannot be N/A. All other combinations reject.
Allowed error/gap codes: `invalid_request`, `identity_mismatch`,
`profile_mismatch`, `scope_drift`, `scope_overflow`, `unsupported_path`,
`unsupported_nested_repo`, `unsupported_stack_or_lock`, `ambiguous_lock`,
`missing_lockfile`, `stale_lock`, `unsupported_dependency_syntax`,
`unsupported_dependency_source`, `configuration_drift`, `missing_binary`,
`unsupported_version`, `native_error`, `native_timeout`, `native_overflow`,
`invalid_native_report`, `coverage_gap`, `evidence_overflow`, `deadline_exceeded`,
`cancelled`, `db_unavailable`, `db_stale`, `not_run`. A completed non-applicable
receipt has null tool version/exit/native digest/counts, no timeout/truncation,
zero captured bytes/findings/omissions and null error. A completed required
receipt has a supported version, valid expected exit, nonnull coverage/findings
counts, native digest and null error. Unsupported state combinations reject.

Each scanner stdout/stderr has the same 64 KiB retained cap. Drain both streams
concurrently, count bytes, flag any extra byte, and terminate the process group
on timeout/cancel; never parse a retained prefix as a complete report. Report
files and export files, if needed, are exclusively created under that unit's
directory and checked while read for the same cap; file output cannot bypass
capture limits. Version probes have 4 KiB/10 s caps; scanner units have 300 s,
uv export 60 s; whole scan has 3,600 s. A stopped/unstarted expected unit gets
`not_run` and blocks. Continue other planned units after an ordinary scanner
failure while the attempt/deadline remains valid so the envelope is diagnostic.

Never clip to the first 20 or first 128 findings then mark complete. If full
normalized evidence would exceed count/byte caps, emit a minimal blocking
`overflow` envelope with `complete=false`, explicit `omitted_count` and every
expected receipt represented; omit findings only in this blocking diagnostic.
If even that cannot fit, process failure/overflow alone blocks. A HIGH finding
after 64 KiB must block due to overflow, whether or not its content was retained.

## 6. Native adapter contracts (primary-source verified)

Pins below were checked against upstream tagged source on 2026-10-23 using
GitHub's read-only API and official documentation. They are supported target
versions, not claims about installed binaries. No tool was installed or scanned.
All commands are fixed argv arrays; placeholders denote validated plan paths,
never report content. Version probes must exactly match these release versions.

### Gitleaks 8.30.1, adapter `gitleaks-json-8.30.1`

`gitleaks version`; then `gitleaks git --no-banner --redact=100 --no-color
--config <trusted-gitleaks.toml> --ignore-gitleaks-allow --exit-code 10
--report-format json --report-path - --log-opts <merge-base>..<head> <repo>`.
Require all Git history objects for the range. Use trusted config without
candidate-controlled allowlists/baselines. Gitleaks also auto-loads the target's
`.gitleaksignore`; preflight rejects its presence unless its exact content is
already explicitly authorized by the trusted profile (initial profile: none).
Do not assume `--gitleaks-ignore-path` disables the target's second auto-load.

Native JSON is an array of Finding records. Validate `RuleID`, `File`,
`StartLine`, `Commit`; only normalized safe fields survive. Exit 0 requires an
empty array; exit 10 requires findings; exit 1/126/other is failure even if a
valid-looking partial report exists. Every Gitleaks finding blocks, preserving
the separate gate's stronger secret policy, including an intermediate commit
whose final path is deleted/unchanged. No secret-derived raw fingerprint is
published. Sources: [CLI and exit order](https://github.com/gitleaks/gitleaks/blob/v8.30.1/cmd/root.go),
[Git command](https://github.com/gitleaks/gitleaks/blob/v8.30.1/cmd/git.go),
[native fields](https://github.com/gitleaks/gitleaks/blob/v8.30.1/report/finding.go).

### Reused pattern SAST, adapter `portable-patterns-v1`

Internal explicit-file adapter, no shell. Its rule IDs and regex/severity/suffix
table are versioned Orchestra assets derived from the portable source above;
the profile covers their digest. Use strict decode/read errors, all matches,
no candidate `nosec`, and no untrusted recursive discovery or raw line evidence.
The supported categories remain secrets, SQL injection, XSS, command injection,
deserialization, weak crypto and tenant-ID input. This is a bounded adaptation
of existing checks, not a new generic language-analysis engine. It produces the
same safe finding model, including explicit zero findings and coverage count.

### Bandit 1.9.4, adapter `bandit-json-1.9.4`

`bandit --version`; then `bandit --format json --severity-level all
--confidence-level all --ignore-nosec --ini <trusted-empty-ini>
--configfile <trusted-bandit.yaml> <explicit-python-files...>` from isolated cwd.
No baseline, exclusions supplied by the candidate or `--exit-zero`. Trusted
configuration selects the full default plugin set. Input batching is fixed in
the plan; skipped/error filenames or missing metrics coverage block.
Validate top-level `results`, `errors`, `metrics`, `generated_at`; result fields
include filename, test_id, issue_severity/confidence and line_number. Nonempty
`errors` blocks even at exit 0/1. Exit 0 must have no results; exit 1 must have
results; 2/other blocks. Preserve legacy Python MEDIUM+ blocking repository-wide;
do not turn unchanged MEDIUM findings into an exception. Sources:
[CLI](https://github.com/PyCQA/bandit/blob/1.9.4/bandit/cli/main.py),
[JSON formatter](https://github.com/PyCQA/bandit/blob/1.9.4/bandit/formatters/json.py).

### uv 0.13.5 export and pip-audit 2.10.1

The exact installed exporter is part of the profile. `uv --version`; then
`uv --no-config --offline --no-managed-python --no-python-downloads export
--frozen --format pylock.toml --all-packages --all-extras --all-groups
--no-emit-workspace --output-file <unit>/audit-input/pylock.toml` in the isolated
workspace manifest tree. No sync/install/build or network resolution. Exit 0,
valid pylock v1 and unchanged input hashes are required. All indexed locked
name/version tuples, including development, optional and platform branches,
must occur in the exported inventory. Compare tuples to uv.lock, excluding only
in-tree workspace packages already source-covered; missing tuples/conflicting
extras/export failure is a coverage gap, not permission to audit a subset.
`--frozen` alone does not prove manifest freshness. Compare every workspace
member's `project.dependencies` and plain string `dependency-groups` arrays to
its lock `package.metadata.requires-dist` and `package.metadata.requires-dev`.
Parse both sides with the pinned `packaging.requirements.Requirement` and use
Requirement equality/set equality, including normalized name/extras, specifier
and Marker equality. Reconstruct each lock requirement from only its documented
`name`, `extras`, `specifier` and optional `marker` fields; preserve all other
source-selection fields for the separate comparison below. Never evaluate
markers against the runner platform and discard other branches. Require equal
`SpecifierSet` values for requires-python, or one exact normalization pair
explicitly listed in the trusted repo profile, and matching workspace name/version.
The required initial Orchestra pair is declared `>=3.12,<3.13` and locked
`==3.12.*`: uv canonicalizes this, while packaging's general range equality
retains a prerelease-boundary distinction. Accept only this approved pair,
not sampled-version tests or a hand-written interval solver. Nexus's `>=3.12`
compares directly. A changed unmatched Python constraint blocks pending profile
review; it is never inferred equivalent.
Duplicate requirements, missing member metadata or non-equivalence block
`stale_lock`; marker algebra the parser does not recognize as equal also blocks,
never receives a custom logical-equivalence implementation.

`tool.uv.constraint-dependencies` is compared by the same requirement objects
to lock `manifest.constraints`. `tool.uv.sources` initially supports indexed
registry selection only: resolve its index name through `tool.uv.index`, require
the exact profile-approved credential-free HTTPS URL and `explicit=true`, and
compare the corresponding `index` metadata in lock requirements/constraints
and registry package sources. Implicit public packages must use the profile's
public index URL. Changed source/constraint/index mappings invalidate freshness
and attribution. Reject unsupported `tool.uv` resolution knobs, URL/Git/external
path requirements, `project.dynamic`, optional-dependency tables and group
includes as `unsupported_dependency_syntax`/source rather than resolving them.
In-tree workspace members with static project metadata are allowed and their
name/path set must match the lock workspace member list (or its documented
implicit single-project root). Every indexed tuple including transitive marker/
extra branches is audited. The native export still requests all groups/extras
and omission of any expected tuple blocks. This explicitly covers the syntax
observed in Orchestra and Nexus, including `adlimen-harness[typesafe]`,
`uvicorn[standard]`, Nexus's constraints and explicit Forgejo index mapping.
Do not replace this with `uv --locked` or assume `--no-build` is isolation:
upstream explicitly permits first-party/editable build backends in that mode.

`pip-audit --version`; then `pip-audit --locked --strict --format json
--desc off --aliases on --progress-spinner off <unit>/audit-input`.
`--locked` reads `pylock.toml`/`pylock.*.toml`, **not uv.lock**. This route parses
versioned packages without installing candidate project/build code. Require
`dependencies` plus `fixes` arrays, name/version/vulns for every expected tuple;
`skip_reason`, missing tuple, nonempty fixes, malformed output or error blocks.
Exit 0 requires no vulnerabilities; exit 1 with a complete valid vulnerability
report means completed-with-findings, but exit 1 without it is an error. All
pip-audit vulnerabilities block repository-wide, regardless of severity, fix
availability or changed files; preserve the existing stronger Python policy.
Do not drop `adlimen-*` packages or treat unknown service results as clean.
Sources: [uv formats](https://github.com/astral-sh/uv/blob/0.13.5/docs/concepts/projects/export.md),
[uv CLI flags](https://github.com/astral-sh/uv/blob/0.13.5/crates/uv-cli/src/lib.rs),
[uv lock revisions/metadata](https://github.com/astral-sh/uv/blob/0.13.5/crates/uv-lock/src/lock/mod.rs),
[requirement equality/parser](https://github.com/pypa/packaging/blob/26.3/src/packaging/requirements.py),
[marker API](https://packaging.pypa.io/en/stable/markers.html),
[pip CLI/error handling](https://github.com/pypa/pip-audit/blob/v2.10.1/pip_audit/_cli.py),
[pylock collection](https://github.com/pypa/pip-audit/blob/v2.10.1/pip_audit/_dependency_source/pylock.py),
[JSON fields](https://github.com/pypa/pip-audit/blob/v2.10.1/pip_audit/_format/json.py).

### pnpm 10.34.8 / npm 11.21.1 native audit

Support these two adapters independently; newer pnpm 11/12 has different audit
behavior and is not implicitly accepted. Exact binary versions are probes via
`pnpm --version` / `npm --version`. For pnpm:
`pnpm --dir <workspace> audit --json --audit-level low --registry <trusted-registry>`.
For npm: `npm --prefix <workspace> audit --json --audit-level low
--package-lock-only --include=dev --include=optional --include=peer
--ignore-scripts --registry <trusted-registry> --userconfig <trusted-empty>
--globalconfig <trusted-empty>`. Never `fix`, omit, ignore-unfixable,
ignore-registry-errors or an allowlist. Run only in a derived manifest/lock tree
with root/importer dependency fields intact and candidate config/suppression,
hooks, package-manager auto-download and scripts excluded. Profile-pinned empty
user/global config and minimal environment prevent inherited registry/audit
settings. Derived input digest binds both original blobs and projection rules.

Use PyYAML6.0.3's pure-Python SafeLoader with a small strict loader wrapper:
reject aliases/anchors, explicit tags, merge keys, duplicate mapping keys,
multiple documents, non-string mapping keys, depth>32 or >100,000 nodes before
construction; input still has the §4 blob limit. A safe tag loader alone does
not reject duplicate keys/resource amplification. No FullLoader/UnsafeLoader,
custom YAML objects or LibYAML fallback. The locked dependency version is
already present in Orchestra. Source:
[PyYAML safe loader](https://github.com/yaml/pyyaml/blob/6.0.3/lib/yaml/__init__.py),
[mapping construction](https://github.com/yaml/pyyaml/blob/6.0.3/lib/yaml/constructor.py).

JS lock freshness is a direct structural comparison, not semver resolution:
for each manifest, compare every dependency/dev/optional/peer name and its exact
declared string to pnpm importer's `specifier` records, or npm lock v3's matching
`packages[workspace-relative-path]` dependency fields. pnpm may substitute a
governing override into the importer specifier. Such a mismatch is accepted
only by an exact trusted-profile binding `(workspace,group,name,declared,
override-selector,override-value,locked-specifier)`; verify the manifest and
lock override tables are equal and that the named selector/value is present.
For Nexus dashboard, the initial three bindings are dependencies
`@tanstack/react-router: ^1 -> 1.168.23` (same-name selector), devDependencies
`@tanstack/router-plugin: ^1 -> 1.167.22` (same-name selector), and
`vite: ^6 -> 6.4.4` (selector `vite@>=6 <7`). These bindings are profile-owned,
not a report/candidate exception; any changed declaration, selector, value or
unlisted mismatch blocks a stale lock/profile until reviewed. This avoids
adding a JS resolver merely to prove lock freshness. Workspace/importer set,
links and override/resolution metadata must agree with the inventoried
manifests; absent, ambiguous or unsupported records block. Reject external
file/Git/URL dependencies; permit only in-tree workspace links whose members
are explicitly covered. The audit copy's package.json projection keeps only
name, version, private, validated workspaces, dependency maps and governing
overrides; it removes scripts, packageManager and audit-ignore/config fields.
The pnpm workspace projection keeps only validated member patterns, never
candidate hooks, registry or audit options. Original manifests and exact
projection digests remain in the request. Dependency graph walking stays in
the native tools; this code only verifies expected inputs and native coverage.

pnpm JSON has `actions`, `advisories` map, `muted`, `metadata.vulnerabilities`
and dependency counts. Validate each advisory's module_name, severity and all
findings version/paths. `muted` must be empty; no ignored advisories; parse the
entire map. It has no native schemaVersion: the pinned source shape is authority.
npm requires native `auditReportVersion=2`, `vulnerabilities` map, metadata
counts; validate each entry's name/severity/via/effects/range/nodes. Resolve via
references within the report, reject dangling/cyclic ambiguity rather than
assuming a package name is an advisory. Native node paths are package graph
evidence, never source-file attribution by themselves.

Exit 0 requires no report findings; exit 1 requires a valid, complete report
with findings; any error object/registry error, inconsistent totals, unsupported
lock or schema, other exit, skipped dependency or unknown coverage blocks. The
consumer permits LOW/MEDIUM dependency findings only with certain attribution;
HIGH/CRITICAL exposure and uncertain attribution block (§8). Sources:
[pnpm handler](https://github.com/pnpm/pnpm/blob/v10.34.8/lockfile/plugin-commands-audit/src/audit.ts),
[pnpm fields](https://github.com/pnpm/pnpm/blob/v10.34.8/lockfile/audit/src/types.ts),
[all-importer walk](https://github.com/pnpm/pnpm/blob/v10.34.8/lockfile/audit/src/lockfileToAuditTree.ts),
[npm command](https://github.com/npm/cli/blob/v11.21.1/lib/commands/audit.js),
[npm report v2](https://github.com/npm/cli/blob/v11.21.1/workspaces/arborist/lib/audit-report.js),
[npm finding fields](https://github.com/npm/cli/blob/v11.21.1/workspaces/arborist/lib/vuln.js).

### OSV-Scanner 2.7.0, adapter `osv-json-2.7.0`

`osv-scanner --version`; then `osv-scanner scan source --format json
--all-packages --no-resolve --no-call-analysis=go,rust
--config <trusted-empty-osv.toml> --lockfile <exact-lock>` per lock unit.
No recursive autodiscovery, allow-no-lockfiles, suppression or reachability
discount. Explicit config overrides candidate config. Validate `results`, source
path/type=lockfile, packages with name/version/ecosystem, vulnerabilities and
groups. `groups[].max_severity` is a numeric-string score (or empty), not a
severity label. Map finite score 0..10 to INFO=0, LOW>0..<4, MEDIUM>=4..<7,
HIGH>=7..<9, CRITICAL>=9; missing/invalid severity is UNKNOWN and blocks. Every
vulnerability must belong to a validated group; MAL-* always blocks. Aliases
may deduplicate display but never hide instances or lower maximum severity.

Require source/package coverage against the lock/export inventory; empty output
is not proof of a scan. 0 requires covered packages and no findings; 1 requires
covered packages and findings; 127 general error, 128 no packages, 129 API
failure, 130 invalid config and all other exits block. The tool has no native
schemaVersion; bind to the pinned v2 model. Sources:
[flags](https://github.com/google/osv-scanner/blob/v2.7.0/cmd/osv-scanner/internal/helper/flags.go),
[output/exit codes](https://github.com/google/osv-scanner/blob/v2.7.0/docs/output.md),
[actual exit handling](https://github.com/google/osv-scanner/blob/v2.7.0/cmd/osv-scanner/internal/cmd/run.go),
[result model](https://github.com/google/osv-scanner/blob/v2.7.0/pkg/models/results.go),
[supported locks](https://github.com/google/osv-scanner/blob/v2.7.0/docs/supported_languages_and_lockfiles.md).

### Trivy 0.76.1, adapter `trivy-json-0.76.1`

`trivy --version`; then `trivy fs --format json --exit-code 10
--severity UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL --list-all-pkgs --include-dev-deps
--config <trusted-trivy.yaml> --ignorefile <trusted-empty-ignore>
--scanners <trusted-ci-scanner-set> <snapshot>`.
The scanner set is the CI-required set, never derived from output; retain
secret/misconfig coverage when CI requires it. Config must contain no
suppression, VEX acceptance, severity reduction, skip paths or ignore-unfixed.
Validate native `SchemaVersion=2`, `Trivy.Version=0.76.1`, ArtifactType and typed
Results with Targets, Packages and all relevant Vulnerabilities,
Misconfigurations and Secrets; UNKNOWN result types/severities block. Native
optional arrays may be absent only as documented empty collections. Record
trusted vulnerability DB identity/freshness in the per-run profile context;
unavailable/stale database or missing required analyzer coverage blocks.
Exit 0 must agree with no failed findings; exit 10 with a valid failed result
means completed-with-findings; 1/other blocks even if partial JSON exists.
Sources: [CLI flags](https://github.com/aquasecurity/trivy/blob/v0.76.1/docs/guide/references/configuration/cli/trivy_filesystem.md),
[native model](https://github.com/aquasecurity/trivy/blob/v0.76.1/pkg/types/report.go),
[schema constant](https://github.com/aquasecurity/trivy/blob/v0.76.1/pkg/report/writer.go),
[exit order](https://github.com/aquasecurity/trivy/blob/v0.76.1/pkg/commands/artifact/run.go),
[exit implementation](https://github.com/aquasecurity/trivy/blob/v0.76.1/pkg/commands/operation/operation.go).

## 7. Scratch, environment and completeness

Nexus creates a mode-0700 random per-scan directory beneath its configured
runner scratch root; producer creates per-unit subdirectories exclusively.
Never shared `/tmp/osv-results.json`, global freshness markers, inherited venvs
or caches. Use task-owned TMPDIR/XDG/cache/config locations. Do not repurpose
HOME or read local credentials/settings; only explicit trusted config inputs
are read. The runner's existing allowlisted environment is the starting point;
service/mail/cloud credentials and scanner override variables are absent.
The profile declares approved audit/DB services as a runner capability
requirement. This slice does not enforce OS egress isolation: an argv/env
allowlist or a scanner's `--registry` argument cannot do that. Envelope mode
may run synthetic local tests without network; live activation requires #170's
verified runner enforcement (network namespace/firewall or equivalent runner
capability) plus artifact/snapshot write isolation and process execution
restrictions. Missing/unknown capability blocks activation, and the evidence
must identify the runner profile revision that was verified. Do not claim the
existing `procs._process_env` blacklist provides isolation or secret confinement.
Authentication,
where required, is a separate scoped runner credential capability and is never
serialized; missing capability blocks rather than falling back anonymously.

No candidate lifecycle/build hooks, binary, test helper, shell startup file,
native plugin or package install executes. All native tools run by configured
absolute paths with process-group timeout/cancellation. Snapshot and input
hashes are checked before and after; drift blocks. Native output is untrusted:
validate types/path containment first, then map only safe identifiers. Raw
reports/stderr are not uploaded or appended to result/Slack/PR bodies.

Terminal envelope facts are sufficient for the bounded gate, not proof that
the tools detect every vulnerability. A clean result means all declared checks
completed on the pinned scope. Tool/database provenance and corpus coverage
remain part of independent review and later activation evidence.

## 8. Attribution and fail-closed decision

Nexus recomputes attribution from its trusted changed set; the producer's label
is diagnostic. Source path must match one exact inventoried path. If changed,
all findings on that file are in scope (no line-only exemption). For a certain
unchanged source path, ordinary SAST HIGH/CRITICAL is recorded as unchanged and
does not itself block this changed-file gate; Gitleaks and Python's stronger
rules above still block. Missing, external, ambiguous or unresolvable paths
yield unknown attribution and block regardless of severity. UNKNOWN severity
also blocks. No exception is inferred merely because a finding is old.

Dependency findings are exposures, not grep locations: associate every affected
package/version with its governing workspace lock and manifests. If any
governing lock/manifest/workspace membership/override changed, classify
`changed` conservatively for all findings under that lock, including transitive,
dev and optional dependencies. No solver or dependency delta exemption is
introduced in v1. When those inputs did not change, a package vulnerability
still lacks proof of attribution to an unchanged source file; classify
`unknown` and block. A source-only edit does not make a vulnerable dependency
irrelevant. This preserves the current unscoped blocker and avoids inventing a
legacy-vulnerability allowance. Python pip-audit and Bandit MEDIUM+ additionally
block as specified regardless of attribution.

Consumer order: reject outer process failure/timeout/truncation; parse strict
wire schema; compare scan/attempt/repo/producer/profile/SHA/digests against
trusted expected values; require exact one-to-one receipt keys; validate N/A,
native parse/exit/coverage facts and completeness; recompute finding policy;
persist safe evidence; then return passed or blocked. Producer exit codes are
0 = full valid envelope produced (may contain policy blockers), 2 = invocation/
internal failure. Neither producer exit 0 nor `complete=true` authorizes a pass.
Any contradiction blocks with typed codes; native error text never becomes the
user-facing detail.

Before publication, require unchanged head, base/profile context and a persisted
passing decision for that exact head. If review changes code/head or policy
changes, invalidate security and rerun through normal workflow; do not reuse a
stale envelope. A restart may read the persisted envelope/decision only after
matching the same immutable request context and current authority; absent or
uncertain evidence blocks. This slice does not implement general restart logic.

## 9. One Gitleaks owner and compatibility order

The v1 Orchestra producer owns exactly one Gitleaks invocation and receipt.
Nexus's `secrets` GateResult is a projection of that validated receipt using
the stronger all-secret policy; `security` evaluates the full envelope. They
share one scan ID/digest/SHA, never run independent scans that can disagree.
Envelope failure makes both gates block when Gitleaks evidence is unavailable.

Introduce explicit trusted `security_mode=legacy|envelope_v1`. Default legacy
preserves the existing separate `run_secrets_gate` plus legacy scanner path and
cannot satisfy issue189/activation. Envelope mode calls the new producer once
and never calls `run_secrets_gate`. No auto-detection or fallback based on
Markdown/JSON output. The config validator rejects legacy scanner_path mixed
with envelope settings. Keep legacy parser tests until the deliberate later
deactivation; no shared scanner edits.

Order: implement producer/consumer and cross-contract tests inert; independent
review and exact-head CI; package/pin reviewed artifacts separately; prepare
trusted repo/CI profile and parity evidence; explicitly authorize activation;
switch the one mode atomically; confirm one Gitleaks process. Rollback to legacy
also disables envelope-required publication/worker activation; it cannot waive
the complete-envelope gate. No live config change is authorized by this spec.

## 10. Persistence and user-safe evidence

Add optional `security_evidence` to `OrchestraTaskResult` containing the bounded
envelope, its canonical digest and consumer decision. Persist via the existing
fenced `queue.set_stage`/AttemptController before moving toward review/publish.
An Atrium failure/readback mismatch blocks; local scanner success cannot bypass
it. Reuse existing `result` JSON storage/API with no new Atrium table/endpoint
or schema migration. Lease loss makes the outcome non-authoritative.

GateResult detail is a short fixed summary of reason codes and safe relative
identities. PR/notification output receives summary and existing work-item
reference, not the entire native report. Historical results may lack
security_evidence and still display as historical; they cannot satisfy a new
envelope-v1 gate. Public rendering must retain Atrium's existing redaction.

## File Manifest

This design task writes only this spec. Future implementation must start with
the following per-repository manifest; changes outside it require scope review.
No global skill/config, live runtime or automatic deploy workflow is included.

Orchestra (relative to repository root):

- `src/orchestra/security/__init__.py`: public typed entry.
- `src/orchestra/security/__main__.py`: CLI.
- `src/orchestra/security/bootstrap.py`: trusted isolated artifact bootstrap;
  artifact assembly places these exact reviewed bytes at its root.
- `src/orchestra/security/contracts.py`: stdlib records and strict JSON.
- `src/orchestra/security/profile.py`: trusted profile loading.
- `src/orchestra/security/inventory.py`: explicit inventory.
- `src/orchestra/security/process.py`: bounded process execution.
- `src/orchestra/security/producer.py`: execution and envelope assembly.
- `src/orchestra/security/lock_metadata.py`: bounded requirement/index/override
  equality checks using packaging and strict YAML, never dependency resolution.
- `src/orchestra/security/patterns.py`: reused pattern adapter.
- `src/orchestra/security/python_audit.py`: Python audit and Bandit adapters.
- `src/orchestra/security/js_audit.py`: JavaScript native audit adapters.
- `src/orchestra/security/osv.py`: OSV adapter and native parsing.
- `src/orchestra/security/trivy.py`: Trivy adapter and native parsing.
- `src/orchestra/security/gitleaks.py`: Gitleaks adapter and native parsing.
- `src/orchestra/security/profiles/pilot-v1.json`: complete immutable profile,
  native pins, command IDs, limits, rule digest, suppression-free config assets.
- `src/orchestra/security/profiles/gitleaks.toml`: trusted Gitleaks settings.
- `src/orchestra/security/profiles/bandit.yaml`: trusted Bandit settings.
- `src/orchestra/security/profiles/bandit.ini`: trusted Bandit INI settings.
- `src/orchestra/security/profiles/osv.toml`: trusted OSV settings.
- `src/orchestra/security/profiles/trivy.yaml`: trusted Trivy settings.
- `tests/unit/security/test_contracts.py`.
- `tests/unit/security/test_inventory.py`.
- `tests/unit/security/test_process.py`.
- `tests/unit/security/test_producer.py`.
- `tests/unit/security/test_native_adapters.py`.
- `tests/unit/security/test_patterns.py`.
- `tests/contract/security/test_nexus_consumer.py`: real producer subprocess
  through real consumer, via explicit isolated Nexus candidate source path.
- `evals/synthetic/security-envelope-v1.json`: scenarios and expected decisions;
  no real native logs, credentials, runtime paths or session content.
- `pyproject.toml`: promote the already locked packaging26.3/PyYAML6.0.3 pins
  to runtime dependencies; include contract-test path/marker and packaged
  profile assets if hatch requires it.
- `uv.lock`: matching runtime dependency metadata; no unrelated version bump.
- `.forgejo/workflows/security-contract.yml`: explicit dispatch-only pair job
  described below; no live scanner/deploy behavior.
- `README.md`.
- `docs/architecture.md`.
- `docs/codebase/INDEX.md`.
- `docs/codebase/architecture.md`.
- `docs/codebase/test.md`.
- `docs/development/security-envelope.md`.
- `CHANGELOG.md`.
- `docs/specs/2026-10-23-security-envelope-issue-189.md`.

Empty-ignore/config content is generated exclusively into per-run scratch from
profile data, not stored in global locations.

Nexus (relative to repository root):

- `src/nexus/orchestra/security_contract.py`: independent strict consumer schema.
- `src/nexus/orchestra/security_plan.py`: trusted plan builder.
- `src/nexus/orchestra/security_gate.py`: security policy and validation.
- `src/nexus/orchestra/config.py`: explicit mode and trusted configuration.
- `src/nexus/orchestra/gates.py`: single-producer call and secrets projection.
- `src/nexus/orchestra/service.py`: evidence persistence and head freshness.
- `src/nexus/orchestra/models.py`: security evidence model integration.
- `src/nexus/orchestra/procs.py`: add stdin/minimal-env injection without
  weakening current capture/process-group behavior; preserve existing API users.
- `config/orchestra.example.toml`: inert example of explicit mode and required
  trusted profile/producer context; no private/live config edits.
- `tests/unit/orchestra/test_security_contract.py`.
- `tests/unit/orchestra/test_security_plan.py`.
- `tests/unit/orchestra/test_security_gate.py`.
- `tests/unit/orchestra/test_config.py`.
- `tests/unit/orchestra/test_gates.py`.
- `tests/unit/orchestra/test_procs.py`.
- `tests/unit/orchestra/test_service.py`.
- `tests/unit/orchestra/test_pipeline_evidence.py`.
- `tests/integration/test_orchestra_security_contract.py`: existing fake Atrium
  harness verifies fenced safe evidence persistence and failed persistence.
- `.forgejo/workflows/ci.yml`: include the security evidence persistence test in
  its existing real-Atrium contract job; no service activation.
- `docs/operations/orchestra.md`.
- `docs/codebase/INDEX.md`.
- `docs/development/security-envelope.md`.
- `CHANGELOG.md`.

Atrium: **no implementation files** in this slice. Existing fenced work-item
result persistence is reused. If its tested size/redaction contract cannot
accept the bounded evidence, stop that integration, record the exact mismatch
and amend the manifest before adding an API/table or silently storing less.

## 12. TDD sequence and issue mapping

The implementation pair is reviewed as a pair. Synthetic fixture executables
are generated in each pytest temp directory; each answers its real --version
probe and native argv/output contract. Real producer execution plus real Nexus
consumer validation is mandatory: parser-only fixtures are insufficient.
The test harness may inject allowlisted fake executable paths/digests into its
own trusted test profile, never through the untrusted envelope.

The following REQ IDs are readiness-tool aliases of the existing SE acceptance
rows below. They add no requirements and do not widen the approved scope:

| Requirement alias | Existing acceptance mapping |
| --- | --- |
| REQ-01 | SE-01: strict schema, identity and receipt completeness. |
| REQ-02 | SE-02: capture/serialization bounds and complete findings. |
| REQ-03 | SE-03: required scanner failures and native result integrity. |
| REQ-04 | SE-04: workspace, lock, input and applicability coverage. |
| REQ-05 | SE-05: immutable revision, profile and artifact binding. |
| REQ-06 | SE-06: approved severity and attribution policy. |
| REQ-07 | SE-07: one Gitleaks owner and persisted safe evidence. |
| REQ-08 | SE-08: exact-pair contract CI and independent delivery gates. |

| Phase / test IDs | RED first, then minimum implementation / verification |
| --- | --- |
| P1 / SE-01 | Strict schema, duplicate JSON keys/receipts, missing/unexpected scanner, missing fields, unknown wire/adapter/tool/native schema, malformed UTF-8/JSON, false complete/counts, forged N/A/profile list. Build contracts/profile/inventory only. Verify independent consumer rejects each. |
| P2 / SE-02 | Real producer with fake binaries: HIGH after >65,536 stdout bytes; same on stderr/report/export file; exactly-cap vs cap+1; relevant 21st finding after 20 unchanged findings; findings-count and serialized-envelope overflow. Verify whole chain blocks overflow and catches 21st without clipping when within cap. |
| P2 / SE-03 | One required scanner missing/error/timeout while another returns valid JSON; failure exit plus empty/valid-looking native report; malformed native JSON; pip exit1 fatal vs complete findings; Bandit errors[]; Gitleaks partial JSON exit1; OSV127/128/129/130; JS registry error; Trivy error with JSON. Real producer emits every expected receipt, consumer blocks. |
| P3 / SE-04 | Nested workspaces/importers, independent nested projects, missing/stale lock, multiple locks, unsupported schema/stack, submodule, escaping/symlink path, untracked tree, unsafe/invalid filenames, exclusion covering changed source, omitted export tuple, skipped private dependency, tool config suppression. Verify applicability is based on tree/trusted profile and gaps block. |
| P3 / SE-05 | All applicable units complete and no findings: passes only on same repo/scan/attempt/head/base/profile/scope/plan and executable digests. Mutate each identity, change HEAD during scan and before publish, replay another attempt, change trusted CI requirement: all block. |
| P4 / SE-06 | Changed HIGH/CRITICAL source, uncertain LOW source, missing severity, changed transitive dependency exposure, source-only edit with vulnerable unchanged lock, pnpm HIGH, Gitleaks all-secret, Python pip LOW and Bandit unchanged MEDIUM. Verify approved severity rules and stronger legacy Python rules; no invented baseline exception. |
| P4 / SE-07 | Nexus service invokes one Gitleaks producer process in envelope mode; secrets/security projections share identity; legacy mode remains explicit, mixed settings reject, no JSON/Markdown fallback. Persistence success/readback failure/lease loss and public redaction use existing Atrium harness. |
| P5 / SE-08 | Cross-repository Forgejo job checks out exact Orchestra/Nexus candidate SHAs, invokes the real CLI + consumer test, retains safe decision fixture evidence. Unit and cross-contract tests are CI-required, never optional/skipped when CI=true. Independent review of exact pair and complete successful exact-head Forgejo CI are separate delivery gates. |

Avoid circular commit pins in the two repos. Orchestra's dispatch-only
`security-contract.yml` accepts two mandatory full commit inputs,
`orchestra_sha` and `nexus_sha`; it validates git40, checks out each under its
own directory with `persist-credentials=false`, verifies both local HEADs equal
the inputs, and refuses moving branch refs. Reuse existing source-read
credential handling if needed; missing read capability fails the job. It runs
Nexus's frozen environment and the Orchestra contract test under that
interpreter with explicit source roots: `NEXUS_SECURITY_CONTRACT_ROOT=<nexus>`
and `ORCHESTRA_SECURITY_CONTRACT_ROOT=<orchestra>` are test-only inputs. The
test invokes the real bootstrap artifact assembled in its own temp directory,
then imports the real consumer from the verified Nexus source. Failure to load
either candidate is a failure, never a skip. Record both SHA values and the
safe fixture-decision digests in job output. Central review requires a complete
successful task run for that exact pair in addition to each repository's
normal exact-head PR CI; dispatch runs may have zero aggregate checks and are
verified by their exact-SHA job tasks. No installable scanner is needed: only
fake binaries and existing frozen Python test dependencies are used.

Issue189 security-envelope acceptance maps to SE-01..SE-08; its two explicit
fault cases (>64 KiB HIGH and failed subscanner beside valid report) map to
SE-02/SE-03. OSA-6 production-scanner controlled fixture proof remains an
activation requirement after code review; synthetic binaries prove the
executable contract, not installed scanner operation or live isolation.

Use existing Python 3.12/frozen environments. Focused tests first; then existing
Orchestra unit tests and Nexus orchestra/procs regressions, Ruff formatting/
lint and strict typing for changed sources, configured security validation and
required Forgejo CI. No runtime scan or scanner installation is part of this
design's validation receipt. Independent reviewer is scheduled by central,
never the implementation author.

## 13. Handoff, readiness and outstanding acceptance

Real-target read-only metadata verification was performed, without scanning or
installing anything, against both immutable baselines. Using the already
available packaging26.3/PyYAML6.0.3 environment only as parsers established:

| Target | Verified shape / implications |
| --- | --- |
| Orchestra `pyproject.toml`, `uv.lock` | uv1/rev3, zero project runtime requirements and one dev group; requirement/group/constraint metadata matches. Python range normalization needs the exact profile pair above. No private registry tuples. |
| Nexus `pyproject.toml`, `uv.lock` | uv1/rev3; 13 direct requirements including two extras, 11 constraints, explicit Forgejo source mapping and 12 private indexed package tuples. Requirement/group/constraint/index metadata comparisons match; plain-name-only grammar would have excluded Nexus and has been replaced. |
| Nexus `dashboard/package.json`, `dashboard/pnpm-lock.yaml` | pnpm lock9; override tables match; exactly the three direct specifier normalization bindings above are needed. `packageManager=pnpm@10.33.0` does not select the audit binary: the trusted adapter pin is10.34.8 and is isolated from candidate package-manager switching. |
| Trivy CI applicability | Nexus's only executable workflow is its direct ci.yml and contains no Trivy requirement. Orchestra calls lib-py-ci/test at adlimen-cicd v3.6.0; both reviewed reusable workflows contain no Trivy invocation. Initial trusted declarations may therefore mark Trivy N/A for these baselines. A different repo/CI revision needs its own reviewed declaration. |

The CI source for Orchestra's inherited MEDIUM+ Python gate is
[lib-py-ci v3.6.0](https://github.com/matteocervelli/adlimen-cicd/blob/v3.6.0/.forgejo/workflows/lib-py-ci.yml).
These are metadata/source checks, not passing scanner runs. They establish a
real Orchestra pilot path and the syntax needed for Nexus, not a clean result.

One genuine live-coverage uncertainty remains: native public vulnerability
services' handling of Nexus's 12 private indexed package tuples and private npm
package `@adlimen/ui-react` has not been exercised or verified. Do not label
Nexus pilot-ready on the basis of public-package fixtures. The specified behavior
is to submit every indexed tuple, reject skipped/error/unsupported results, and
block if coverage is unknown; no `adlimen-*` exclusion or namespace exception.
Before a Nexus pilot can pass, the separately authorized installed-scanner
canary must prove complete coverage for those exact inputs or provide a reviewed
private-advisory coverage contract/profile extension. This design does not
invent such a service or change policy to make that gap green. The real
Orchestra repository has no private dependency tuples and is the bounded first
pilot; Nexus remains a required follow-on coverage check before its activation.

All native JSON shapes above are pinned to verified primary source; native
schemas without numeric versions are explicitly named as such. There is no
claimed installed-tool parity or clean scan. Implementation must preserve these
pins and add fixtures before accepting a different version/schema. Frozen
locks, exporter completeness and CI policy are validated contracts, not guessed
by tool availability.

The bounded producer/consumer implementation can proceed after root accepts
this design, with support limited to the declared formats. Before enabling it
for a real repo, an authorized operator must provision/verify exact artifact
digests, trusted repo/CI profile, audit registry capability and DB freshness;
these deployment-specific values are deliberately not fabricated here. If
upstream/output verification during implementation contradicts any pinned
contract, stop that adapter and mark the design not implementation-ready until
corrected; do not make the parser permissive.

Still outstanding for issue189: declarative full SDLC steps/input/output and
restart idempotence; issue search/clarification behavior; independent reviewer
identity and same-SHA review/Forgejo CI invalidation; real dual-forge publication
restart/fault-injection acceptance after first push/PR; protected orchestrator
integration authorization. Existing #185 publisher/recovery primitives must be
reused and tested, not claimed complete by this security spec. #170 runner
isolation, #186 accounting/reservation, #64 cutover and all worker activation
checks remain separate. No merge, tag, release, deploy or live switch follows
from completing this design.

### P1 validation note — internal pattern receipt convention

Root confirmed the internal pattern convention before implementation on
2026-10-23: `tool_version="1"` identifies `portable-patterns-v1`;
`exit_code=0` denotes internal completion, even with findings, and is not a
subprocess observation or policy pass. Its `native_digest` is SHA-256 of the
full canonical JSON object `{adapter_id,input_digest,scanned_count,findings}`.
Canonical encoding is UTF-8, `ensure_ascii=false`, sorted object keys,
separators comma/colon and no NaN/Infinity. The full finding list is ordered by
path (null as empty string), line (null as0), rule_id, severity, then canonical
finding JSON bytes as the tie-breaker. Failure/overflow never uses a complete
state to simulate internal success. This adds no scanner or wire field.

P1 implements only the approved structural wire-model subset of REQ-01/SE-01:
immutable envelope/receipt/key/finding/package/gap records, strict bounded JSON,
safe boundary errors and real producer-codec -> independent consumer-codec
synthetic roundtrip. The common raw corpus includes two OSV lock scopes and
contiguous Bandit batches, rejects mixed required/N/A units and batch gaps,
and does not constrain a family to one required receipt. These checks do not
verify expected SHA/profile/plan/process truth, run scanners or apply the
HIGH/CRITICAL publication policy. Remaining SE-01 and full #189 stay required.

First-wave deterministic validation: Orchestra 96 focused/122 total unit tests
and Nexus 38 focused/263 Orchestra unit tests pass; the Nexus selection includes
both integration-marked synthetic cross-repository codec tests with an explicit
candidate source root. Scoped native Ruff formatting/lint, strict mypy and
Ruff security rules pass. No native scanner, package installation, service or
gate wiring was performed. Parent independent review and all later phases
remain outstanding; no commit or activation follows from this note.
