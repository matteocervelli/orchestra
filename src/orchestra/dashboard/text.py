"""Deterministic Italian card text and structural validation."""

from __future__ import annotations

import re
from typing import Any

from .common import CLOSED, REPOS, STATUSES
from .sources import task_display_title
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
    """Deterministic Italian title; never infer a translation of raw text."""
    label = _fallback_repo_label(it)
    ref = _fallback_reference(it)
    kind = _fallback_kind(it, raw)
    if not kind and not ref:
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


def fill_text(
    it: dict[Any, Any],
    curated: set[str],
    asking: bool,
    ask_note: dict[Any, Any] | None = None,
    legacy_asking: bool = False,
    tasks: list[dict[Any, Any]] | None = None,
) -> bool:
    """Fill missing card text and record actual fallback fields."""
    asking = _human_asking(it, asking, ask_note, legacy_asking)
    title = _selected_title(it, curated, tasks)
    auto = [] if title else ["title_it"]
    it["title"] = title or fallback_title(it, it["raw_title"])
    if not it["problem"].strip():
        it["problem"] = it["title"]
    if not it["solution"].strip():
        it["solution"] = _solution_fallback(it)
        auto.append("solution")
    if not it["needs"].strip():
        it["needs"], automatic = _needs_fallback(it, asking)
        if automatic:
            auto.append("needs")
    for key in ("problem", "solution"):
        if key not in curated and key not in auto:
            auto.append(key)
    it["auto"] = sorted(auto)
    return asking


def _human_asking(
    it: dict[Any, Any],
    asking: bool,
    ask_note: dict[Any, Any] | None,
    legacy_asking: bool,
) -> bool:
    if not asking or legacy_asking:
        return asking
    if _technical_failure(it):
        override = (ask_note or {}).get("ask")
        if isinstance(override, (dict, list)):
            return bool(ask_of(it, override))
        # Retire only this generated needs fallback. Explicit rows must stay
        # lossless: the caller pairs them positionally with answer ownership.
        if it["needs"].strip() == SERVE_NEEDS:
            it["needs"] = ""
        return bool(ask_of(it))
    return asking


def _technical_failure(it: dict[Any, Any]) -> bool:
    children = it.get("children") or []
    if (
        it.get("status") != "Backlog"
        or not children
        or any(child.get("running") for child in children)
    ):
        return False
    if _independent_human_signal(it):
        return False
    last = max(children, key=lambda child: str(child.get("start") or ""))
    return last.get("exit") not in (None, 0, "0")


def _independent_human_signal(it: dict[Any, Any]) -> bool:
    return bool(
        it.get("pr")
        or it.get("decisions")
        or (it.get("triage") or {}).get("verdict") == "done?"
        or "needs-human" in it.get("labels", [])
    )


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
    return [split_advice(row, it["needs"]) for row in _ask_rows(it, override)]


def _ask_rows(
    it: dict[Any, Any], override: dict[Any, Any] | list[Any] | None
) -> list[dict[Any, Any]]:
    if isinstance(override, dict):
        override = [override]
    if isinstance(override, list):
        return [ask for ask in override if isinstance(ask, dict)]
    if it.get("decisions"):
        return [
            {
                "id": decision.get("id"),
                "question": decision.get("title"),
                "rec": decision.get("rec"),
                "link": decision.get("link"),
            }
            for decision in it["decisions"]
        ]
    if it["needs"] and not is_nothing(it["needs"]):
        return [{"link": ask_link(it)}]
    return []


def split_advice(a: dict[Any, Any], needs: str) -> dict[Any, Any]:
    """Normalize one ask and separate inline advice."""
    question, rec = _question_and_advice(a, needs)
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
    for candidate in raw if isinstance(raw, list) else []:
        option = _clean_option(candidate, seen)
        if option is None:
            continue
        seen.add(option["value"])
        out.append(option)
        if len(out) == MAX_OPTIONS:
            break
    return out


def validate(data: dict[Any, Any]) -> list[str]:
    """Check structure; this does not prove semantic request freshness."""
    return [error for item in data.get("items", []) for error in _item_errors(item)]


def _fallback_repo_label(it: dict[Any, Any]) -> str:
    repo = it.get("repo") or "orchestra"
    return " · ".join(
        REPO_LABEL.get(REPOS.get(r, r), REPOS.get(r, r))
        for r in it.get("repos") or [repo]
    )


def _fallback_reference(it: dict[Any, Any]) -> str:
    pr = (it.get("pr") or {}).get("number")
    issue = (it.get("issue") or {}).get("number")
    return f"PR #{pr}" if pr else f"Issue #{issue}" if issue else ""


def _fallback_kind(it: dict[Any, Any], raw: str) -> str:
    ids = [it["id"], *it.get("slugs", [])]
    if any(i.startswith("review-") for i in ids):
        return "Revisione indipendente"
    if any(re.search(r"-fix\d*($|-)", i) for i in ids):
        return "Correzione dopo la revisione"
    prefix = PREFIX_RE.search(raw or "")
    return PREFIX_IT[prefix.group(1).lower()] if prefix else ""


def _selected_title(
    it: dict[Any, Any], curated: set[str], tasks: list[dict[Any, Any]] | None
) -> str:
    supplied = it.pop("title_it", "")
    protected = _curated_title(it, curated, supplied)
    if protected:
        return protected
    direct = meaningful_title(supplied)
    if direct:
        return direct
    if it.get("pr") or it.get("issue"):
        return ""
    candidates = {title for task in tasks or [] if (title := task_display_title(task))}
    return candidates.pop() if len(candidates) == 1 else ""


def _curated_title(it: dict[Any, Any], curated: set[str], supplied: Any) -> str:
    if "title_it" in curated and isinstance(supplied, str) and supplied.strip():
        return supplied
    if "title" in curated and str(it.get("title") or "").strip():
        return str(it["title"])
    return ""


def _solution_fallback(it: dict[Any, Any]) -> str:
    finished = any(
        c.get("end") or c.get("exit") is not None for c in it.get("children", [])
    )
    if it["status"] == "Backlog" and finished:
        return (
            "È già stata avviata un'esecuzione; Orchestra deve verificarne "
            "esito e seguito prima di dichiarare il lavoro concluso."
        )
    return SOLUTION.get(
        it["status"], "Dettagli nel resoconto dell'agente, nel pannello di dettaglio."
    )


def _needs_fallback(it: dict[Any, Any], asking: bool) -> tuple[str, bool]:
    if asking:
        return SERVE_NEEDS, True
    if it.get("blocked"):
        return f"Niente per ora: è bloccata ({it['blocked']}).", False
    return NOTHING.get(it["status"], NOTHING_DONE), False


def _question_and_advice(a: dict[Any, Any], needs: str) -> tuple[str, str]:
    question, rec = str(a.get("question") or needs), str(a.get("rec") or "")
    if not rec:
        parts = ADVICE_RE.split(question, maxsplit=1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return parts[0].strip(), parts[1].strip()
    return question, rec


def _clean_option(raw: object, seen: set[str]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    value, label = raw.get("value"), raw.get("label")
    if (
        not (isinstance(value, str) and OPTION_VALUE_RE.fullmatch(value))
        or value == "other"
    ):
        return None
    if not isinstance(label, str) or not label.strip() or value in seen:
        return None
    return {
        "value": value,
        "label": label.strip()[:MAX_OPTION_LABEL],
        "recommended": raw.get("recommended") is True,
    }


def _item_errors(it: dict[Any, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("title", "problem", "solution", "needs"):
        if not str(it.get(key) or "").strip():
            errors.append(f"{it['id']}: empty {key}")
    if it.get("status") not in STATUSES:
        errors.append(f"{it['id']}: unknown status {it.get('status')!r}")
    return errors + _human_text_errors(it)


def _human_text_errors(it: dict[Any, Any]) -> list[str]:
    errors: list[str] = []
    if not (it.get("your_call") or it.get("serve_te")):
        return errors
    if not it.get("ask"):
        errors.append(f"{it['id']}: your_call without ask")
    for ask in it.get("ask") or []:
        for field in ("question", "rec"):
            if not str(ask.get(field) or "").strip():
                errors.append(f"{it['id']}: ask without {field}")
    return errors
