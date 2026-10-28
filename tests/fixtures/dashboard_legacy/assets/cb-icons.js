// Stroke icons (24x24, 2px, currentColor) and the status label: icon + word, never colour alone.
const NS = "http://www.w3.org/2000/svg";

const PATHS = {
  clock: ["circle:12,12,9", "M12 7v5l3 2"],
  play: ["circle:12,12,9", "M10 8.5v7l5.5-3.5z"],
  eye: [
    "M2.5 12s3.5-6.5 9.5-6.5 9.5 6.5 9.5 6.5-3.5 6.5-9.5 6.5S2.5 12 2.5 12z",
    "circle:12,12,2.5",
  ],
  alert: [
    "M10.3 4 2.2 18a2 2 0 0 0 1.7 3h16.2a2 2 0 0 0 1.7-3L13.7 4a2 2 0 0 0-3.4 0z",
    "M12 9.5v4",
    "M12 17h.01",
  ],
  ask: [
    "circle:12,12,9",
    "M9.2 9.2a3 3 0 0 1 5.7 1.1c0 2-2.9 2.6-2.9 2.6",
    "M12 16.8h.01",
  ],
  check: ["circle:12,12,9", "m8.5 12 2.5 2.5 4.5-5"],
  minus: ["circle:12,12,9", "M8.5 12h7"],
  external: ["M8 16 16 8", "M9 8h7v7"],
  chevron: ["m9 6 6 6-6 6"],
  activity: ["M21 12h-4l-3 8-4-16-3 8H3"],
  merge: ["circle:6,5,2", "circle:6,19,2", "circle:18,12,2", "M6 7v10", "M6 9a7 7 0 0 0 10 3"],
  layers: ["m12 3 9 5-9 5-9-5z", "m3 13 9 5 9-5"],
  deploy: ["M12 15V4", "m7 9 5-5 5 5", "M4 20h16"],
  lock: ["M6 11h12v9H6z", "M8.5 11V8a3.5 3.5 0 0 1 7 0v3"],
  arrow: ["M5 12h14", "m13 6 6 6-6 6"],
  close: ["M6 6l12 12", "M18 6 6 18"],
};

export function icon(name, { size = 16, cls = "" } = {}) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(size));
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.setAttribute("class", `cb-icon${cls ? ` ${cls}` : ""}`);
  for (const p of PATHS[name] || []) {
    if (p.startsWith("circle:")) {
      const [cx, cy, r] = p.slice(7).split(",");
      const c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", cx);
      c.setAttribute("cy", cy);
      c.setAttribute("r", r);
      svg.append(c);
    } else {
      const path = document.createElementNS(NS, "path");
      path.setAttribute("d", p);
      svg.append(path);
    }
  }
  return svg;
}

// Status vocabulary (English names are the data's own; the legend line is the only translation).
export const STATUS_ICON = {
  Backlog: "clock",
  Doing: "play",
  "PR review": "eye",
  "PR fix": "alert",
  Merge: "merge",
  Integration: "layers",
  Main: "check",
  Deployed: "deploy",
  Dropped: "minus",
};
export const STATUS_NOTE = {
  Backlog: "Non ancora iniziato: nessuno ci lavora.",
  Doing: "Un agente ci sta lavorando.",
  "PR review": "PR aperta, in attesa della review.",
  "PR fix": "Review bloccante o conflitti: va corretta.",
  Merge: "Review approvata: pronta per il merge.",
  Integration: "Mergiata in auto/integration.",
  Main: "Arrivata su main.",
  Deployed: "In produzione o pubblicata.",
  Dropped: "Chiusa senza merge: il motivo è sull'etichetta.",
};

export function statusLabel(status) {
  const span = document.createElement("span");
  span.className = "cb-status";
  span.append(
    icon(STATUS_ICON[status] || "minus"),
    document.createTextNode(status || "—"),
  );
  return span;
}
