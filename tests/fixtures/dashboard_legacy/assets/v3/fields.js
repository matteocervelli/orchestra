// «Campi visibili»: card fields and table columns from the URL (?fields=), plus the
// card's «12 min fa» update time. Legacy storage helpers remain for older callers. No DOM here.
export const FIELDS = [
  { key: "priority", label: "Priorità" },
  { key: "repo", label: "Repo" },
  { key: "refs", label: "#issue / PR" },
  { key: "pages", label: "Link pagine" },
  { key: "updated", label: "Aggiornata" },
  { key: "agent", label: "Agente / revisore" },
  { key: "blocked", label: "Stato blocco" },
  { key: "asks", label: "Conteggio domande" },
  { key: "preview", label: "Anteprima" },
];
const KEYS = FIELDS.map((f) => f.key);
export const DEFAULT_FIELDS = new Set(KEYS.filter((k) => k !== "agent"));
const STORE_KEY = "orchestra-fields-v1";

const ordered = (set) => KEYS.filter((k) => set.has(k));

// "repo,updated" -> Set in toolbar order; "none" -> empty; "" / null / nothing valid -> null (not set).
export function parseFields(v) {
  const s = String(v ?? "").trim();
  if (s === "none") return new Set();
  const keys = s.split(",").map((x) => x.trim());
  const set = new Set(KEYS.filter((k) => keys.includes(k)));
  return set.size ? set : null;
}

// "" for the default set (left out of the URL), "none" for nothing, else the keys in toolbar order.
export function serializeFields(set) {
  const keys = ordered(set);
  if (
    keys.length === DEFAULT_FIELDS.size &&
    keys.every((k) => DEFAULT_FIELDS.has(k))
  )
    return "";
  return keys.length ? keys.join(",") : "none";
}

// A bookmark carries its own fields; a plain URL always starts with the defaults.
export function loadFields(urlValue) {
  return parseFields(urlValue) || new Set(DEFAULT_FIELDS);
}

// true when stored; false when this browser cannot keep it (the URL still carries it).
export function saveFields(set, storage) {
  try {
    if (!storage) return false;
    const v = serializeFields(set);
    if (v) storage.setItem(STORE_KEY, v);
    else storage.removeItem(STORE_KEY);
    return true;
  } catch {
    return false;
  }
}

const pad = (n) => String(n).padStart(2, "0");
const absolute = (d) =>
  `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;

// Item `updated` -> { text: "12 min fa", abs: "14/10/2026 16:18", iso } or null when missing/invalid.
export function ago(v, now = new Date()) {
  const d = v ? new Date(v) : null;
  if (!d || Number.isNaN(d.getTime())) return null;
  const min = Math.max(0, Math.floor((now - d) / 60000));
  let text;
  if (min < 1) text = "adesso";
  else if (min < 60) text = `${min} min fa`;
  else if (min < 24 * 60) text = `${Math.floor(min / 60)} h fa`;
  else if (min < 7 * 24 * 60) text = `${Math.floor(min / 1440)} g fa`;
  else text = `${pad(d.getDate())}/${pad(d.getMonth() + 1)}`;
  return { text, abs: absolute(d), iso: d.toISOString() };
}
