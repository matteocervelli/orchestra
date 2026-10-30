import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { cpSync, copyFileSync, readFileSync, writeFileSync, mkdirSync, mkdtempSync } from "node:fs";
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const legacy = resolve(root, "src/orchestra/dashboard/legacy");
const fixture = resolve(root, "tests/fixtures/dashboard_legacy");
const manifest = JSON.parse(readFileSync(resolve(legacy, "manifest.json"), "utf8"));
const callchipsManifest = JSON.parse(readFileSync(resolve(legacy, "callchips-manifest.json"), "utf8"));
const releaseManifest = JSON.parse(readFileSync(resolve(legacy, "release-visibility-manifest.json"), "utf8"));
const digest = bytes => createHash("sha256").update(bytes).digest("hex");
// Preserve this donor's existing blank EOF losslessly, without a source-code whitespace exception.
const toolbarDonor = Buffer.from(JSON.parse(readFileSync(resolve(fixture, "assets/cb-toolbar.js.json"), "utf8")));
const donorBytes = name => name === "cb-toolbar.js" ? toolbarDonor : readFileSync(resolve(fixture, "assets", name));
for (const [name, hash] of Object.entries(manifest.baseline_assets))
  assert.equal(digest(donorBytes(name)), hash, `baseline ${name}`);
for (const file of manifest.files)
  assert.equal(digest(donorBytes(file.path.slice("assets/".length))), file.before_sha256, `donor ${file.path}`);
for (const [name, hash] of Object.entries(callchipsManifest.baseline_assets))
  assert.equal(digest(donorBytes(name)), hash, `call chips donor ${name}`);
for (const file of callchipsManifest.files)
  assert.equal(digest(donorBytes(file.path.slice("assets/".length))), file.before_sha256, `call chips target ${file.path}`);
assert.equal(digest(readFileSync(resolve(legacy, callchipsManifest.patch))), callchipsManifest.patch_sha256);
assert.equal(digest(readFileSync(resolve(fixture, "repositoryFilter.ts"))), manifest.helper.source_sha256);
assert.equal(digest(readFileSync(resolve(legacy, "repository-filter.js"))), manifest.helper.generated_sha256);
assert.equal(digest(readFileSync(resolve(legacy, "repository-aliases.patch"))), manifest.patch_sha256);
assert.equal(digest(readFileSync(resolve(legacy, releaseManifest.patch))), releaseManifest.patch_sha256);
for (const [name, hash] of Object.entries(releaseManifest.prerequisite_runtime_patches))
  assert.equal(digest(readFileSync(resolve(legacy, name))), hash, `release prerequisite ${name}`);
const cache = resolve(root, ".pytest_cache");
mkdirSync(cache, { recursive: true });
const work = mkdtempSync(resolve(cache, "legacy-js-"));
const baseline = resolve(work, "baseline");
const assets = resolve(work, "assets");
cpSync(resolve(fixture, "assets"), baseline, { recursive: true });
writeFileSync(resolve(baseline, "cb-toolbar.js"), toolbarDonor);
cpSync(baseline, assets, { recursive: true });
writeFileSync(resolve(work, "package.json"), '{"type":"module"}\n');
if (process.env.LEGACY_BASELINE !== "1") {
  execFileSync("patch", ["--batch", "--fuzz=0", "-p1", "-i", resolve(legacy, "repository-aliases.patch")], { cwd: work });
  copyFileSync(resolve(legacy, "repository-filter.js"), resolve(assets, "repository-filter.js"));
  for (const file of manifest.files)
    assert.equal(digest(readFileSync(resolve(work, file.path))), file.after_sha256, `candidate ${file.path}`);
  if (process.env.LEGACY_CALLCHIPS_BASELINE !== "1") {
    execFileSync("patch", ["--batch", "--fuzz=0", "-p1", "-i", resolve(legacy, callchipsManifest.patch)], { cwd: work });
    for (const file of callchipsManifest.files)
      assert.equal(digest(readFileSync(resolve(work, file.path))), file.after_sha256, `call chips candidate ${file.path}`);
  }
  for (const file of releaseManifest.files)
    assert.equal(digest(readFileSync(resolve(work, file.path))), file.before_sha256, `release donor ${file.path}`);
  if (process.env.LEGACY_RELEASE_VISIBILITY_BASELINE !== "1") {
    execFileSync("patch", ["--batch", "--fuzz=0", "-p1", "-i", resolve(legacy, releaseManifest.patch)], { cwd: work });
    for (const file of releaseManifest.files)
      assert.equal(digest(readFileSync(resolve(work, file.path))), file.after_sha256, `release candidate ${file.path}`);
  }
}
const filters = await import(pathToFileURL(resolve(assets, "cb-state.js")));
const dedupe = await import(pathToFileURL(resolve(assets, "cb-dedupe.js")));
const toolbar = await import(pathToFileURL(resolve(assets, "cb-toolbar.js")));
const callchips = await import(pathToFileURL(resolve(assets, "v3/callchips.js")));
const { state, readUrl, writeUrl, matches, facetCounts, sortItems, takenCounts, resetFilters, setTakenTest } = filters;
const item = (id, repo, extra = {}) => ({
  id, repo, title: "Attività indipendente", status: "Integration", ask: [],
  steps: [{ id: "verify", checked: false }], your_call: false,
  flags: { protected: true }, aliases: [`old-${id}`], ...extra,
});
const selected = items => items.filter(it => matches(it)).map(it => it.id);
const open = search => { globalThis.location = { search, pathname: "/board.html", hash: "#card" }; readUrl(); };
beforeEach(() => { resetFilters(); state.sort = []; setTakenTest(it => Boolean(it.taken)); });

test("JavaScript deltas and whole generated helper pass default Git whitespace rules", () => {
  // Compare donor to candidate: inherited donor whitespace is preserved, not certified clean.
  const pairs = [...manifest.files, ...callchipsManifest.files].map(file => [resolve(baseline, file.path.slice("assets/".length)), resolve(work, file.path)]);
  pairs.push(["/dev/null", resolve(legacy, "repository-filter.js")]);
  for (const [before, after] of pairs) {
    const result = spawnSync("git", ["-c", "core.whitespace=blank-at-eol,blank-at-eof,space-before-tab", "diff", "--no-index", "--check", "--", before, after], { cwd: root, encoding: "utf8" });
    // --no-index returns 1 for an ordinary difference; whitespace failures add 2.
    assert.ok(result.status === 0 || result.status === 1, result.stdout + result.stderr);
    assert.equal(result.stdout, "");
    assert.equal(result.stderr, "");
  }
});

test("old URL CSV aliases canonicalize and deduplicate, preserving drawer and presentation", () => {
  open("?repo=himalaia,app-himalaia,matteocervelli/app-himalaia.,ratio&view=table&open=exact-id&answer=1&fields=repo&sort=repo:asc&group=repo&taken=no");
  assert.deepEqual(state.repo, ["app-himalaia", "app-ratio"]);
  assert.equal(state.item, "exact-id");
  assert.equal(state.answer, true);
  assert.equal(state.view, "table");
  assert.equal(state.tab, "tabella");
  assert.equal(state.group, "repo");
  assert.equal(state.taken, "no");
  assert.deepEqual([...state.fields], ["repo"]);
  assert.deepEqual(state.sort, [{ f: "repo", d: "asc" }]);
});

test("new URLs canonicalize even direct legacy selections without changing source state", () => {
  open("?item=exact-id&answer=1&status=Integration&tab=tabella");
  state.repo = ["ratio", "app-ratio", "foreign/app-ratio."];
  const before = structuredClone(state.repo);
  let written;
  globalThis.history = { state: { old: true }, replaceState: (_, __, url) => { written = url; } };
  writeUrl();
  const url = new URL(written, "https://example.invalid");
  assert.equal(url.searchParams.get("repo"), "app-ratio,foreign/app-ratio.");
  assert.equal(url.searchParams.get("item"), "exact-id");
  assert.equal(url.searchParams.get("answer"), "1");
  assert.equal(url.searchParams.get("status"), "Integration");
  assert.equal(url.hash, "#card");
  assert.deepEqual(state.repo, before);
});

test("registered aliases, owner-qualified canonicals and exactly one dot match", () => {
  const pairs = [
    ["himalaia", "app-himalaia"], ["ratio", "app-ratio"],
    ["adlimenui", "adlimen-ui"], ["dotfiles", "claude-dotfiles"],
    ...["app-himalaia", "app-ratio", "adlimen-ui", "claude-dotfiles", "nexus", "atrium", "orchestra", "adlimen-cicd", "adlimen-infra", "adlimen-harness", "adlimen-auth", "limen-assistant"]
      .flatMap(repo => [[repo, repo], [`matteocervelli/${repo}`, repo]]),
  ];
  for (const [alias, canonical] of pairs) for (const key of [alias, `${alias}.`]) {
    state.repo = [canonical];
    assert.equal(matches(item("same", key)), true, key);
    state.repo = [key];
    assert.equal(matches(item("same", canonical)), true, `selection ${key}`);
  }
});

test("unknown, foreign, case, whitespace and repeated dots remain literal, never all", () => {
  for (const repo of ["unknown.", "foreign/app-himalaia.", "app-himalaia..", "himalaia..", "Nexus.", "Ratio.", " nexus", "matteocervelli/himalaia"]) {
    state.repo = [repo];
    assert.equal(matches(item("own", repo)), true, repo);
    assert.equal(matches(item("other", "app-himalaia")), false, repo);
    assert.equal(matches(item("none", null)), false, repo);
  }
  state.repo = [];
  assert.equal(matches(item("none", null)), true);
  state.repo = ["nexus"];
  assert.equal(matches(item("none", null)), false);
});

test("multirepository membership remains authoritative and each canonical counts once per card", () => {
  const items = [
    item("a", "ignored", { repos: ["himalaia", "app-himalaia", "matteocervelli/app-himalaia.", "ratio"] }),
    item("b", "app-himalaia"), item("c", "unknown."), item("n", null),
    item("done", "himalaia", { status: "Deployed" }), item("hidden", "ratio", { hidden: true }),
  ];
  const counts = facetCounts(items, "repo");
  assert.equal(counts.get("app-himalaia"), 2);
  assert.equal(counts.get("app-ratio"), 1);
  assert.equal(counts.get("unknown."), 1);
  assert.equal(counts.get(null), 1);
  assert.equal(counts.has("himalaia"), false);
  state.repo = ["app-ratio"];
  assert.deepEqual(selected(items), ["a"]);
  state.repo = ["ignored"];
  assert.equal(matches(items[0]), false);
  assert.equal(facetCounts(items, "status").get("Deployed"), undefined);
});

test("facet counts apply other filters and retain historical status counting", () => {
  const items = [item("a", "himalaia"), item("b", "app-himalaia", { status: "Main" }), item("d", "himalaia", { status: "Dropped" })];
  state.status = ["Integration"];
  assert.equal(facetCounts(items, "repo").get("app-himalaia"), 1);
  state.status = [];
  state.repo = ["app-himalaia"];
  assert.equal(facetCounts(items, "status").get("Dropped"), 1);
});

test("complete normalized repository queries gain alias compatibility; text semantics stay intact", () => {
  const card = item("a", "himalaia", { problem: "Verificare caffè e qualità" });
  for (const q of ["app-himalaia", "matteocervelli/app-himalaia.", "APP-HIMALAIA"]) {
    state.q = q;
    assert.equal(matches(card), true, q);
  }
  state.q = "caffe qualita";
  assert.equal(matches(card), true);
  state.q = "app-himalaia absent";
  assert.equal(matches(card), false);
  state.q = "absent";
  assert.equal(matches(card), false);
  state.q = "app-ratio";
  assert.equal(matches(item("m", "nexus", { repos: ["nexus", "ratio"] })), true);
});

test("repository sort compares canonical keys and preserves stable IDs/order on equivalent keys", () => {
  state.sort = [{ f: "repo", d: "asc" }];
  const items = [item("z", "app-himalaia"), item("a", "matteocervelli/app-himalaia"), item("b", "ratio"), item("n", null)];
  assert.deepEqual(sortItems(items, []).map(it => it.id), ["a", "z", "b", "n"]);
  assert.deepEqual(items.map(it => it.id), ["z", "a", "b", "n"]);
});

test("repo action scope comparisons normalize aliases, preserving rows and item scopes", () => {
  const a = item("a", "himalaia"), b = item("b", "app-himalaia");
  const rows = [{ item: "a", kind: "dispatch", text: "", scope: "repo:matteocervelli/app-himalaia.", received: "20261027T000000Z", done: false }];
  const before = structuredClone(rows);
  const blocks = dedupe.activeBlocks(rows, new Map([[a.id, a], [b.id, b]]));
  assert.equal(dedupe.scopeOf("promote", a.id, a), "repo:app-himalaia");
  assert.equal(dedupe.scopeOf("release", a.id, a), "repo:app-himalaia");
  assert.equal(dedupe.scopeOf("merge", a.id, a), "item:a");
  assert.strictEqual(dedupe.blockFor(b, blocks), rows[0]);
  assert.deepEqual(rows, before);
  assert.equal(dedupe.blockFor(item("f", "foreign/app-himalaia"), blocks), null);
});

test("taken counts use the real shared action blocker without broadening unrelated actions", () => {
  const items = [item("a", "himalaia"), item("b", "app-himalaia"), item("c", "ratio")];
  const rows = [{ item: "a", kind: "dispatch", text: "", done: false }];
  const blocks = dedupe.activeBlocks(rows, new Map(items.map(it => [it.id, it])));
  setTakenTest(it => Boolean(it.taken) || Boolean(dedupe.blockFor(it, blocks)));
  assert.deepEqual(takenCounts(items), { all: 3, yes: 2, no: 1 });
  state.taken = "no";
  assert.deepEqual(selected(items), ["c"]);
});

test("comparison/filtering does not rewrite cached cards, nested evidence or existing text cache", () => {
  const card = item("exact-id", "himalaia", { repos: ["himalaia", "ratio"], _hay: "existing cached prose", your_call: true, ask: [{ id: "q1", kind: "decide", text: "Confermare?" }], status: "Doing", hidden: false });
  const before = structuredClone(card);
  const asks = card.ask, steps = card.steps, flags = card.flags, repos = card.repos;
  Object.freeze(card.repos); Object.freeze(card.ask[0]); Object.freeze(card.ask);
  Object.freeze(card.steps[0]); Object.freeze(card.steps); Object.freeze(card.flags); Object.freeze(card);
  state.q = "app-himalaia";
  assert.equal(matches(card), true);
  facetCounts([card], "repo"); sortItems([card], []);
  assert.deepEqual(card, before);
  assert.equal(filters.isCall(card), true);
  assert.strictEqual(card.ask, asks);
  assert.strictEqual(card.steps, steps);
  assert.strictEqual(card.flags, flags);
  assert.strictEqual(card.repos, repos);
});

test("real toolbar renders one canonical option per repository including secondary memberships", () => {
  // Only the DOM boundary is synthetic; real toolbar, counts and predicates run unchanged.
  class Element {
    constructor(tag) { this.tag = tag; this.attributes = {}; this.children = []; this.style = { setProperty() {} }; }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
  }
  globalThis.Node = Element;
  globalThis.document = { createElement: tag => new Element(tag), createElementNS: (_, tag) => new Element(tag) };
  const panel = new Element("div");
  const items = [item("a", "himalaia", { repos: ["himalaia", "app-himalaia", "ratio"] }), item("b", "matteocervelli/app-himalaia.")];
  const before = structuredClone(items);
  toolbar.renderFilterStrip(panel, items, ["Integration"], { filtersOpen: true, openMenu: "repo", msQuery: {} });
  const all = node => node instanceof Element ? [node, ...node.children.flatMap(all)] : [];
  const inputs = all(panel).filter(node => node.tag === "input" && node.attributes["data-facet"] === "repo");
  assert.deepEqual(inputs.map(node => node.attributes["data-value"]), ["app-himalaia", "app-ratio"]);
  const labels = all(panel).filter(node => node.tag === "label" && node.attributes["data-ms-label"]);
  const himalaia = labels.find(node => node.attributes["data-ms-label"] === "app-himalaia");
  const count = all(himalaia).find(node => node.className === "cb-facet");
  assert.deepEqual(count.children, ["2"]);
  assert.equal(count.attributes.title, "2");
  assert.deepEqual(items, before);
});

const callItem = (id, repo, extra = {}) => item(id, repo, {
  your_call: true, ask: [{ id: `question-${id}`, kind: "decide", text: "Confermare?" }], ...extra,
});
const mixedCalls = () => [
  ...Array.from({ length: 9 }, (_, i) => callItem(`canonical-${i}`, "app-himalaia")),
  callItem("short-1", "himalaia"), callItem("short-2", "himalaia"),
  callItem("dot-1", "app-himalaia."),
];

test("call chips: 9 canonical, 2 short and 1 dot produce one chip counting all 12 cards", () => {
  const items = mixedCalls();
  const before = structuredClone(items);
  const counts = callchips.callCounts(items, state);
  assert.deepEqual([...counts.repos], [["app-himalaia", 12]]);
  assert.equal(counts.total, 12);
  assert.equal(counts.shown, 12);
  assert.equal(counts.kinds.get("decide"), 12);
  const html = callchips.callChips(items, state);
  assert.equal((html.match(/data-call-chip=/g) || []).length, 1);
  assert.match(html, /data-call-chip="app-himalaia"[^>]*title="12"[^>]*>[^]*?<span class="v3-call__count">12<\/span>/);
  assert.deepEqual(items, before);
});

test("call chips: canonical click selection count matches all raw aliases and preserves drawer URL", () => {
  const items = mixedCalls();
  state.item = "short-1"; state.answer = true;
  callchips.chipClick(state, { repo: "himalaia." });
  assert.deepEqual(state.repo, ["app-himalaia"]);
  assert.equal(state.yourcall, true);
  assert.equal(selected(items).length, 12);
  assert.equal(callchips.callCounts(items, state).shown, 12);
  globalThis.location = { pathname: "/board.html", hash: "#questions" };
  let written;
  globalThis.history = { state: {}, replaceState: (_, __, url) => { written = url; } };
  writeUrl();
  const url = new URL(written, "https://example.invalid");
  assert.equal(url.searchParams.get("repo"), "app-himalaia");
  assert.equal(url.searchParams.get("item"), "short-1");
  assert.equal(url.searchParams.get("answer"), "1");
  assert.equal(url.hash, "#questions");
});

test("call chips: old raw selections and raw picks toggle the same logical key once", () => {
  state.repo = ["himalaia", "app-himalaia.", "app-ratio"];
  callchips.chipClick(state, { repo: "matteocervelli/app-himalaia." });
  assert.deepEqual(state.repo, ["app-ratio"]);
  assert.equal(state.yourcall, true);
  callchips.chipClick(state, { repo: "ratio" });
  assert.deepEqual(state.repo, []);
  assert.equal(state.yourcall, false);
  callchips.chipClick(state, { kind: "approve UI" });
  assert.deepEqual(state.call, ["approve UI"]);
  assert.equal(state.yourcall, true);
  callchips.chipClick(state, null);
  assert.deepEqual(state.call, []);
  assert.deepEqual(state.repo, []);
  assert.equal(callchips.allPressed(state), true);
});

test("call chips: raw selected aliases render one pressed canonical chip with truthful total", () => {
  state.repo = ["himalaia", "app-himalaia."]; state.yourcall = true;
  const before = structuredClone(state.repo);
  const html = callchips.callChips(mixedCalls(), state);
  assert.equal((html.match(/data-call-chip=/g) || []).length, 1);
  assert.match(html, /data-call-chip="app-himalaia"[^>]*title="12" aria-pressed="true"/);
  assert.deepEqual(state.repo, before);
});

test("call chips: memberships match filters and deduplicate equivalent keys per card", () => {
  const items = [callItem("multi", "nexus", { repos: ["ratio", "app-ratio", "matteocervelli/app-ratio.", "nexus"] }), callItem("secondary", "ratio")];
  const before = structuredClone(items);
  assert.deepEqual([...callchips.callCounts(items, state).repos], [["app-ratio", 2], ["nexus", 1]]);
  callchips.chipClick(state, { repo: "app-ratio" });
  assert.deepEqual(selected(items), ["multi", "secondary"]);
  assert.equal(callchips.callCounts(items, state).shown, 2);
  assert.match(callchips.callChips(items, state), /data-call-chip="app-ratio"[^>]*title="2"/);
  assert.deepEqual(items, before);
});

test("call chips: unknown foreign and repeated-dot repositories remain separate literal selections", () => {
  const names = ["foreign/app-himalaia.", "unknown.", "app-himalaia..", "matteocervelli/himalaia"];
  const items = names.map((repo, i) => callItem(`literal-${i}`, repo));
  assert.deepEqual([...callchips.callCounts(items, state).repos.keys()], names);
  callchips.chipClick(state, { repo: names[0] });
  assert.deepEqual(state.repo, [names[0]]);
  assert.deepEqual(selected(items), ["literal-0"]);
  assert.equal(callchips.callCounts(items, state).shown, 1);
});

test("call chips: open-call/status gates, asks, primary repos and active action rows remain intact", () => {
  const items = mixedCalls();
  items.push(callItem("done", "himalaia", { status: "Deployed" }));
  items.push(callItem("hidden", "himalaia", { hidden: true }));
  items.push(callItem("answered", "himalaia", { ask: [{ id: "answered-q", kind: "decide", answered: true }] }));
  const rows = [{ item: "short-1", kind: "dispatch", scope: "repo:himalaia", text: "", done: false }];
  const raw = structuredClone({ items, rows });
  const byId = new Map(items.map(it => [it.id, it]));
  const blocks = dedupe.activeBlocks(rows, byId);
  callchips.callCounts(items, state); callchips.callChips(items, state);
  assert.deepEqual({ items, rows }, raw);
  assert.equal(callchips.callCounts(items, state).repos.get("app-himalaia"), 12);
  assert.strictEqual(dedupe.blockFor(items[0], blocks), rows[0]);
  assert.equal(rows[0].scope, "repo:himalaia");
});

// Exact public identity/classification fields from the frozen same-generation rows.
// Neither row publishes ask/steps; these fixtures do not manufacture those fields.
const previouslyHiddenWork = [
  { id: "hima19-beta-final-deploy-sol61-20261025", repo: "app-himalaia", kind: "feature", status: "Backlog", title: "Preparare tag finale e distribuzione beta Himalaia .19 senza staging separato", slugs: ["hima19-beta-final-deploy-sol61-20261025"] },
  { id: "pr-adlimen-cicd-40", repo: "adlimen-cicd", kind: "fix", status: "PR fix", title: "Ritirare i vecchi workflow riutilizzabili deploy-ops", slugs: ["cicd-40-fix", "cicd-deploy-ops-sweep", "review-cicd-40-r2", "review-cicd-40"], pr: { number: 40, url: "https://github.com/matteocervelli/adlimen-cicd/pull/40" } },
];

test("release visibility: exact two ordinary work cards remain visible without name inference", () => {
  const before = JSON.stringify(previouslyHiddenWork);
  for (const card of previouslyHiddenWork) {
    assert.equal(filters.releaseItem(card), false, card.id);
    assert.equal(matches(card), true, card.id);
    assert.equal(Object.hasOwn(card, "ask"), false);
    assert.equal(Object.hasOwn(card, "steps"), false);
  }
  assert.deepEqual(selected(previouslyHiddenWork), previouslyHiddenWork.map(card => card.id));
  assert.equal(JSON.stringify(previouslyHiddenWork), before);
});

test("release visibility: exact restored cards contribute to their real repo and status filters", () => {
  assert.equal(facetCounts(previouslyHiddenWork, "status").get("Backlog"), 1);
  assert.equal(facetCounts(previouslyHiddenWork, "status").get("PR fix"), 1);
  state.repo = ["adlimen-cicd"]; state.status = ["PR fix"];
  assert.deepEqual(selected(previouslyHiddenWork), ["pr-adlimen-cicd-40"]);
  state.repo = ["himalaia"]; state.status = ["Backlog"];
  assert.deepEqual(selected(previouslyHiddenWork), ["hima19-beta-final-deploy-sol61-20261025"]);
});

test("release visibility: ordinary work names and slugs never supply release classification", () => {
  const names = ["release-notes-editor", "tag-parser-fix", "promotion-policy-docs", "promotions-help", "deploy-ops-workflow-fix", "ordinary-tag-parser", "ordinary-deploy-ops-fix"];
  for (const name of names) for (const kind of ["feature", "fix"]) for (const releaseFlag of [undefined, false]) {
    for (const namedField of ["id", "slugs"]) {
      const card = item(namedField === "id" ? name : "ordinary", "nexus", { kind, release_operation: releaseFlag, slugs: namedField === "slugs" ? [name] : [] });
      assert.equal(filters.releaseItem(card), false, `${namedField} ${name} ${kind}`);
      assert.equal(matches(card), true, `${namedField} ${name} ${kind}`);
    }
  }
});

test("release visibility: explicit true flag remains authoritative and matching search reveals it", () => {
  const card = item("explicit-flag-operation", "nexus", { kind: "feature", release_operation: true });
  assert.equal(filters.releaseItem(card), true);
  for (const q of ["", " ", "\t"]) {
    state.q = q;
    assert.equal(filters.releaseVisible(card, q), false);
    assert.equal(matches(card), false);
  }
  state.q = "explicit-flag";
  assert.equal(filters.releaseVisible(card, state.q), true);
  assert.equal(matches(card), true);
  state.q = "absent-term";
  assert.equal(matches(card), false);
});

test("release visibility: each existing explicit kind retains hidden/default and search semantics", () => {
  for (const kind of ["release", "tag", "promotion", "deploy", "release_prepare"]) {
    const card = item(`explicit-kind-${kind}`, "nexus", { kind, release_operation: false });
    assert.equal(filters.releaseItem(card), true, kind);
    for (const q of ["", " ", "\t"]) {
      state.q = q;
      assert.equal(matches(card), false, kind);
    }
    state.q = "explicit-kind";
    assert.equal(matches(card), true, kind);
    state.q = "unrelated-term";
    assert.equal(matches(card), false, kind);
  }
});

test("release visibility: synthetic evidence bytes and references survive restored visibility", () => {
  const card = item("ordinary-deploy-ops-fix", "himalaia", {
    kind: "fix", release_operation: false, status: "PR fix", repos: ["himalaia", "ratio"],
    your_call: true, ask: [{ id: "synthetic-q", kind: "decide", text: "Domanda sintetica" }],
    pr: { number: 1, url: "https://github.com/example/fixture/pull/1" },
  });
  const before = JSON.stringify(card);
  const refs = { ask: card.ask, steps: card.steps, pr: card.pr, flags: card.flags, repos: card.repos };
  Object.freeze(card.ask[0]); Object.freeze(card.ask); Object.freeze(card.steps[0]);
  Object.freeze(card.steps); Object.freeze(card.pr); Object.freeze(card.flags);
  Object.freeze(card.repos); Object.freeze(card);
  assert.equal(matches(card), true);
  assert.equal(callchips.callCounts([card], state).repos.get("app-himalaia"), 1);
  facetCounts([card], "repo"); sortItems([card], []);
  assert.equal(JSON.stringify(card), before);
  for (const [key, value] of Object.entries(refs)) assert.strictEqual(card[key], value);
});
