"""Deterministic Italian card text and structural validation."""

from __future__ import annotations

import re
from typing import Any

from .common import CLOSED, REPOS, STATUSES
from .titles import meaningful_title

NOTHING_DONE = "Niente: già fatto."
NOTHING = {
    "Backlog": "Niente per ora: è in coda, la prende un agente.",
    "Doing": "Niente per ora: un agente ci sta lavorando.",
    "PR review": "Niente per ora: è in revisione indipendente.",
    "PR fix": "Niente per ora: un agente corregge i problemi trovati in revisione.",
    "Merge": "Niente per ora: è approvata, aspetta il merge in integration.",
    "Integration": (
        "Niente per te: Orchestra deve verificare promozione,"
        " rilascio e risultato operativo del codice integrato"
        "."
    ),
    "Main": (
        "Niente per te: Orchestra deve verificare rilascio e "
        "risultato operativo del codice su main."
    ),
    "Deployed": NOTHING_DONE,
    "Dropped": "Niente: non serve più.",
}
SOLUTION = {
    "Backlog": "Da pianificare: nessun agente l'ha ancora presa in carico.",
    "Doing": "In lavorazione: un agente ci sta lavorando, nessun risultato ancora.",
    "Dropped": "Nessuna: il lavoro non serve più.",
}
SERVE_NEEDS = "Guarda il dettaglio e decidi come procedere."
NO_REC = "nessuno, scegli tu: nessun agente ha lasciato una proposta per questa scelta."
REPO_LABEL = {
    "himalaia": "Himalaia",
    "ratio": "Ratio",
    "adlimenui": "adlimen-ui",
    "dotfiles": "dotfiles",
    "nexus": "Nexus",
    "atrium": "Atrium",
    "orchestra": "Orchestra",
}
PREFIX_IT = {
    "feat": "nuova funzione",
    "fix": "correzione",
    "docs": "documentazione",
    "ci": "CI",
    "chore": "manutenzione",
    "test": "test",
    "refactor": "riorganizzazione",
    "perf": "prestazioni",
}
PREFIX_RE = re.compile(
    "(?:^|\\]\\s*|\\s)(" + "|".join(PREFIX_IT) + ")(?:\\([^)]*\\))?!?:", re.I
)
ADVICE_RE = re.compile("\\s*\\bConsiglio:\\s*")


def fallback_title(it: dict[Any, Any], raw: str) -> str:
    "Deterministic Italian title from what the item is; never the raw English title."
    repo = it.get("repo") or "orchestra"
    label = " · ".join(
        REPO_LABEL.get(REPOS.get(r, r), REPOS.get(r, r))
        for r in it.get("repos") or [repo]
    )
    ids = [it["id"], *it.get("slugs", [])]
    pr, issue = (
        (it.get("pr") or {}).get("number"),
        (it.get("issue") or {}).get("number"),
    )
    ref = f"PR #{pr}" if pr else f"Issue #{issue}" if issue else ""
    kind = ""
    if any(i.startswith("review-") for i in ids):
        kind = "Revisione indipendente"
    elif any(re.search("-fix\\d*($|-)", i) for i in ids):
        kind = "Correzione dopo la revisione"
    else:
        m = PREFIX_RE.search(raw or "")
        if m:
            kind = PREFIX_IT[m.group(1).lower()]
    if not kind and (not ref):
        kind = "lavoro"
    return " · ".join(x for x in (label, kind, ref) if x)


def uncurated_open(data: dict[Any, Any]) -> list[dict[Any, Any]]:
    """Open cards still using an automatic fallback title."""
    return [
        i
        for i in data.get("items", [])
        if i["status"] not in CLOSED and "title_it" in i["auto"]
    ]


def is_nothing(needs: str) -> bool:
    return needs.startswith("Niente")


def fill_text(it: dict[Any, Any], curated: set[str], asking: bool) -> None:
    """Fill missing card text and record actual fallback fields."""
    supplied = it.pop("title_it", "")
    if "title_it" in curated and isinstance(supplied, str) and supplied.strip():
        title = supplied
    elif "title" in curated and str(it.get("title") or "").strip():
        title = str(it["title"])
    else:
        title = meaningful_title(supplied)
    auto = [] if title else ["title_it"]
    it["title"] = title or fallback_title(it, it["raw_title"])
    if not it["problem"].strip():
        it["problem"] = it["title"]
    if not it["solution"].strip():
        finished = any(
            c.get("end") or c.get("exit") is not None for c in it.get("children", [])
        )
        if it["status"] == "Backlog" and finished:
            it["solution"] = (
                "È già stata avviata un'esecuzione; Orchestra deve ve"
                "rificarne esito e seguito prima di dichiarare il lav"
                "oro concluso."
            )
        else:
            it["solution"] = SOLUTION.get(
                it["status"],
                "Dettagli nel resoconto dell'agente, nel pannello di dettaglio.",
            )
        auto.append("solution")
    if not it["needs"].strip():
        if asking:
            it["needs"] = SERVE_NEEDS
            auto.append("needs")
        elif it.get("blocked"):
            it["needs"] = f"Niente per ora: è bloccata ({it['blocked']})."
        else:
            it["needs"] = NOTHING.get(it["status"], NOTHING_DONE)
    for k in ("problem", "solution"):
        if k not in curated and k not in auto:
            auto.append(k)
    it["auto"] = sorted(auto)


def ask_link(it: dict[Any, Any]) -> str:
    return (it["pr"] or {}).get("url") or (it["issue"] or {}).get("url") or ""


def needs_of(it: dict[Any, Any]) -> str:
    parts = []
    for d in it.get("decisions", []):
        parts.append(f"Mail {d['id']}: {d['title']} (consiglio: {d.get('rec', '')})")
    if it["pr"] and it["pr"]["state"] == "open" and ("needs-human" in it["labels"]):
        parts.append("PR etichettata needs-human: rivedila e decidi il merge.")
    if (it.get("triage") or {}).get("verdict") == "done?" and (not it["pr"]):
        parts.append("Conferma che è già risolta e chiudi la issue.")
    return " ".join(parts)


def ask_of(
    it: dict[Any, Any], override: dict[Any, Any] | list[Any] | None = None
) -> list[dict[Any, Any]]:
    "One-line questions with the recommended answer: notes `ask` > decisions > needs."
    if isinstance(override, dict):
        override = [override]
    if isinstance(override, list):
        rows = [a for a in override if isinstance(a, dict)]
    elif it.get("decisions"):
        rows = [
            {
                "id": d.get("id"),
                "question": d.get("title"),
                "rec": d.get("rec"),
                "link": d.get("link"),
            }
            for d in it["decisions"]
        ]
    elif it["needs"] and (not is_nothing(it["needs"])):
        rows = [{"link": ask_link(it)}]
    else:
        rows = []
    return [split_advice(a, it["needs"]) for a in rows]


def split_advice(a: dict[Any, Any], needs: str) -> dict[Any, Any]:
    """Normalize one ask and separate inline advice."""
    question = str(a.get("question") or needs)
    rec = str(a.get("rec") or "")
    if not rec:
        parts = ADVICE_RE.split(question, maxsplit=1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            question, rec = (parts[0].strip(), parts[1].strip())
    out: dict[str, Any] = {
        "id": str(a.get("id") or ""),
        "question": question,
        "rec": rec,
        "link": str(a.get("link") or ""),
        "kind": str(a.get("kind") or ""),
    }
    options = clean_options(a.get("options"))
    if options:
        out["options"] = options
        out["multi"] = a.get("multi") is True
    return out


OPTION_VALUE_RE = re.compile("^[A-Za-z0-9._-]{1,64}$")
MAX_OPTIONS = 24
MAX_OPTION_LABEL = 200


def clean_options(raw: object) -> list[dict[Any, Any]]:
    """Normalize bounded ask choices and reject duplicates/reserved values."""
    out: list[dict[Any, Any]] = []
    seen: set[str] = set()
    for o in raw if isinstance(raw, list) else []:
        if not isinstance(o, dict):
            continue
        value, label = (o.get("value"), o.get("label"))
        if (
            not (isinstance(value, str) and OPTION_VALUE_RE.fullmatch(value))
            or value == "other"
        ):
            continue
        if not isinstance(label, str) or not label.strip() or value in seen:
            continue
        seen.add(value)
        out.append(
            {
                "value": value,
                "label": label.strip()[:MAX_OPTION_LABEL],
                "recommended": o.get("recommended") is True,
            }
        )
        if len(out) == MAX_OPTIONS:
            break
    return out


def validate(data: dict[Any, Any]) -> list[str]:
    """Check structure; this does not prove semantic request freshness."""
    errs = []
    for it in data.get("items", []):
        for k in ("title", "problem", "solution", "needs"):
            if not str(it.get(k) or "").strip():
                errs.append(f"{it['id']}: empty {k}")
        if it.get("status") not in STATUSES:
            errs.append(f"{it['id']}: unknown status {it.get('status')!r}")
        if it.get("your_call") or it.get("serve_te"):
            if not it.get("ask"):
                errs.append(f"{it['id']}: your_call without ask")
            for a in it.get("ask") or []:
                if not str(a.get("question") or "").strip():
                    errs.append(f"{it['id']}: ask without question")
                if not str(a.get("rec") or "").strip():
                    errs.append(f"{it['id']}: ask without rec")
    return errs
