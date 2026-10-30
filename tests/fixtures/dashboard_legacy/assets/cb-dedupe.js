// No duplicate steps (same rules as bin/action_dedupe.py): a dispatch whose text is a step preset (or
// empty: the step of the item's status) is a step; promotion and release count per repo, the others per
// item. An action blocks a new one of the same step while it is active: the server's `active` flag
// (no .done, or its child not finished yet), or not done for the rows this page sent and not listed yet.
import { repoName } from "./v3/model.js";

export const INTENT_TEXT = {
  inizia: "start",
  "rivedi la pr": "review",
  "correggi i rilievi": "fix",
  unisci: "merge",
  "prepara la promozione verso main": "promote",
  "prepara il rilascio": "release",
};
export const STATUS_INTENT = {
  Backlog: "start",
  "PR review": "review",
  "PR fix": "fix",
  Merge: "merge",
  Integration: "promote",
  Main: "release",
};
const REPO_INTENTS = ["promote", "release"];
const REPO_WORD = { promote: "promozione", release: "rilascio" };

const norm = (s) =>
  String(s ?? "")
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");

// row: an /api/actions row (or a payload); item: its work item, when known.
export function intentOf(row, item) {
  if (row.intent !== undefined && row.intent !== "") return row.intent;
  if (row.kind !== "dispatch") return "";
  const t = norm(row.text);
  return t ? INTENT_TEXT[t] || "" : STATUS_INTENT[item?.status] || "";
}

export const scopeOf = (intent, id, item) =>
  REPO_INTENTS.includes(intent) && item?.repo
    ? `repo:${item.repo}`
    : `item:${id}`;

const isActive = (r) => (r.active !== undefined ? r.active === true : !r.done);

// Map "<intent>|<scope>" -> the newest active row.
export function activeBlocks(rows, byId) {
  const out = new Map();
  for (const r of rows || []) {
    if (!r.item || !isActive(r)) continue;
    const item = byId.get(r.item);
    const intent = intentOf(r, item);
    if (!intent) continue;
    const key = `${intent}|${r.scope || scopeOf(intent, r.item, item)}`;
    const cur = out.get(key);
    if (!cur || String(r.received) > String(cur.received)) out.set(key, r);
  }
  return out;
}

// The row that already took the item's next step, or null.
export function blockFor(it, blocks) {
  const intent = STATUS_INTENT[it.status];
  return intent
    ? blocks.get(`${intent}|${scopeOf(intent, it.id, it)}`) || null
    : null;
}

const stamp = (received) => {
  const m = /^(\d{4})(\d\d)(\d\d)T(\d\d)(\d\d)/.exec(received || "");
  return m ? new Date(Date.UTC(+m[1], m[2] - 1, +m[3], +m[4], +m[5])) : null;
};

// «Già presa in carico · 16:24» (other days: «· 12 ott 16:24»); «· promozione Ratio» when the action
// that holds the repo's promotion/release sits on another card.
export function blockText(row, it, now = new Date()) {
  const d = stamp(row.received);
  let when = "";
  if (d) {
    const hm = d.toLocaleTimeString("it-IT", {
      hour: "2-digit",
      minute: "2-digit",
    });
    when =
      d.toDateString() === now.toDateString()
        ? hm
        : `${d.toLocaleDateString("it-IT", { day: "numeric", month: "short" }).replace(".", "")} ${hm}`;
  }
  const intent = STATUS_INTENT[it.status];
  const other = row.item !== it.id && REPO_INTENTS.includes(intent);
  return [
    "Già presa in carico",
    when,
    other ? `${REPO_WORD[intent]} ${repoName(it.repo)}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
}
