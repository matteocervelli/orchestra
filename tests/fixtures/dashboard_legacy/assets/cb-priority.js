// Priority of a work item (P0 urgent .. P3 low), where it came from, and the sort key. Pure, no DOM.
export const PRIORITIES = ["P0", "P1", "P2", "P3"];
export const PRIORITY_NAME = { P0: "urgente", P1: "alta", P2: "normale", P3: "bassa" };
export const PRIORITY_LABEL = Object.fromEntries(
  PRIORITIES.map((p) => [p, `${p} · ${PRIORITY_NAME[p]}`]),
);
const SRC = {
  nota: "impostata da te",
  etichetta: "da etichetta",
  titolo: "dal titolo",
  decisione: "da decisione",
};
export const srcLabel = (src) => SRC[src] || "predefinita";

export const priorityOf = (it) => (PRIORITIES.includes(it?.priority) ? it.priority : "P2");
export const orderOf = (it) => (Number.isInteger(it?.order) ? it.order : 0);
// Ascending: P0 first, then the lower `order`.
export const prioKey = (it) => PRIORITIES.indexOf(priorityOf(it)) * 100000 + orderOf(it);

// Text for the chip title / screen readers. `proposed` = a priority waiting for Orchestra.
export function priorityText(it, proposed = "") {
  return proposed
    ? `Priorità ${proposed} (proposta, in attesa di Orchestra)`
    : `Priorità ${priorityOf(it)} (${srcLabel(it?.priority_src)})`;
}

// "Fai prima": one step before every item that already has this priority (clamped to the server's ±9999).
export function orderBefore(items, priority) {
  const same = (items || []).filter((i) => priorityOf(i) === priority).map(orderOf);
  return Math.max(-9999, (same.length ? Math.min(...same) : 0) - 1);
}
