// "Da fare tu": human-task steps ticked from the drawer (POST /api/actions kind check) and the final
// «Fatto» (kind done). Client state = item.steps[].checked overlaid with the check actions Orchestra has
// not applied yet; a pending done keeps the item «Fatto · in attesa di verifica». Pure, plus `local`.
import { safeHref } from "./cb-util.js";
import { isAnswered } from "./cb-bits.js";

export const isActionAsk = (a) => a?.kind === "action";
const asks = (it) => (Array.isArray(it?.ask) ? it.ask : []);
// Same-second actions of one item are <received>-<item>.json, then -2.json, -3.json…
const nth = (r) => {
  const rest = String(r.file || "")
    .slice(`${r.received}-${r.item}`.length)
    .replace(/\.json$/, "");
  return /^-\d+$/.test(rest) ? Number(rest.slice(1)) : 1;
};
const order = (a, b) =>
  String(a.received).localeCompare(String(b.received)) || nth(a) - nth(b);

// "2026-10-14T11:41:00Z" -> "20261014T114100Z", the received format of the actions.
const stamp = (iso) =>
  String(iso || "")
    .replace(/[-:]/g, "")
    .replace(/\.\d+/, "")
    .slice(0, 16);

// item -> Map(step -> checked) from pending check rows, oldest first so the newest wins. A check
// already applied (done) but newer than the data (`generated`) still counts: the data lags behind.
export function pendingChecks(rows, generated = "") {
  const since = generated ? stamp(generated) : "";
  const out = new Map();
  const live = (rows || []).filter(
    (r) =>
      r.kind === "check" &&
      r.item &&
      r.step &&
      (!r.done || (since && String(r.received) > since)),
  );
  for (const r of live.sort(order)) {
    if (!out.has(r.item)) out.set(r.item, new Map());
    out.get(r.item).set(r.step, r.checked === true);
  }
  return out;
}

// item -> newest done row that Orchestra has not verified yet.
export function pendingDone(rows) {
  const out = new Map();
  for (const r of (rows || [])
    .filter((x) => x.kind === "done" && !x.done && x.item)
    .sort(order))
    out.set(r.item, r);
  return out;
}

export function stepsOf(it, checks = local.checks) {
  const over = checks.get(it?.id);
  return (Array.isArray(it?.steps) ? it.steps : []).map((s) => ({
    ...s,
    checked: over?.has(s.id) ? over.get(s.id) : s.checked === true,
  }));
}

export const stepCount = (steps) => ({
  done: steps.filter((s) => s.checked).length,
  total: steps.length,
});

// Listed under «Da fare tu»: a Your call with an open action ask, or a Fatto waiting for Orchestra.
export const isTodo = (it, done = local.done) =>
  done.has(it.id) ||
  (Boolean(it.your_call) &&
    asks(it).some((a) => isActionAsk(a) && !a.answered));

// The drawer shows the checklist / Fatto block: steps to follow or an open action ask (also once the
// server has taken the item out of Your call, e.g. after a Fatto).
export const hasTask = (it) =>
  (Array.isArray(it.steps) && it.steps.length > 0) ||
  asks(it).some((a) => isActionAsk(a) && !a.answered);

// A step link: relative page or http(s) URL only; label = page name or host + path.
export function stepLink(link) {
  const href = link ? safeHref(link) : null;
  if (!href) return null;
  const label = /^https?:/i.test(href)
    ? href.replace(/^https?:\/\//i, "")
    : href.replace(/\.html(#.*)?$/, "");
  return { href, label };
}

// Items that left Your call because of a dashboard action (server: acted_ids in bin/wi_fields.py):
// a dispatch/comment not handled yet, or a Fatto not verified yet. Edits and checks do not count.
export function actedItems(rows) {
  const out = new Set();
  for (const r of rows || [])
    if (r.item && !r.done && ["dispatch", "comment", "done"].includes(r.kind))
      out.add(r.item);
  return out;
}

// Board-wide state from GET /api/actions (server) plus the rows sent from this page (own): an own row
// is optimistic until its POST answers, then it waits for a refresh that lists its file.
export const local = {
  checks: new Map(),
  done: new Map(),
  acted: new Set(),
  server: [],
  own: [],
  generated: "",
};

export function syncRows(rows, generated = local.generated) {
  local.server = rows || [];
  local.generated = generated;
  const files = new Set(local.server.map((r) => r.file));
  local.own = local.own.filter((o) => !o.file || !files.has(o.file));
  const all = [...local.server, ...local.own];
  local.checks = pendingChecks(all, generated);
  local.done = pendingDone(all);
  local.acted = actedItems(all);
  return all;
}
export const setTaskRows = syncRows;

const nowStamp = () =>
  new Date().toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z";
export function addOwn(fields) {
  const row = { file: "", received: nowStamp(), done: false, ...fields };
  local.own.push(row);
  syncRows(local.server);
  return row;
}
export function dropOwn(row) {
  local.own = local.own.filter((r) => r !== row);
  syncRows(local.server);
}

// A server Your call the page already acted on: acted here, or every decision answered from here and
// no action left open. It leaves the strip and the toolbar count at once.
export function clearedCall(it) {
  if (!it?.your_call) return false;
  // Recurring health cards keep their identity; only per-finding answers close their asks.
  if (!it.health && local.acted.has(it.id)) return true;
  const open = asks(it).filter((a) =>
    isActionAsk(a) ? !a.answered : !isAnswered(it, a),
  );
  return asks(it).length > 0 && open.length === 0;
}

// The one Your call definition (toolbar count, filter, strip chips): the server's your_call (open asks,
// not acted on: bin/workitems.py asks()) minus what this page already acted on or answered.
export const isOpenCall = (it) => Boolean(it?.your_call) && !it.hidden && !clearedCall(it);
