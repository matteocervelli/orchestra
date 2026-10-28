// Your call strip as multi-select filter chips, always visible, no accordion: «Tutto», the KIND of
// call (Tipo) and the repos. Every pressed chip filters the board and the table (state.call = kinds,
// state.repo = repos, both in the URL): kind AND repo, OR inside a group. Every number comes from the
// board's own filter (cb-state.js matches + isOpenCall): a chip counts the cards its click shows, and
// «Tutto» shows the toolbar's number (callSummary), saying when other filters narrow it.
import { countable } from "../cb-counts.js";
import { callSummary, countSummary, matches, openCallKind, KIND_LABELS } from "../cb-state.js";
import { CALL_KINDS } from "../cb-bits.js";
import { repoName } from "./model.js";
import { esc, icon } from "./ui.js";

export { KIND_LABELS };
export const kindLabel = (k) => KIND_LABELS[k] || k;

export const callTotal = (items) => callSummary(items).total;

const selected = (st) => st.call.length + st.repo.length > 0;
// «Tutto» is pressed when nothing narrows the board: no kind, no repo, Your call off.
export const allPressed = (st) => !selected(st) && !st.yourcall;

// Kind / repo chip click toggles the value; Your call follows the selection so answered or
// dispatched items never show while a chip is on. «Tutto» (null) clears everything.
export function chipClick(st, pick = null) {
  if (pick === null) {
    st.call = [];
    st.repo = [];
  } else {
    const key = pick.kind !== undefined ? "call" : "repo";
    const v = pick.kind ?? pick.repo;
    st[key] = st[key].includes(v) ? st[key].filter((x) => x !== v) : [...st[key], v];
  }
  st.yourcall = selected(st);
  return st;
}

// Faceted counts on open calls, with every board filter applied except the chip's own group: a kind
// chip counts the open calls its click shows (same for repos). st: the view state (cb-state.js state).
export function callCounts(items, st) {
  const count = (except, key) => {
    const m = new Map();
    for (const it of items)
      if (countable(it) && openCallKind(it) && matches(it, except, st)) m.set(key(it), (m.get(key(it)) || 0) + 1);
    return m;
  };
  const sum = callSummary(items, st);
  return { ...sum, kinds: count("call", openCallKind), repos: count("repo", (it) => it.repo) };
}

const chip = (attr, key, pressed, label, count, extra = "", title = "") =>
  `<button type="button" class="v3-call__chip${extra}" ${attr} data-key="${esc(key)}" title="${esc(title)}" aria-pressed="${pressed}">${label}<span class="v3-call__count">${count}</span>${
    pressed ? icon("check", "v3-call__check") : ""
  }</button>`;

const group = (label, title, chips) =>
  chips.length
    ? `<div class="v3-call__group" role="group" aria-label="${label}"><span class="v3-call__title" aria-hidden="true">${title}</span>${chips.join("")}</div>`
    : "";

// st: { yourcall, repo, call } (cb-state.js state).
export function callChips(items, st) {
  const { total, text, filtered, label, kinds, repos } = callCounts(items, st);
  if (!total && !selected(st)) return "";
  const kindOrder = [...new Set([...CALL_KINDS, ...kinds.keys(), ...st.call])].filter(
    (k) => kinds.get(k) || st.call.includes(k),
  );
  const repoOrder = [...new Set([...repos.keys(), ...st.repo])]
    .filter((r) => repos.get(r) || st.repo.includes(r))
    .sort((a, b) => (repos.get(b) || 0) - (repos.get(a) || 0) || repoName(a).localeCompare(repoName(b), "it"));
  const all = chip(
    "data-call-all",
    "call:*",
    allPressed(st),
    `${icon("ask", "v3-call__icon")}<span class="v3-call__label">Tutto</span>`,
    text,
    " v3-call__chip--total",
  );
  const note = filtered ? `<span class="v3-call__note" role="status">${esc(label)}</span>` : "";
  const summaryFor = (facet, value, n) => countSummary(n, items.filter(it => countable(it) && openCallKind(it) && (facet === "call" ? openCallKind(it) : it.repo) === value).length, st, facet).label;
  const kindChips = kindOrder.map((k) =>
    chip(`data-call-kind="${esc(k)}"`, `callkind:${k}`, st.call.includes(k), esc(kindLabel(k)), kinds.get(k) || 0, "", summaryFor("call", k, kinds.get(k) || 0)),
  );
  const repoChips = repoOrder.map((r) =>
    chip(`data-call-chip="${esc(r)}"`, `call:${r}`, st.repo.includes(r), esc(repoName(r)), repos.get(r) || 0, "", summaryFor("repo", r, repos.get(r) || 0)),
  );
  return `<div class="v3-call">${all}${note}${group("Tipo di richiesta", "Tipo", kindChips)}${group("Repo", "Repo", repoChips)}</div>`;
}
