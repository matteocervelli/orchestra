# Security envelope checkpoint A — issue 189

Status: approved checkpoint A implementation; parent GO received 2026-10-23.
Only the literal A manifest and waves1..6 are authorized; B/C/D need their gates.
Date: 2026-10-23. This is checkpoint A of the approved A→D synthetic security
gate, not completion of issue189, an activation approval, or a second codec task.

## Authority and fixed decisions

The full normative security contract is Orchestra's
[approved envelope spec](https://github.com/matteocervelli/orchestra/blob/f73b9bca5a3e0d76984cfd5d32692f6756b53fdf/docs/specs/2026-10-23-security-envelope-issue-189.md),
SHA256 2843d3c83a5122f80ae28c7a0f804103682011802fd4880ad0b558dfd8730378.
The subsequent root-accepted A→D implementation handoff is identified by SHA256
9c25bc15471293f2661819190acb84629ef371cd69c010e3921e7174b14d9acd.
This formal phase document carries its A contracts into the repository; the
original spec's complete adapter commands/versions/grammars and later acceptance
remain normative. No runtime dependency on an operational artifact directory
or mutable shared skill is introduced.

Matteo approved the versioned required profile and HIGH/CRITICAL blocking for
Orchestra, including JavaScript. Missing/error/timeout/truncation/overflow of a
required scanner blocks; unknown severity/attribution blocks. All Gitleaks
secrets, all pip-audit vulnerabilities and Bandit MEDIUM+ preserve their stronger
rules. No general JS policy elsewhere changes. P1 structural parsing remains
separate: complete envelope does not mean policy pass.

Root approved responsibility splits, the exact A manifest, direct runtime
declaration of already-locked packaging26.3/PyYAML6.0.3 in both repos, and the
documentation amendments in this manifest. No unrelated dependency upgrade,
scanner installation, source/test/lock edit or live setting follows merely from
writing this spec. No subagent, reviewer CLI, commit, push, PR, merge, tag,
release or deployment is authorized by this preparation. Independent review
and integration are central-owned.

## Frozen pair and compatibility

| Repository | Immutable base | Provenance |
| --- | --- | --- |
| Orchestra | f73b9bca5a3e0d76984cfd5d32692f6756b53fdf | Integrated P1, exact reviewed head22e2310 Forgejo PR CI17/17 and merge tree equality d2edaf62dc909638312c0cd349d6107e13e82590. Workflow is PR-only; no merge-push CI job is claimed. |
| Nexus | 91d0aa9a60edae1425a9dff6d3257dc25a10cc9a | Integrated P1 head7de0ee7; central exact-head PR CI10/10 and integration evidence; relevant security/runtime/dependency sources unchanged from reviewed P1. |

The paired branch is auto/stateless-security-189-checkpoint-a-20261023 in each
repo, in its own dedicated worktree. No source modification in the old
central-owned P1 worktrees. Readiness is run with this exact spec path, not
ambiguous issue-number discovery. Repo AGENTS and current codebase maps apply.
Protect Nexus's already-integrated inert memory reader and token-normalization
modules/tests; their additions are not security runtime wiring and must not be
overwritten. Historical P1 suite counts are not the new baseline.

## Outcome and checkpoint boundary

A implements the trusted foundation needed for the REAL next gate:
profile/runtime/artifact identity, private request records, independent immutable
inventory/applicability/plan in Nexus, bounded raw protocol supervision and
bootstrap verification in Orchestra. A has no scanner adapter invocation,
producer success entrypoint, policy decision, service wiring or durable evidence
claim. No fake-success placeholder or new passed field substitutes for B→D.

The unchanged mandatory progression is:

1. A: foundations and negative-path tests under the exact manifest below.
2. B: every approved native adapter, trusted installed-style artifact and real
   producer CLI using generated fake native executables.
3. C: real producer→independent Nexus retained-plan/process consumer and policy;
   all-required Python+JS and required-Trivy variants, multiple dependency roots,
   contiguous Bandit batches and no-findings positive. All-N/A is insufficient.
4. D: explicit inert mode, one Gitleaks invocation/two projections, fenced safe
   evidence PATCH+GET/readback, prepublish invalidation and exact-pair Forgejo CI.

A is only partial REQ-01..05 evidence. REQ-06..08 and the full end-to-end
acceptance stay required in B→D. Full189 SDLC/search/clarification, same-SHA
reviewer/publication recovery acceptance and #170/#186/#64 activation conditions
remain separate. No extra scheduler, scan engine, durable store, Atrium API or
database is introduced.

## Requirements and verification mapping

These aliases map existing SE acceptance only, without new product requirements.

| Alias | Existing acceptance | A proof / remaining proof |
| --- | --- | --- |
| REQ-01 | SE-01 identity/schema/receipt completeness | Strict trusted request/profile records, deterministic full keys; P1 envelope unchanged. Real expected-envelope validation C. |
| REQ-02 | SE-02 bounded complete capture | Raw stdin/stdout/stderr/file/probe limits, byte digests/counters, timeout/cancel cleanup A; full producer overflow/21st-finding chain B/C. |
| REQ-03 | SE-03 native integrity/fail-closed | Process/preflight/bootstrap failure cannot look successful A; each actual adapter error/schema/version B/C. |
| REQ-04 | SE-04 immutable workspace/applicability coverage | Bounded inventory, real-target uv/pnpm/npm metadata grammar and expected plan A; native tuple/report coverage B/C. |
| REQ-05 | SE-05 SHA/profile/artifact binding | Independent retained request/digests and detectable artifact/runtime drift A; launch-to-policy/prepublish replay proof C/D. |
| REQ-06 | SE-06 approved severity/attribution | Policy invariant preserved in A profile, full decision/attribution tests C. |
| REQ-07 | SE-07 one Gitleaks/safe persistence | A specifies safety/size preflight only; real one-scan projections and Atrium fenced readback D. |
| REQ-08 | SE-08 exact-pair CI/review | A deterministic gates and parent review receipt; required full exact-pair executable gate D. |

## Immutable types, authority and error handling

Orchestra uses frozen stdlib records; Nexus independently uses strict immutable
Pydantic-v2 records with extra=forbid. No runtime import of Orchestra by Nexus.
Use packaging26.3 for requirement equality and PyYAML6.0.3 pure SafeLoader with
the restricted wrapper, not a dependency resolver or a new YAML parser. Do not
rely on transitive/dev-only installs. Authorized A implementation now promotes
those existing exact pins directly, changing root dependency metadata only.
This does not install native scanners or activate a deployment.

All serialized objects reject duplicate JSON keys, floats/NaN/Infinity, invalid
UTF8, BOM, trailing documents and unknown fields. Canonical JSON is UTF8,
ensure_ascii=false, sorted keys, comma/colon separators and no floats; SHA256
is lowercase hex64. Depth counts containers from root=1 and must be <=16.
Existing P1 UUID/git40/digest/relative-path/strict integer constraints apply.
Booleans are not integers. Null is explicit, not an omitted required field.

All fields below are required unless explicitly nullable. Collections are
immutable, unique where specified and deterministically sorted. Host paths,
argv, raw bytes and environment are private local/request-only data with safe
repr; never diagnostics/model_dump/log payloads or persisted/public fields.
Safe typed boundary errors carry only existing P1 code, optional receipt key
and safe relative path. Raw exception/native text is never public detail.
PlanError prevents launch/pass for an unsafe/oversized request; a failure need
not manufacture an envelope or claim successful process observation.

## Profile, runtime and execution context

load_trusted_profile(profile_file, expected_digest, assets_root) -> TrustedProfile
reads only explicitly trusted deployed/test assets outside candidate control.
JSON cap65536/depth16 and P1 safe identifiers/path rules apply. Exact top-level:

    schema: orchestra.security-profile/v1
    profile_id
    adapters
    limits
    exclusions
    dependency_free_scopes
    source_bindings
    policy
    assets

Adapters is the sorted closed catalog of all nine P1 adapter IDs, including
both JS alternatives: each item carries adapter_id, family, version,
native_schema, recipe_id and asset_paths. recipe_id equals adapter_id and maps
only to fixed approved spec §6 code; no arbitrary argv. Native schemas without
upstream numeric version use the pinned adapter's source-shape tag, not an
invented native version. Every version/family pair is the P1 catalog's pair.

Limits are the approved maxima: request2097152; envelope/native stdout/native
stderr/report file/export65536 each; probe streams4096 each; files10000;
manifest/locks256; roots64; receipts/findings/gaps128 each; blob4194304;
aggregate67108864; probe10s/export60s/native300s/scan3600s; YAML depth32 and
nodes100000. All JSON fields are strict integers. Smaller reviewed limits may
fail earlier; larger limits reject. No larger capture to conceal omissions.

Exclusions are explicit sorted component prefixes, not gitignore or tests/
hidden-directory heuristics. The initial catalog includes .git/.worktrees and
the approved dependency/cache/build prefixes only; tracked source/manifest
changes under exclusions are coverage gaps. Dependency_free_scopes is sorted
{path,inventory_digest}, empty initially; root path sentinel is null, not dot.
Source_bindings encodes only the approved uv1-r3/pnpm9/npm3-v1 grammar, exact
trusted credential-free registry/index URLs, Orchestra Python-range pair and
three Nexus dashboard override bindings in original §6. No host marker pruning,
directURL/Git/external path or new resolution behavior is inferred.

Policy is fixed orchestra-high-block-v1. Reject a profile weakening all-secret,
all-pip or Bandit-MEDIUM+ rules. Assets is sorted {path,sha256,size}, byte hashes
for configs/rules, excluding profile itself. Profile_digest is canonical full
profile hash; configs/rules also belong to producer artifact manifest. A's
checked-in catalog is not an activatable complete artifact: native assets are
added in B. Missing referenced asset blocks configuration_drift, never fake hash
or successful empty rule set. A tests use actual generated trusted temp assets.

RuntimeBindings retained by Nexus:

    python: {absolute_path,provisioning_digest}
    producer: {absolute_root,revision,manifest_digest}
    tools: [{adapter_id,absolute_path,sha256,provisioning_digest}]
    git: {absolute_path,sha256,provisioning_digest}
    scratch_root
    runner_capability_revision
    capability_digest
    registry_capability_digest: hex64|null

Tools sort by adapter ID; same executable aliases only when retained concrete
path/digests match. Provisioning digest covers full interpreter/stdlib/tool
runtime tree (including Node CLI modules or Python tool packages), not just a
launcher hash. Actual deployment values are not fabricated. Runtime_digest
hashes identity fields with host paths/scratch root excluded; retained concrete
bindings still must match at admission, spawn and later freshness checks.

ScanContext exact fields:

    schema: orchestra.security-context/v1
    runtime_digest
    ci_declaration: {digest,workflow_revisions,requires_trivy,trivy_scanners}
    trivy_db: {digest,updated_at_epoch,verified_at_epoch}|null

Workflow revisions are sorted {repository,path,revision} pinned git40 entries.
CI declaration digest covers its canonical declaration excluding its own digest.
It is reviewed authority, not candidate grep; changed governed workflow content
invalidates it. Trivy scanner set is the trusted required set. DB epochs are
strict nonnegative integers, nonfuture and <=86400s old at launch/consumption/
prepublish when required; absent/stale DB blocks. Context_digest hashes this
whole context. No credential value is serialized; scoped auth capability is a
separate future live prerequisite.

## Inventory, metadata grammar and expected-plan composition

Nexus build_scan_request(repo,attempt,head,base,profile,runtime,context,git)
returns PreparedScan {request_bytes,expected}, retaining ExpectedScan before any
producer report. It is bounded synchronous composition; service wiring is D.
Repo key/roots/attempt come from trusted allowlists/live attempt, not task text.
Fresh scan UUID per launch; retry cannot reuse another attempt's authority.

Use trusted argv-only git with system/global/config hooks, external diff,
textconv and rename behavior disabled. Require clean worktree including
untracked files; capture full head/base/merge-base40 once. Read ls-tree -r -z
and diff --no-ext-diff --no-textconv --no-renames --name-only -z merge-base head
as binary NUL records. Rename means delete+add; deleted paths remain in changed
set. No whitespace/colon/newline splitting or mutable refs afterward. Reject
shallow/incomplete Gitleaks range, gitlinks/submodules, relevant symlinks,
untracked nested repo, unsafe names/modes/globs and all approved size/count
overflows. Do not follow another .git/external dependency. Blob content comes
from pinned tree; verify mutable content before/after, materialize privately
with exclusive/no-follow operations. Synthetic snapshots are not OS isolation.

Records and canonical digests:

- FileInput={path,mode,blob_id,sha256,size}; mode100644|100755; sorted UTF8 path.
- ChangedInput={path}; unique UTF8-path order including deletions.
  Changed_digest hashes this exact array.
- WorkspaceInput={lock_path,kind,members,manifests,governing_inputs,packages};
  kind uv1-r3|pnpm9|npm3; path lists unique/sorted. Packages are unique indexed
  {ecosystem,name,version} tuples, sorted by their three UTF8 strings, preserving
  transitive/dev/optional/platform/extra branches. In-tree members are source.
- PlannedUnit={key,adapter_id,applicability,applicability_reason,input_paths,
  input_digest,expected_packages,depends_on}; exact P1 key/adapter/N/A rules.
  depends_on is sorted receipt keys, only pip audit depends on its uv export.
  Sort units in fixed family order gitleaks,patterns,bandit,python-export,
  python-audit,javascript-audit,osv,trivy; null scope before UTF8 path; batch int.
- Input_digest hashes {key,adapter_id,profile_digest,context_digest,inputs,
  expected_packages,depends_on}; inputs are full FileInput records, not names.
  Gitleaks also binds base/head/merge-base. Patterns/Bandit bind all target
  sources. N/A binds relevant full inventory, never tool availability.
  Pip binds original locks/manifests and its export recipe/input identity;
  actual pylock hash/tuple completeness is validated by trusted B adapter, not
  fabricated as a pre-execution expected hash or Nexus-native observation.
- Scope_digest hashes {repository,head_sha,base_sha,merge_base_sha,profile_digest,
  files,changed,workspaces,units}. No nested scope_digest/self-reference.
- Plan_digest hashes {schema:orchestra.security-plan/v1,scope_digest,
  changed_digest,context_digest,units,gaps}. Gaps are unique canonical-JSON
  sorted, <=128 and always prevent a later pass.

ExpectedScan retains all identities, profile/runtime/context digests, captured
SHAs and all above records, never rebuilt from a report. Bandit batches greedily
pack sorted target paths under24KiB UTF8 target argv bytes including separators,
contiguous0.. and max128. Full key is unique, not one receipt per family.
All other/N/A units batch0.

Applicability: gitleaks/patterns always; Bandit all .py files; export+pip+OSV per
uv root; native JS+OSV per JS root; Trivy iff reviewed CI declaration requires.
Independent nested roots are separate units; parent-lock members/importers are
covered once. Missing/stale/competing locks, unsupported stacks, malformed
metadata, escaping links, suppression/config drift and excluded changed source
block even on docs-only changes. N/A only for proven no applicable scope or
trusted Trivy declaration. Absence of a binary never implies N/A.

Implement ONLY original §6 metadata grammar: uv1/rev3, pnpm9 and npm3. uv uses
packaging Requirement/Marker/SpecifierSet equality with exact approved range
normalization, extras/dev/markers/constraints/index metadata including Nexus's
real Forgejo mapping; no evaluating host markers or custom resolver. Optional
dependency tables/dynamic/group includes/unapproved sources/knobs block.
JS compares literal manifest maps to importers/workspace records; the three
Nexus router/router-plugin/vite override bindings are exact profile-owned
exceptions, not a semver solver. Verify all members/override tables. Restricted
PyYAML pure SafeLoader rejects anchor/alias/explicit tag/merge/duplicate/nonstring
key/multidoc/depth>32/nodes>100000 before construction. No LibYAML fallback.
Keep whole real-target shapes in synthetic fixture builders; do not use a toy
grammar excluding Nexus then call it ready for both.

## Request/artifact/bootstrap interface

Request schema orchestra.security-request/v1 contains all P1 envelope identity/
digest fields (scan/work-unit/attempt/repo/producer/profile/context/head/base/
merge-base/scope/changed/plan) plus private repo_root,scratch_root,runtime,context,
files,changed,workspaces,units,gaps; no complete/receipts. Exact cap2097152,
depth16, same strict JSON. Producer resolves installed profile catalog, not
request profile contents; validates supplied records/digests against its own
pinned-tree inventory/grammar before B runs native commands. If representation
cannot fit, block scope_overflow; max10000 files does not guarantee fitting2MiB.

Artifact manifest is the original exact canonical
{format:orchestra.producer-artifact/v1,revision,files:[{path,sha256,size}]},
path-sorted, excluding only manifest itself. Include bootstrap, package init,
every security module/config/profile/rule, complete pure-Python packaging26.3/
PyYAML6.0.3 trees/licenses and source provenance. Reject missing/extra files,
symlink, bytecode, .pth, extension module or mismatched bytes. Stdlib/interpreter
are separately provisioned identity. No editable install or repo symlink.

Launch contract remains trusted-python -I -S -B artifact/bootstrap.py
--request-stdin. Bootstrap derives own root, verifies manifest BEFORE package
imports, replaces sys.path with artifact plus trusted stdlib paths and verifies
all nonstdlib loaded origins are exact listed Orchestra/packaging/yaml files.
Check configs too, not merely imports. No candidate cwd/PYTHONPATH/user-site/
site startup or native yaml import. A may validate request/artifact/load origins,
but missing B producer entrypoint must fail closed exit2; never success stub or
empty complete report. Test bootstrap in a real subprocess with actual fixture
artifact/modules/assets/manifest, not monkeypatched integrity checks.

Runtime admission rejects any symlink in path/ancestors, relative/dot-parent
aliases, candidate/scratch containment and candidate/group/world-writable
binding or ancestors. Open no-follow, record device/inode/size/owner/mode, hash
that descriptor and compare path stat and retained binding immediately before
spawn and afterward. Reject unapproved shebang interpreters/env/shell wrappers,
unbound Node/Python trees. This detects drift but does NOT close pathname
hash→exec TOCTOU: live use requires verified immutable runtime/artifact mounts
unwritable by candidate AND scanner, no concurrent deployment, protected
snapshot and restricted execution/egress, bound capability revision/digest.
Absent capability blocks live admission. Synthetic tests test negative admission
and detectable replacement; they do not certify host isolation. No fd-exec
interpreter contract is silently invented.

## Separate bounded raw process protocol

Nexus procs.run_protocol(launch,*,on_started=None,on_heartbeat=None)
returns ProtocolObservation and preserves existing run_capture/run_logged
diagnostic privacy/API. Orchestra process module implements analogous
NativeRunner without importing Nexus. Reuse process-group start identity,
kill/reap/deadline logic; no daemon or general new worker policy.

ProtocolLaunch local fields: executable,argv,cwd,environment,stdin,
stdin_limit,stdout_limit,stderr_limit,deadline_seconds. All executable/path/env
values already validated by security runtime admission. No shell. Deadline is
finite positive local monotonic duration, at most3600s; integer profile seconds
are not JSON floats. ProtocolObservation local fields:

    exit_code,timed_out,cancelled,io_error,wall_ms,process_identity
    stdout_bytes,stderr_bytes,stdout_total,stderr_total
    stdout_truncated,stderr_truncated,stdout_digest,stderr_digest
    stdin_complete,reaped

Raw byte fields/launch contents have repr=False and safe custom repr. No raw
model dump, diagnostics, logs, exception interpolation or persisted payload.
Hash full observed bytes BEFORE decoding/redaction. Digest of a nonfully
drained/overflowed stream is partial local data, never complete native_digest.
Counts mean bytes actually read, not unseen child output. No valid-prefix pass.

Independent caps: stdin2MiB; outer stdout65536 including whitespace; outer
stderr65536; each native stdout/stderr65536; each report/export file65536;
version stdout/stderr4096 each. Validate stdin size before spawn. Concurrent
bounded writer closes stdin on completion; broken pipe/partial write is io_error
even if stdout looks valid. Concurrent readers retain at most each cap while
hashing/counting observed bytes; first excess marks overflow and terminates the
group. Files must be exclusive regular/no-follow under private unit scratch,
bounded read+size checks; never output-file bypass. Request depth/size and
envelope size are distinct limits, not one tunable capture setting.

Timeout covers spawn/stdin/process/drain: probe10s/export60s/native300s/scan3600s;
native deadline=min(unit limit,remaining scan budget). On cancel, timeout,
overflow, I/O/hook/lease failure AND normal exit, close stdin, terminate group,
SIGKILL after bounded existing grace, reap leader and join I/O workers.
Reader/writer still alive, unreaped leader or inherited pipe held open means
noncomplete io_error. Parent exiting cannot leave grandchildren behind.
Cancellation propagates only after cleanup; no passing observation on cancelled
or unobserved crash. Existing diagnostic redaction/replacement decoding stays
unchanged; raw protocol never uses it or adds a global redact=false switch.

Security-only environment is built from constants plus scan scratch:
LANG/LC_ALL=C.UTF-8,TZ=UTC, trusted HOME/USER, fixed trusted PATH,
TMPDIR/XDG_CACHE_HOME/XDG_CONFIG_HOME/XDG_DATA_HOME inside private scratch.
Do not repurpose process HOME or widen execution.py's nine-key worker allowlist.
No inherited NODE_OPTIONS/npm/pnpm/UV_/PYTHON_/GITLEAKS_/TRIVY_ overrides or
service/mail/cloud secrets. Future scoped registry auth is per-unit capability,
not request/log data; no anonymous fallback. These controls are NOT OS isolation.

## A TDD roadmap and validation gates

No code or test is written during spec preparation. After explicit parent GO:

1. Profile/private types/runtime admission → RED duplicate/malformed JSON,
   weakened policy, wrong digest/version, alias/symlink/writable/transitive
   runtime mismatch; GREEN strict loaders and retained identity only.
2. Inventory/metadata → RED real temporary Git tree and synthetic real-target
   uv/Nexus extras+markers+constraints/index and pnpm override cases; missing/
   stale/mixed/unsupported/unsafe/suppression/overflow cases; GREEN bounded
   parsers/inventory, no network, resolver, native scanner or candidate hook.
3. Plan/request → RED two independent roots/twoOSV, Bandit batches0/1 vs0/2,
   no family-only uniqueness, deterministic canonicalization, changed deletion/
   rename, replay/CI/profile/SHA/content drift and request cap; GREEN independent
   ExpectedScan retained before any report, not new envelope fields.
4. Raw protocol → RED real generated local subprocess exact-cap/cap+1 per stream,
   stdin completion/broken pipe, split writes/invalid UTF8, >64KiB HIGH suffix,
   slow/hung I/O, forked inherited pipe, timeout/cancel/hook failure and safe repr;
   GREEN bounded bytes/digests/counts/group cleanup, existing diagnostic tests
   and worker environment behavior unchanged. Native/file caps covered through
   synthetic regular output files, not actual scanners.
5. Artifact/bootstrap → RED actual temp manifest/module origins/config tamper,
   candidate PYTHONPATH, extra/missing/symlink/.pth/bytecode/native yaml and
   missing B entrypoint; GREEN real isolated bootstrap verification, never
   fake producer success. Keep partial A catalog explicitly unactivatable.
6. A-only safe-evidence preflight specifies canonical legal near64KiB envelope,
   <=98304-byte evidence and cap+1 rejection using synthetic data in listed
   profile/plan tests; it is NOT an implemented C decision or D persistence test.

Run narrow RED first and observe failure; no mocks that bypass integrity or
weaken tests. Then focused GREEN, existing Orchestra unit and Nexus orchestra/
procs/diagnostic/launch regressions under verified frozen Python3.12 environment,
Ruff format/lint/strict changed-source typing and deterministic configured
security validation as explicitly allowed by parent. Do not infer scanner/
install authorization from test plans. Select local imports explicitly when
reusing a verified environment; unset inherited UV_PROJECT_ENVIRONMENT and
VIRTUAL_ENV before any future uv operation outside its original repo.

Capture exact commands/results/hashes, changed-file/manifest check and dependency
metadata proof with zero unrelated bump. Review stages: spec compliance then
edge cases/privacy/cleanup; parent owns independent reviewer and exact-head
Forgejo gate. Stop for parent receipt before commit/ship or entering B. A does
not add CI wiring or force crossrepo neighbor paths into ordinary unit tests.

## Deferred but mandatory B→D evidence and activation boundaries

Native report validation and per-family scanned_count semantics are the full
approved contract, not guessed from scalar native totals. B/C must reject one
failed required scanner beside valid JSON, omitted/skipped/private package,
unknown native/tool version, malformed partial report, gap/receipt mismatch,
21st relevant finding and any overflow. Required Trivy fixture exists even when
the two initial trusted CI declarations allow N/A. No package namespace exclusion.

D adds SecurityEvidence <=98304 canonical bytes via existing Atrium result JSON.
Source inspection proved identical work-item schema/model/route/service/body
middleware between pinned harness8f07b67cbb0bf5fd6703c32dcf06acff41b85866 and
integrationfa0c023d544b28a7f71c62f565cce3f747769f4c: dict→JSONB has no result cap
or automatic redaction, and ingest body cap does not cover work_items. Nexus
queue's returned check verifies fence ONLY, not evidence equality. D must add
existing queue.get plus exact canonical expected-evidence/identity/live-fence
comparison, PATCH→GET→restart→GET with real PostgreSQL harness, tampered-readback
and structured canary-secret negatives. No raw snippets/messages/credentials
or host paths may be persisted; preserve safe counts/severity/relative paths
and exact advisory IDs. Do not claim downstream redaction exists or clip a
complete report. No Atrium implementation or new endpoint/table.

Live activation still needs separately verified immutable runtime/toolchain/
artifact provisioning, protected scratch/snapshot, OS execution/egress isolation,
trusted CI declaration/DB freshness/proxy request limit and scoped registry auth.
Nexus's12 private indexed Python tuples and @adlimen/ui-react public-native-audit
coverage remain unproven: submit all, unknown coverage blocks. First bounded
live pilot remains Orchestra, only after separately authorized controlled
installed-scanner proof. Synthetic A→D never certifies installed scanners or OS
isolation. Unsupported cases remain explicit blockers, never silently green.

## Orchestra checkpoint-A responsibilities

Profile holds installed logical catalog/limits/asset validation; request holds
strict private request/plan/runtime records without changing P1 envelope code.
Artifact owns complete manifest/origin verification, bootstrap only isolated
startup/request admission. Inventory reads pinned Git and composes reproducible
snapshot/applicability checks; lock_metadata owns uv grammar, js_metadata owns
pnpm/npm grammar and yaml_loader restricted construction. Process owns bounded
NativeRunner. Dependency direction: bootstrap→artifact/profile/request/inventory;
inventory→metadata/profile/request; process→validated local records. No package
initializer side effects or dependency on Nexus/runtime services.

Tests mirror these responsibilities under test_profile, test_artifact,
test_inventory, test_lock_metadata and test_process. Real process fixtures use
trusted temp executables/artifacts; no scanner, package-manager hook or external
API. Existing P1 codec source/test corpus remains unchanged. Update INDEX only
when modules exist in the later code wave; conventions accurately distinguish
current zero runtime declarations from approved future exact parser promotion.
The existing full spec may receive amendment notes only, not rewritten policy.

## Checkpoint A implementation evidence

A foundations are implemented locally, pending parent review; B→D and full189
remain required. No scanner adapters, producer success entrypoint, policy
decision, gate/service wiring, persistent evidence or live configuration were
added. The checked-in catalog intentionally rejects without B's native assets.

The paired test sets ORCHESTRA_SECURITY_REQUEST_ROOT explicitly and runs the
real independent producer request verifier, including tampered records. Its
installed-style subprocess uses real pure parser trees/licenses/provenance,
manifest checks and isolated bootstrap; a valid request reaches fixed
security_producer_not_available exit2. That is fail-closed A evidence, not a
complete producer or passed gate. NativeRunner/procs tests cover both4096-byte
probe and65536-byte native streams at cap/cap+1, stdin overflow before spawn,
concurrent input/broken pipe, byte hashes, raw canary privacy and process-group
cleanup. File/export bounds are independent of stream bounds.

Runtime observation detects digest/inode/path drift but grants no live runner
capability. Ordinary executable admission defaults live and requires external
verified authority; synthetic callers explicitly opt out. Approved absolute
interpreter bindings are retained/rechecked; env/shell/unbound wrappers reject.
Governed CI workflow content is checked against retained revisions; no candidate
text chooses Trivy applicability. ExpectedScan has no passed field.

Synthetic uv graph vectors include missing direct/dev/extra/transitive records,
root-edge deletion, wrong resolved version and an extra known-name local source.
JS importers and recorded transitive edges must exist in inventory. Actual-target
metadata-only parsing succeeds (Orchestra25 Python tuples; Nexus113 Python and450
dashboard npm tuples), without executing scanners or resolving dependencies.
This is not whole-target inventory acceptance: Nexus tracks references/paperclip
as a gitlink and is correctly blocked. Do not remove or exempt it implicitly.
Private native-audit coverage, live isolation/runtime provisioning and actual
scoped auth remain separate blockers. Marker-disjoint duplicate-name uv branches
outside the accepted bounded grammar may reject conservatively; no resolver or
host marker pruning is introduced.

The local A checks are full native Ruff format/lint, repository type checking,
scoped deterministic Ruff safety checks and unit regressions. Parent owns the
independent reviewer and exact-pair Forgejo acceptance; no commit/PR or CI pass
is claimed for this local snapshot. General documentation audit warnings outside
the literal manifest were reported, not repaired by broadening A.

## Supplemental checkpoint-A corrections

Parent released the central review freeze for five mandatory Sol findings;
this correction does not authorize B or live activation.

Git's trusted byte helper sets GIT_NO_REPLACE_OBJECTS=1 and GIT_ALLOW_PROTOCOL
to the empty string for every command. Before object/status work it inspects
local configuration NAMES only, with includes disabled, and rejects includes,
candidate filters, promisor/partial configuration, promisor pack markers,
alternates, grafts, replacement refs and shallow state. No credential value is
read or emitted. The complete head/base reachable object closure is checked by
rev-list --objects --no-object-names --missing=error under the same transport
denial and bounded capture. This is conservatively stronger than only checking
merge-base..head and can reject oversized historical closures. There is no
fetch, Git upgrade, quarantine engine or reliance on an ignored lazy-fetch flag.
The commands and local transport-helper canary are verified on Git2.43.0;
see pinned [environment contract](https://github.com/git/git/blob/v2.43.0/Documentation/git.txt),
[missing-object traversal](https://github.com/git/git/blob/v2.43.0/Documentation/rev-list-options.txt)
and [promisor implementation](https://github.com/git/git/blob/v2.43.0/promisor-remote.c).

Live admit_executable now requires the exact retained RuntimeBindings and
capability, not merely well-formed capability strings. The injected authority
must expose provisioning_digest(path), proving the COMPLETE interpreter/stdlib/
tool/module tree, or the complete verified producer manifest/tree, never a
launcher-only digest. All retained paths/digests and producer manifest revision
are checked; supplied shebang interpreters must match concrete retained bindings,
independent of any supplied FileIdentity admission. A different immutable but
unbound interpreter blocks. The same retained authority/freshness check runs
before spawn and after cleanup. Unknown writable/immutable results or provider
exceptions become fixed configuration_drift. No authority provider is added:
the positive tests explicitly isolate ancestor inspection as a unit seam and
do not claim /tmp immutability, OS isolation or deployed provisioning. A Node
interpreter absent from the concrete retained bindings remains inadmissible;
B synthetic Python fixtures do not prove live Node provisioning.

Pattern/exclusion relevance shares exact .env basename plus supported suffix
classification. The bounded unsupported catalog detects Maven/Gradle variants,
requirements*.txt, pylock.toml/pylock.*.toml and all previously named unsupported
families before dependency N/A. Cleanup returns explicit reap status; missing
reap or incomplete selector drain sets io_error independently of timeout and
overflow. Existing diagnostic redaction and worker environment rules are
unchanged. Installed artifacts must include the admission module and reject
its absence/tampering. Independent rereview and new exact hashes remain required.


## File Manifest

Parent amendment 2026-10-23: add runtime.py solely to split executable identity/
capability admission from raw process supervision before exceeding 500 lines.
process.py retains compatible explicit re-exports; no second implementation,
provider, schema, tool or dependency is added. Its installed artifact entry is
mandatory and covered by missing/tampered module negatives.

- `src/orchestra/security/profile.py`
- `src/orchestra/security/request.py`
- `src/orchestra/security/artifact.py`
- `src/orchestra/security/bootstrap.py`
- `src/orchestra/security/inventory.py`
- `src/orchestra/security/lock_metadata.py`
- `src/orchestra/security/js_metadata.py`
- `src/orchestra/security/yaml_loader.py`
- `src/orchestra/security/process.py`
- `src/orchestra/security/runtime.py`
- `src/orchestra/security/profiles/pilot-v1.json`
- `tests/unit/security/test_profile.py`
- `tests/unit/security/test_artifact.py`
- `tests/unit/security/test_inventory.py`
- `tests/unit/security/test_lock_metadata.py`
- `tests/unit/security/test_process.py`
- `pyproject.toml`
- `uv.lock`
- `docs/codebase/INDEX.md`
- `docs/specs/2026-10-23-security-envelope-issue-189.md`
- `docs/codebase/conventions.md`
- `docs/specs/2026-10-23-security-envelope-checkpoint-a-issue-189.md`
