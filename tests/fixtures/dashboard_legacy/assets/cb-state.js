import { countable } from "./cb-counts.js";

// View state, URL persistence, filtering, faceted counts and sorting.
import { priorityOf, prioKey, PRIORITY_LABEL } from "./cb-priority.js";
import { isTodo, isOpenCall } from "./cb-tasks.js";
import { FIELDS, DEFAULT_FIELDS, parseFields, serializeFields } from "./v3/fields.js";

export const SORT_FIELDS = {
  priority: "Priorità",
  updated: "Aggiornato",
  repo: "Repo",
  status: "Stato",
  cost: "Costo",
  number: "Numero",
};
export const DEFAULT_SORT = [
  { f: "priority", d: "asc" },
  { f: "updated", d: "desc" },
];
// Direction a sort rule starts with when added from the menu: P0 first, the others newest/biggest first.
export const defaultDir = (f) => (f === "priority" ? "asc" : "desc");
export const FACETS = ["repo", "status", "call", "priority"];
export const TOGGLES = ["yourcall", "todo", "mockup", "display", "preview"];
// «Presa in carico» (three-way, ?taken=yes|no): "" all, "yes" taken, "no" still to take.
export const TAKEN = { yes: "Prese in carico", no: "Da prendere" };
export const KIND_LABELS = {
  decide: "Da decidere", "approve mockup": "Approva mockup", "approve UI": "Approva UI",
  "approve merge": "Approva merge", action: "Da fare tu",
};
export const FACET_LABEL = { repo: "Repo", status: "Stato", call: "Tipo", priority: "Priorità" };
export const TOGGLE_LABEL = {
  yourcall: "Solo Your call", todo: "Da fare tu", mockup: "Mockup", display: "Display", preview: "Preview live",
};
export const filterValueLabel = (facet, value) =>
  facet === "priority" ? PRIORITY_LABEL[value] || value : facet === "call" ? KIND_LABELS[value] || value : value;

// One inventory for the visible chips and explanations. Fields change presentation only.
export function activeFilters(s = state, except = null) {
  const filters = [];
  const add = (facet, label, value = "") => {
    if (facet !== except) filters.push({ facet, label, value });
  };
  if (s.q?.trim()) add("q", `Ricerca: ${s.q.trim()}`);
  for (const facet of FACETS)
    for (const value of s[facet] || []) add(facet, `${FACET_LABEL[facet]}: ${filterValueLabel(facet, value)}`, value);
  for (const key of TOGGLES) if (s[key]) add(key, TOGGLE_LABEL[key]);
  if (s.taken) add("taken", TAKEN[s.taken]);
  if (s.fields instanceof Set && serializeFields(s.fields)) {
    const names = FIELDS.filter(f => s.fields.has(f.key)).map(f => f.label);
    add("fields", `Campi: ${names.length ? names.join(", ") : "nessuno"}`);
  }
  return filters;
}

export function countSummary(shown, total, s = state, except = null) {
  const filtered = shown !== total;
  const names = activeFilters(s, except).filter(f => f.facet !== "fields").map(f => f.label);
  const text = filtered ? `${shown} su ${total}` : String(total);
  const note = names.length ? `${names.length === 1 ? "filtro" : "filtri"}: ${names.join("; ")}` : "";
  return { total, shown, filtered, text, label: filtered && note ? `${text} · ${note}` : text };
}
let takenTest = (it) => Boolean(it.taken);
// board.js widens it: handled action, a step pending or held for the repo (cb-dedupe.js).
export const setTakenTest = (fn) => {
  takenTest = fn;
};
export const isTakenItem = (it) => takenTest(it);
export const GROUPS = {
  none: "Nessuno",
  repo: "Repo",
  status: "Stato",
  call: "Your call",
  agent: "Agente",
  priority: "Priorità",
};
const TABS = ["board", "tabella", "health", "rilasci", "figli", "costi"];

export const state = {
  tab: "board",
  view: "board",
  q: "",
  repo: [],
  status: [],
  call: [],
  priority: [],
  yourcall: false,
  todo: false,
  taken: "",
  mockup: false,
  display: false,
  preview: false,
  sort: DEFAULT_SORT.map((r) => ({ ...r })),
  group: "none",
  item: null, // id of the item open in the drawer (?item=)
  answer: false, // its questions modal is open (?answer=1): a reload or a discarded tab reopens it
  fields: new Set(DEFAULT_FIELDS), // «Campi visibili» (v3/fields.js)
  fieldsFromUrl: false, // fields are restored only from the URL
};

const list = (v) =>
  v
    ? v
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
    : [];

export function readUrl() {
  const p = new URLSearchParams(location.search);
  state.view = p.get("view") === "table" ? "table" : "board";
  const tab = p.get("tab");
  state.tab = TABS.includes(tab)
    ? tab
    : state.view === "table"
      ? "tabella"
      : "board";
  if (state.tab === "board") state.view = "board";
  if (state.tab === "tabella") state.view = "table";
  state.q = p.get("q") || "";
  for (const f of FACETS) state[f] = list(p.get(f));
  for (const t of TOGGLES) state[t] = p.get(t) === "1";
  const taken = p.get("taken");
  state.taken = taken === "no" ? "no" : taken === "yes" || taken === "1" ? "yes" : "";
  state.item = p.get("item") || p.get("open") || null;
  state.answer = Boolean(state.item) && p.get("answer") === "1";
  const fields = parseFields(p.get("fields"));
  state.fieldsFromUrl = Boolean(fields);
  state.fields = fields || new Set(DEFAULT_FIELDS);
  const group = p.get("group");
  state.group = Object.hasOwn(GROUPS, group) ? group : "none";
  const sort = list(p.get("sort"))
    .map((r) => {
      const [f, d] = r.split(":");
      return { f, d: d === "asc" ? "asc" : "desc" };
    })
    .filter(
      (r, i, a) => SORT_FIELDS[r.f] && a.findIndex((x) => x.f === r.f) === i,
    )
    .slice(0, 3);
  state.sort = sort.length ? sort : DEFAULT_SORT.map((r) => ({ ...r }));
}

// mode: "replace" (default) or "push" (new history entry, used when the drawer opens).
export function writeUrl(mode = "replace") {
  const p = new URLSearchParams();
  if (state.tab !== "board") p.set("tab", state.tab);
  if (state.view !== "board") p.set("view", state.view);
  if (state.q.trim()) p.set("q", state.q.trim());
  for (const f of FACETS) if (state[f].length) p.set(f, state[f].join(","));
  for (const t of TOGGLES) if (state[t]) p.set(t, "1");
  if (state.taken) p.set("taken", state.taken);
  const sort = state.sort.map((r) => `${r.f}:${r.d}`).join(",");
  if (sort && sort !== DEFAULT_SORT.map((r) => `${r.f}:${r.d}`).join(","))
    p.set("sort", sort);
  if (state.group !== "none") p.set("group", state.group);
  const fields = serializeFields(state.fields);
  if (fields) p.set("fields", fields);
  if (state.item) p.set("item", state.item);
  if (state.item && state.answer) p.set("answer", "1");
  const qs = p.toString();
  const url = `${location.pathname}${qs ? `?${qs}` : ""}${location.hash}`;
  if (mode === "push") history.pushState({ cbItem: state.item }, "", url);
  else history.replaceState(history.state, "", url);
}

export const activeFilterCount = () => activeFilters().filter(f => f.facet !== "fields").length;

export function resetFilters() {
  state.q = "";
  for (const f of FACETS) state[f] = [];
  for (const t of TOGGLES) state[t] = false;
  state.taken = "";
  state.fields = new Set(DEFAULT_FIELDS);
}

export function removeFilter(facet, value = "") {
  if (FACETS.includes(facet)) state[facet] = state[facet].filter(v => v !== value);
  else if (facet === "fields") state.fields = new Set(DEFAULT_FIELDS);
  else if (facet === "q" || facet === "taken") state[facet] = "";
  else if (TOGGLES.includes(facet)) state[facet] = false;
}

const norm = (s) =>
  String(s ?? "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");

// Multi-select option search: case- and accent-insensitive substring.
export const matchOption = (label, q) => norm(label).includes(norm(q).trim());

function haystack(it) {
  if (!it._hay) {
    it._hay = norm(
      [
        it.id,
        it.repo,
        ...(it.repos || []),
        it.kind,
        it.title,
        it.raw_title,
        it.status,
        it.dropped,
        it.blocked,
        it.agent,
        callKind(it),
        it.problem,
        it.solution,
        it.needs,
        it.evidence,
        it.branch,
        it.issue ? `#${it.issue.number}` : "",
        it.pr ? `#${it.pr.number} pr${it.pr.number} ${it.pr.title || ""}` : "",
        (it.labels || []).join(" "),
        (it.slugs || []).join(" "),
      ].join(" "),
    );
  }
  return it._hay;
}

const asks = (it) => (Array.isArray(it.ask) ? it.ask : []);
export const isCall = (it) => Boolean(it.your_call ?? it.serve_te) || asks(it).length > 0;
// Your call kind of an item: the backend's call_kind, else the first ask's kind.
export const callKind = (it) =>
  isCall(it) ? it.call_kind || asks(it)[0]?.kind || "decide" : "";
// Kind used to filter, count and group Your call (Filtri › Your call, chips Tipo, Raggruppa): only an
// open call (isOpenCall) has one, so an item whose asks were answered or acted on counts nowhere.
export const openCallKind = (it) => (isOpenCall(it) ? callKind(it) : "");
export const hasPages = (it) =>
  Object.values(it.pages || {}).some((a) => Array.isArray(a) && a.length > 0);
export const PREDICATES = {
  yourcall: isOpenCall,
  todo: (it) => isTodo(it),
  mockup: (it) =>
    Boolean(it.gates?.mockup) || (it.pages?.mockup || []).length > 0 || (it.pages?.pre || []).length > 0,
  display: (it) => (it.pages?.display || []).length > 0,
  preview: (it) => Boolean(it.gates?.preview_live),
};
export const facetValue = (it, f) =>
  f === "call" ? openCallKind(it) : f === "priority" ? priorityOf(it) : it[f];

// Operational release cards live in Rilasci; an explicit search still finds their drawers.
export const releaseItem = it => it.release_operation === true ||
  ['release','tag','promotion','deploy','release_prepare'].includes(it.kind) ||
  [it.id,...(it.slugs || [])].some(id=>/^(?:release|promotion|promotions|deploy|tag)(?:-|$)|(?:^|-)(?:tag|deploy)(?:-|$)/.test(id || ''));
export const releaseVisible = (it,q='') => !releaseItem(it) || Boolean(q.trim());

// s: the view state (default the page's); tests and counts pass the state a click would produce.
export function matches(it, except = null, s = state) {
  if (it.hidden || !releaseVisible(it,s.q)) return false;
  const terms = norm(s.q).split(/\s+/).filter(Boolean);
  if (terms.length && !terms.every((t) => haystack(it).includes(t)))
    return false;
  for (const f of FACETS)
    if (f !== except && s[f].length && !(f === "repo"
      ? (it.repos?.length ? it.repos : [it.repo]).some(r => s[f].includes(r))
      : s[f].includes(facetValue(it, f))))
      return false;
  for (const t of TOGGLES)
    if (except !== t && s[t] && !PREDICATES[t](it)) return false;
  if (except !== "taken" && s.taken && (s.taken === "yes") !== isTakenItem(it)) return false;
  return true;
}

// The one Your call number (toolbar button and strip «Tutto»). total: open calls on the whole board;
// shown: those that pass every other filter (search, Filtri, Presa in carico, chips Tipo/Repo), i.e.
// the cards «Your call» shows. A narrowed number names its filters: "4 su 13 · filtro: Da prendere".
export function callSummary(items, s = state) {
  const open = items.filter(it => countable(it) && isOpenCall(it));
  const shown = open.filter((it) => matches(it, "yourcall", s)).length;
  const summary = countSummary(shown, open.length, s, "yourcall");
  return { ...summary, label: summary.filtered ? summary.label : `${open.length} in tutto` };
}

// «Tutte / Da prendere / Prese in carico» counts, every other filter applied.
export function takenCounts(items) {
  const pool = items.filter((it) => countable(it) && matches(it, "taken"));
  const yes = pool.filter(isTakenItem).length;
  return { all: pool.length, yes, no: pool.length - yes };
}

// Count per value of `facet` with every OTHER filter applied (himalaia faceted counts).
export function facetCounts(items, facet) {
  const counts = new Map();
  for (const it of items)
    if ((facet === "status" || countable(it)) && matches(it, facet)) {
      const values = facet === "repo" && it.repos?.length ? [...new Set(it.repos)] : [facetValue(it, facet)];
      for (const v of values) counts.set(v, (counts.get(v) || 0) + 1);
    }
  return counts;
}

export const toggleCount = (items, key, pred) =>
  items.filter((it) => countable(it) && matches(it, key) && pred(it)).length;

function sortValue(it, f, statuses) {
  switch (f) {
    case "priority":
      return prioKey(it);
    case "updated":
      return it.updated || null;
    case "repo":
      return it.repo || null;
    case "status": {
      const i = statuses.indexOf(it.status);
      return i < 0 ? null : i;
    }
    case "cost":
      return typeof it.cost === "number" ? it.cost : null;
    case "number":
      return it.issue?.number ?? it.pr?.number ?? null;
    default:
      return null;
  }
}

export function sortItems(items, statuses) {
  const rules = state.sort.length ? state.sort : DEFAULT_SORT;
  return [...items].sort((a, b) => {
    for (const { f, d } of rules) {
      const va = sortValue(a, f, statuses);
      const vb = sortValue(b, f, statuses);
      if (va === vb) continue;
      if (va === null) return 1; // missing values always last
      if (vb === null) return -1;
      const c =
        typeof va === "string"
          ? va.localeCompare(vb, "it", { numeric: true })
          : va - vb;
      if (c) return d === "asc" ? c : -c;
    }
    return String(a.id).localeCompare(String(b.id));
  });
}
