// Small pieces shared by the Your call strip, board cards and drawer: tags, agent line, UI gates, answer action.
import { h, ext, icon, richText } from "./cb-util.js";

export const CALL_KINDS = [
  "decide",
  "approve mockup",
  "approve UI",
  "approve merge",
  "action",
];
export const ANSWERED_TEXT =
  "Risposta inviata, in attesa che Orchestra la applichi";

const asks = (it) => (Array.isArray(it?.ask) ? it.ask : []);
export { asks };

// The bridge accepts ^[A-Za-z0-9._-]{1,64}$: the decision id when it has one, else the item id.
const ID_RE = /^[A-Za-z0-9._-]{1,64}$/;
export function decisionId(it, a) {
  if (a && ID_RE.test(a.id || "")) return a.id;
  return String(it.id || "item")
    .replace(/[^A-Za-z0-9._-]/g, "-")
    .slice(0, 64);
}

// Answers sent from this page, kept until a data refresh reports them as answered.
export const sent = new Set();
export const isAnswered = (it, a) =>
  Boolean(a?.answered) || sent.has(decisionId(it, a));
export function pruneSent(items) {
  for (const it of items)
    for (const a of asks(it)) if (a.answered) sent.delete(decisionId(it, a));
}

export const callTag = (kind) =>
  h(
    "span",
    { class: "cb-tag cb-tag--call" },
    icon("ask", { size: 14 }),
    kind || "decide",
  );

export const blockedTag = (reason) =>
  reason
    ? h(
        "span",
        { class: "cb-tag cb-tag--blocked", title: `Blocked: ${reason}` },
        icon("lock", { size: 14 }),
        `Blocked: ${reason}`,
      )
    : null;

export const droppedTag = (it) =>
  it.status === "Dropped" && it.dropped
    ? h("span", { class: "cb-tag" }, it.dropped)
    : null;

// "Codex sol · review Claude"
export function agentText(it) {
  const parts = [];
  if (it.agent) parts.push(it.agent);
  if (it.reviewer) parts.push(`review ${it.reviewer}`);
  return parts.join(" · ");
}
export const agentLine = (it, cls = "cb-agent") => {
  const t = agentText(it);
  return t ? h("p", { class: cls }, t) : null;
};

// UI gates: Mockup (pre) → Comparison (before · mockup · after) → Preview (live link).
export function gatesRow(it) {
  if (!it.ui) return null;
  const g = it.gates || {};
  const step = (label, href, extra) =>
    href
      ? ext(
          href,
          [label, extra ? h("span", { class: "cb-gate__extra" }, extra) : null],
          { class: "cb-gate cb-gate--on", title: href },
        )
      : h("span", { class: "cb-gate cb-gate--off" }, `${label} missing`);
  const arrow = () =>
    h("span", { class: "cb-gate__arrow", "aria-hidden": "true" }, "→");
  return h(
    "p",
    { class: "cb-gates", role: "group", "aria-label": "Porte UI" },
    step("Mockup", g.mockup),
    h("span", { class: "cb-gates__pair" }, arrow(), step(
      "Comparison",
      g.comparison,
      g.comparison && g.mockup && g.comparison_has_mockup === false ? " (senza mockup)" : "",
    )),
    h("span", { class: "cb-gates__pair" }, arrow(), step(
      "Preview",
      g.preview,
      g.preview && !g.preview_live ? " (offline)" : g.preview ? " (live)" : "",
    )),
  );
}

export const recLine = (a, cls = "cb-ask__rec") =>
  a.rec
    ? h(
        "p",
        { class: cls },
        h("span", { class: "cb-ask__rec-label" }, "Recommended: "),
        richText(a.rec),
      )
    : null;

// "Rispondi" (opens the decision modal) or the answered note; key is where focus returns.
export function answerAction(it, i, where, { full = false } = {}) {
  const a = asks(it)[i];
  const key = `${where}:${it.id}:${i}`;
  if (isAnswered(it, a))
    return h(
      "p",
      { class: "cb-answered", tabindex: "-1", "data-key": key },
      icon("check", { size: 16 }),
      ANSWERED_TEXT,
    );
  return h(
    "button",
    {
      type: "button",
      class: `al-btn al-btn--primary al-btn--sm cb-answer${full ? " cb-answer--full" : ""}`,
      "data-action": "answer",
      "data-id": it.id,
      "data-ask": String(i),
      "data-key": key,
    },
    "Rispondi",
  );
}
