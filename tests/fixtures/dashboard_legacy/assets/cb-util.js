// DOM helpers and formatters. All data reaches the DOM through textContent/attributes.
import { icon, statusLabel } from "./cb-icons.js";

export { icon, statusLabel };

export function safeHref(u) {
  const s = String(u ?? "").trim();
  if (/^https?:\/\/[^\s]+$/i.test(s)) return s;
  // relative page, optionally with a #fragment (anchor links to a section of a post page)
  if (/^[\w][\w.\-/]*(#[\w\-.:]+)?$/.test(s) && !s.includes("..")) return s;
  return null;
}

export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = String(v);
    else if (k === "style")
      for (const [p, val] of Object.entries(v)) el.style.setProperty(p, val);
    else if (k === "href") {
      const href = safeHref(v);
      if (href) el.setAttribute("href", href);
    } else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : String(kid));
  }
  return el;
}

export function ext(href, text, attrs = {}) {
  return h("a", { href, target: "_blank", rel: "noopener", ...attrs }, text);
}

export const KIND_LABEL = {
  feature: "funzione",
  fix: "correzione",
  docs: "documentazione",
  review: "review",
  issue: "issue",
  ops: "operazioni",
  test: "test",
  decision: "decisione",
};
export const PR_STATE = {
  open: "aperta",
  merged: "mergiata",
  closed: "chiusa",
};
export function badge(text, variant = "neutral", attrs = {}) {
  const cls =
    variant === "info"
      ? "al-badge al-badge--custom cb-badge--info"
      : `al-badge al-badge--${variant}`;
  return h("span", { ...attrs, class: cls }, text);
}

// Review verdict as quiet text; a block also carries the alert icon.
export function verdictText(v) {
  if (!v) return null;
  const up = String(v).toUpperCase();
  if (up === "BLOCK")
    return h("span", { class: "cb-verdict cb-verdict--block", title: "Review: BLOCK" }, icon("alert", { size: 14 }), "review bloccata");
  return h("span", { class: "cb-verdict", title: `Review: ${up}` }, up === "APPROVE" ? "review approvata" : `review ${v}`);
}

// Ledger outcomes are short English codes written by the orchestrator; show them in Italian.
const OUTCOME_IT = [
  ["partial", "Parziale: il figlio non ha chiuso tutto, un passo successivo ha completato"],
  ["blocked", "Bloccato: serviva qualcosa che il figlio non poteva fare"],
  ["already", "Già fatto: niente da cambiare"],
  ["fail", "Fallito"],
  ["done", "Completato"],
];
export function outcomeLabel(o) {
  const s = String(o || "").toLowerCase();
  for (const [k, v] of OUTCOME_IT) if (s.startsWith(k)) return v;
  return String(o || "—");
}

export function outcomeVariant(o) {
  const s = String(o || "").toLowerCase();
  if (!s) return "neutral";
  if (s.includes("block") || s.includes("fail")) return "error";
  if (
    s.includes("partial") ||
    s.includes("not-") ||
    s.includes("already") ||
    s.includes("attesa")
  )
    return "warning";
  return "success";
}

export function fmtDur(sec) {
  if (sec == null || Number.isNaN(Number(sec))) return "—";
  const s = Math.max(0, Math.floor(Number(sec)));
  const p = (n) => String(n).padStart(2, "0");
  return s >= 3600
    ? `${Math.floor(s / 3600)}h${p(Math.floor((s % 3600) / 60))}m`
    : `${Math.floor(s / 60)}m${p(s % 60)}s`;
}

export function money(x, digits = 2) {
  return x == null || x === "" || Number.isNaN(Number(x))
    ? "—"
    : `$${Number(x).toFixed(digits)}`;
}

const pad = (n) => String(n).padStart(2, "0");
export const hhmm = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
export const fullDate = (d) =>
  `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${hhmm(d)}`;

export function toDate(v) {
  if (v == null || v === "") return null;
  const d = typeof v === "number" ? new Date(v * 1000) : new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function relTime(v, now = new Date()) {
  const d = toDate(v);
  if (!d) return { text: "—", title: "" };
  const min = Math.round((now - d) / 60000);
  let text;
  if (min < 1) text = "adesso";
  else if (min < 60) text = `${min} min fa`;
  else if (d.toDateString() === now.toDateString()) text = hhmm(d);
  else text = `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${hhmm(d)}`;
  return { text, title: fullDate(d) };
}

export function timeEl(v, now) {
  const r = relTime(v, now);
  const d = toDate(v);
  return h(
    "time",
    { class: "cb-time", datetime: d ? d.toISOString() : null, title: r.title },
    r.text,
  );
}

export function short(text, n = 160) {
  const t = String(text ?? "")
    .split(/\s+/)
    .join(" ")
    .trim();
  return t.length <= n ? t : `${t.slice(0, n - 1)}…`;
}

// The anchor is the (≥44 px on touch) hit area; the compact tag inside is the visual.
const pageLink = (f, label) =>
  ext(f, h("span", { class: "al-tag al-tag--sm al-tag--primary" }, label), {
    class: "cb-page-link",
    title: f,
  });

export function pageLinks(pages) {
  const out = [];
  for (const type of ["pre", "post", "mockup", "display"]) {
    const files = (pages && pages[type]) || [];
    files.forEach((f, i) => {
      const label = files.length > 1 ? `${type} ${i + 1}` : type;
      out.push(pageLink(f, label));
    });
  }
  return out;
}

export function emptyState(title, description) {
  return h(
    "div",
    { class: "al-empty-state" },
    h("p", { class: "al-empty-state__title" }, title),
    description
      ? h("p", { class: "al-empty-state__description" }, description)
      : null,
  );
}

const PAGE_GROUP = {
  pre: "Prima",
  post: "Dopo",
  mockup: "Mockup",
  display: "Pagine",
};

// Pages grouped by type, each link labelled with its file name; all open in a new tab.
export function pageGroups(pages) {
  const groups = [];
  for (const type of ["pre", "post", "mockup", "display"]) {
    const files = (pages && pages[type]) || [];
    if (!files.length) continue;
    groups.push(
      h(
        "div",
        { class: "cb-page-group" },
        h("span", { class: "cb-page-group__label" }, PAGE_GROUP[type]),
        h(
          "span",
          { class: "cb-links" },
          files.map((f) =>
            pageLink(f, String(f).split("/").pop().replace(/\.html$/, "")),
          ),
        ),
      ),
    );
  }
  return groups;
}

// `code` spans in the curated copy become <code>; everything else stays text.
export function richText(text) {
  return String(text ?? "")
    .split(/`([^`]+)`/)
    .map((part, i) => (i % 2 ? h("code", null, part) : part))
    .filter((x) => x !== "");
}

function linkLabel(link, id) {
  if (id) return "Apri la decisione";
  if (/github\.com\/[^/]+\/[^/]+\/pull\//.test(link)) return "Apri la PR su GitHub";
  if (/github\.com\/[^/]+\/[^/]+\/issues\//.test(link)) return "Apri l'issue su GitHub";
  if (/^https?:/i.test(link)) return "Apri il link";
  return "Apri la pagina";
}

// Where a decision is read: each ask.link, else the item's first page, PR or issue.
export function askLinks(it) {
  const asks = Array.isArray(it?.ask) ? it.ask : [];
  const seen = new Map();
  for (const a of asks) if (a.link && safeHref(a.link) && !seen.has(a.link)) seen.set(a.link, a.id);
  if (!seen.size) {
    const p = it?.pages || {};
    const f = ["display", "pre", "post", "mockup"].map((k) => (p[k] || [])[0]).find(Boolean);
    const fb = f || it?.pr?.url || it?.issue?.url;
    if (fb && safeHref(fb)) seen.set(fb, "");
  }
  return [...seen].map(([link, id]) => ({ link, label: linkLabel(link, id) }));
}

// The approval asked of Matteo: question, "Recommended", and one action per distinct link.
// Used by the table cell (variant "cell": links as plain text).
export function askBlock(it, { variant = "card" } = {}) {
  const list = Array.isArray(it?.ask) ? it.ask : [];
  if (!list.length) return null;
  const links = askLinks(it);
  return h(
    "div",
    { class: `cb-ask cb-ask--${variant}` },
    list.map((a) =>
      h(
        "div",
        { class: "cb-ask__item" },
        h(
          "p",
          { class: "cb-ask__q" },
          a.id && a.id !== "—" ? h("span", { class: "cb-ask__id" }, `Mail ${a.id} · `) : null,
          richText(a.question),
        ),
        a.rec
          ? h("p", { class: "cb-ask__rec" }, h("span", { class: "cb-ask__rec-label" }, "Recommended: "), richText(a.rec))
          : null,
      ),
    ),
    links.length
      ? h(
          "div",
          { class: "cb-ask__actions" },
          links.map((l, i) =>
            ext(l.link, [l.label, icon("external", { size: 14 })], {
              class:
                variant === "cell"
                  ? "cb-ask__link"
                  : `al-btn al-btn--sm ${i ? "al-btn--ghost" : "al-btn--primary"} cb-ask__btn`,
              title: l.link,
            }),
          ),
        )
      : null,
  );
}
