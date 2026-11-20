import { cardCount } from "../cb-counts.js";
// Board v3 (direction A): pure view logic over data/work-items.json items. No DOM here.
import { openCallKind } from "../cb-state.js";
import { CALL_KINDS, isAnswered } from "../cb-bits.js";
import { isActionAsk, isOpenCall } from "../cb-tasks.js";
import { PRIORITIES, PRIORITY_LABEL, prioKey, priorityOf } from "../cb-priority.js";

export const OPEN_COLUMNS = [
  "Backlog",
  "Doing",
  "PR review",
  "PR fix",
  "Merge",
];
export const SHOWN = 6; // cards per column before "Altre N"
const ACTIVE = new Set(["Doing", "PR review", "PR fix", "Merge"]);

const REPO_NAMES = {
  "app-himalaia": "Himalaia",
  "app-ratio": "Ratio",
  atrium: "Atrium",
  "adlimen-ui": "adlimen-ui",
  nexus: "Nexus",
  orchestra: "Orchestra",
  "claude-dotfiles": "dotfiles",
  "adlimen-cicd": "CI/CD",
  "adlimen-infra": "Infra",
  ".agents": "agents",
};
export const repoName = (r) => REPO_NAMES[r] || r || "";
export const itemRepos = (it) => [...new Set(it.repos?.length ? it.repos : [it.repo || 'orchestra'])];
export const repoLabel = (it) => itemRepos(it).map(repoName).join(' · ');

const prNum = (it) => it.pr_no ?? it.pr?.number ?? null;
const issueNum = (it) => it.issue_no ?? it.issue?.number ?? null;
const isRunning = (it) => Boolean(it.child?.running);
export const isCall = (it) => Boolean(it.your_call);

export const metaLine = (it) =>
  `${repoLabel(it)} · ${it.status}${prNum(it) ? ` · #${prNum(it)}` : ""}`;

const hm = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
};

// "Presa in carico" line of an item whose action Orchestra handled: { text, card } or null.
// card = id of the item that holds the child's report (opens its drawer), "" when none.
export function takenLine(it) {
  const t = it.taken;
  if (!t) return null;
  const done = t.state === "finito" ? [`finito${t.end ? ` ${hm(t.end)}` : ""}${t.ok ? "" : ", con errori"}`] : [t.state];
  const parts = ["Presa in carico", ...(t.slug ? [t.slug, ...done] : [t.state, t.note].filter(Boolean))];
  return { text: parts.join(" · "), card: t.card || "" };
}

// Your call, most urgent first: blocked or active work, then the oldest. Items acted on from this
// page leave at once (isOpenCall), before the data refresh says so.
export function callList(items) {
  const rank = (it) => (it.blocked || ACTIVE.has(it.status) ? 0 : 1);
  return items
    .filter(isOpenCall)
    .sort(
      (a, b) =>
        rank(a) - rank(b) || String(a.updated).localeCompare(String(b.updated)),
    );
}

// Default card order: priority and "Fai prima" order first, then your call, running, newest.
export const cardOrder = (a, b) =>
  prioKey(a) - prioKey(b) ||
  isCall(b) - isCall(a) ||
  isRunning(b) - isRunning(a) ||
  String(b.updated).localeCompare(String(a.updated));

export function matchesQuery(it, q) {
  const s = String(q || "")
    .trim()
    .toLowerCase();
  if (!s) return true;
  const hay = [
    it.title,
    it.repo,
    ...itemRepos(it),
    repoLabel(it),
    it.id,
    prNum(it) ? `#${prNum(it)}` : "",
    issueNum(it) ? `#${issueNum(it)}` : "",
  ]
    .join(" ")
    .toLowerCase();
  return hay.includes(s);
}

// A Your call whose only open asks are actions: «Da fare tu» (an open decision keeps it «Your call»).
const todoOnly = (it) => {
  const open = (it.ask || []).filter((a) => !(isActionAsk(a) ? a.answered : isAnswered(it, a)));
  return open.length > 0 && open.every(isActionAsk);
};

// One badge at most, by priority: Fatto waiting for verification (pending === "done") > sent (action
// or answer waiting for Orchestra) > blocked > Da fare tu > your call.
export function badgeKind(it, pending) {
  if (pending === "done") return "done";
  if (pending) return "sent";
  if (it.blocked) return "blocked";
  if (isCall(it)) return todoOnly(it) ? "todo" : "call";
  return "";
}

// Only http(s) or relative page names (optionally with a #section anchor): never javascript:, protocol-relative or "..".
export const safeHref = (h) =>
  /^https?:\/\/[^\s]+$/i.test(h) || (/^[\w][\w.\/-]*(#[\w\-.:]+)?$/.test(h) && !h.includes("..")) ? h : "#";

const LINKS = [
  ["pre", "PRE", "page"],
  ["mockup", "Mockup", "mockup"],
  ["post", "POST", "page"],
  ["comparison", "Prima/Dopo", "compare"],
  ["preview", "Anteprima", "preview"],
  ["display", "Display", "page"],
  ["pr", "PR", "pr"],
  ["issue", "Issue", "issue"],
];
const isHimalaia = (it) => itemRepos(it).some(r => ["app-himalaia", "himalaia"].includes(r));
const pageIdentity = (href) => {
  const origin = "https://homelab4change.siamese-dominant.ts.net:8460/";
  try {
    const url = new URL(href, origin);
    return url.origin === new URL(origin).origin ? url.pathname : href;
  } catch {
    return href;
  }
};
function visibleLinks(it, definitions) {
  const links = it.links || {};
  const strict = isHimalaia(it);
  return definitions.filter(([key]) => links[key] && (!strict || (
    typeof links[key] === "string" && safeHref(links[key]) !== "#" &&
    !(["display", "mockup", "pre", "post"].includes(key) && links.comparison &&
      pageIdentity(links[key]) === pageIdentity(links.comparison))
  )));
}
export function linkList(it) {
  const links = it.links || {};
  return visibleLinks(it, LINKS).map(([key, label, icon]) => ({
    key,
    icon,
    href: safeHref(links[key]),
    label: key === "pr" && prNum(it) ? `PR #${prNum(it)}` : label,
  }));
}

// Card meta row: repo, #issue, PR #n (linked when the URL is known), status only when the
// column is not a status (e.g. Stato swimlane by repo). [{ kind, text, href?, label? }]
export function metaParts(it, { showStatus = false } = {}) {
  const links = it.links || {};
  const out = itemRepos(it).map(r => ({ kind: "repo", text: repoName(r) }));
  const num = (kind, n, text, label) =>
    n && out.push({ kind, text, href: links[kind] ? safeHref(links[kind]) : "", label });
  num("issue", issueNum(it), `#${issueNum(it)}`, `Issue ${issueNum(it)}`);
  num("pr", prNum(it), `PR #${prNum(it)}`, `Pull request ${prNum(it)}`);
  if (showStatus && it.status) out.push({ kind: "status", text: it.status });
  return out;
}

// Card pages row: the item's review pages, most useful first.
const PAGES = [
  ["comparison", "Prima/Dopo", "compare"],
  ["pre", "PRE", "page"],
  ["mockup", "Mockup", "mockup"],
  ["post", "POST", "page"],
  ["display", "Display", "page"],
  ["preview", "Anteprima", "preview"],
];
export function pageLinks(it) {
  const links = it.links || {};
  return visibleLinks(it, PAGES).map(([key, label, icon]) => ({
    key, label, icon, href: safeHref(links[key]),
  }));
}

export function firstOpenAsk(it, answered) {
  const asks = Array.isArray(it.ask) ? it.ask : [];
  return asks.findIndex((a) => !answered(it, a));
}

// opts: { q, filtering: items are already filtered (search/filters on), keepOrder: items come
// sorted by the user's sort rules, unfolded: Set(status) opened by hand, expanded: Set(key) showing
// every card, scope: lane id (key = "<scope>|<status>"), limit: cards before "Altre N",
// openStatuses: Set(status) open in every lane (swimlanes align their columns) }.
export function columns(
  items,
  statuses,
  {
    q = "",
    filtering = false,
    keepOrder = false,
    unfolded = new Set(),
    expanded = new Set(),
    scope = "",
    limit = SHOWN,
    openStatuses = null,
  } = {},
) {
  const narrowed = filtering || Boolean(String(q).trim());
  return statuses.map((status) => {
    const key = scope ? `${scope}|${status}` : status;
    const all = items.filter((i) => i.status === status && matchesQuery(i, q));
    if (!keepOrder) all.sort(cardOrder);
    const open = openStatuses
      ? openStatuses.has(status)
      : narrowed
        ? all.length > 0
        : OPEN_COLUMNS.includes(status)
          ? all.length > 0
          : unfolded.has(status);
    const shown = expanded.has(key) ? all : all.slice(0, limit);
    return {
      status,
      key,
      ids: all.map((i) => i.id),
      total: all.length,
      shown,
      more: all.length - shown.length,
      folded: !open,
    };
  });
}

// Columns by repo for a Stato swimlane, same shape as columns(); a repo without items is folded.
export function repoColumns(items, repos, { expanded = new Set(), scope = "", limit = SHOWN } = {}) {
  return repos.map((repo) => {
    const key = `${scope}|${repo}`;
    const all = items.filter((i) => i.repo === repo);
    const shown = expanded.has(key) ? all : all.slice(0, limit);
    return {
      status: repo, label: repoName(repo), dim: "repo", key, ids: all.map((i) => i.id),
      total: cardCount(all), shown, more: all.length - shown.length, folded: !all.length,
    };
  });
}

export function phoneTabs(items, statuses) {
  const counts = {};
  for (const i of items) counts[i.status] = (counts[i.status] || 0) + 1;
  return statuses
    .filter((s) => counts[s])
    .map((status) => ({ status, count: counts[status] }));
}

// Groups for "Raggruppa": [{ key, label, items }], items keep their incoming order; empty keys last.
const byLabel = (a, b) => a.label.localeCompare(b.label, "it", { numeric: true });
const GROUP_BY = {
  status: { key: (it) => it.status || "", label: (k) => k },
  call: { key: (it) => openCallKind(it), label: (k) => k || "Nessuna richiesta" },
  repo: { key: (it) => it.repo || "", label: (k) => repoName(k) || "Nessun repo" },
  agent: { key: (it) => it.agent || "", label: (k) => k || "Nessun agente" },
  priority: { key: (it) => priorityOf(it), label: (k) => PRIORITY_LABEL[k] || k },
};
export function groupItems(items, by, statuses = []) {
  const g = GROUP_BY[by];
  if (!g) return [{ key: "", label: "", items }];
  const map = new Map();
  for (const it of items) {
    const k = g.key(it);
    if (!map.has(k)) map.set(k, { key: k, label: g.label(k), items: [] });
    map.get(k).items.push(it);
  }
  const rank = (k) => {
    const order =
      by === "status" ? statuses : by === "call" ? CALL_KINDS : by === "priority" ? PRIORITIES : null;
    const i = order ? order.indexOf(k) : -1;
    return order && i >= 0 ? i : order ? order.length : 0;
  };
  return [...map.values()].sort(
    (a, b) =>
      (a.key === "") - (b.key === "") || rank(a.key) - rank(b.key) || byLabel(a, b),
  );
}

// Your call strip per repo: callList order inside, repos by count then name.
export function callGroups(items) {
  const map = new Map();
  for (const it of callList(items)) {
    if (!map.has(it.repo)) map.set(it.repo, { repo: it.repo, label: repoName(it.repo), items: [] });
    map.get(it.repo).items.push(it);
  }
  return [...map.values()].sort((a, b) => b.items.length - a.items.length || byLabel(a, b));
}
