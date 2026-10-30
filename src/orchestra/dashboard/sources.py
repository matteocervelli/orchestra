"""Canonical dashboard helpers, extracted from reviewed producer source."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .provenance import parse_task_provenance
from .titles import meaningful_title

AUTHOR_PREFIX = re.compile(r"^(?:GO\s+)?ROOT\s*\d+\s*(?:[-—:]\s*)?", re.I)
AUTHOR_UNSAFE = re.compile(
    r"https?://|(?:^|\s)(?:/|~/|\.\.?/)|\.(?:md|py|json|log|sh)\b|"
    r"\.(?:toml|ya?ml|html?|conf|csv|sql|txt)\b|`|\$\(|--[a-z]|"
    r"\b(?:bin|src|docs|tasks|tests|scripts|config|etc|var|home|data)/\S+|"
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b|"
    r"\b[\w-]+\.(?:dev|net|com|org|local)\b|"
    r"\b(?:git|uv|pnpm|npm|docker|ssh|sudo|bash|sh|python3?|exec)\s",
    re.I,
)
AUTHOR_GENERIC = re.compile(
    r"\bgoal\s+attivo\b|^(?:riprendi|ripresa|resume|read|leggi|non|preserva|mantieni)\b|"
    r"^(?:base\s+[a-f0-9]{6,}|processo precedente|review delta finale\s*\d)|"
    r"\bda avviare\b|^richiesta\s+chat-|^cambio di priorità operativo\b|"
    r"\bGO\s+sorgenti\b.*\bintegrati\b|"
    r"\b(?:APPROVE|PASS|CHANGES_REQUESTED|DEPLOYED|READY|EXIT\s*\d|"
    r"completat[oaie]|rilasciat[oaie]|approvat[oaie])\b|\baccettazione\s+ROOT\b",
    re.I,
)
ITALIAN_INTENT = re.compile(
    r"\b(?:implementa|implementare|correggi|correggere|verifica|verificare|"
    r"prepara|preparare|completa|completare|integra|integrare|rivedi|rivedere|"
    r"analizza|analizzare|risolvi|risolvere|consegna|consegnare|definisci|definire|"
    r"collega|collegare)\b",
    re.I,
)
ITALIAN_WORDS = frozenset(
    [
        "e",
        "in",
        "per",
        "con",
        "del",
        "della",
        "delle",
        "degli",
        "dei",
        "di",
        "nel",
        "nella",
        "senza",
        "solo",
        "sola",
        "dopo",
        "prima",
        "una",
        "un",
        "il",
        "la",
        "le",
        "dentro",
        "al",
        "alla",
        "alle",
        "sul",
        "sullo",
        "sulla",
        "sulle",
        "dello",
    ]
)
ITALIAN_EXCLUSIVE = ITALIAN_WORDS - {"in", "per", "con", "un"}
ITALIAN_NOUNS = frozenset(
    [
        "lettura",
        "sorgenti",
        "immagine",
        "catalogo",
        "documenti",
        "voci",
        "condiviso",
        "compatibilità",
        "bozza",
        "richiesta",
        "risposta",
        "mappatura",
        "contratto",
        "permessi",
        "titoli",
        "notifiche",
        "documentazione",
        "creazione",
        "candidata",
        "prova",
        "tentativo",
        "consegna",
        "completo",
        "indipendente",
        "separata",
        "interfaccia",
        "proposta",
        "controllo",
        "controlli",
        "metriche",
        "documentale",
    ]
)


def authored_title(value: str) -> str:
    """Retain bounded Italian author text, never translate or mine a slug."""
    if len(value) > 400:
        return ""
    value = re.sub(r"^#+\s*", "", value.strip())
    value = re.sub(
        r"^(?:GO\s+)?ROOT\s+\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}\s+UTC\s*[-—:]\s*",
        "",
        value,
        flags=re.I,
    )
    value = AUTHOR_PREFIX.sub("", value)
    value = re.sub(r"[,;]\s*fonte accettata\s*$", "", value, flags=re.I)
    if AUTHOR_UNSAFE.search(value) or AUTHOR_GENERIC.search(value):
        return ""
    words = set(re.findall(r"[^\W_]+", value.casefold()))
    if not _italian_author_text(value, words):
        return ""
    return meaningful_title(value)


def _italian_author_text(value: str, words: set[str]) -> bool:
    return bool(
        ITALIAN_INTENT.search(value)
        or words & ITALIAN_EXCLUSIVE
        or len(words & ITALIAN_WORDS) >= 2
        or bool(words & ITALIAN_NOUNS)
        or re.search(r"\b\w+(?:zione|zioni|ità)\b", value, re.I)
    )


def _body_goal(text: str) -> str:
    """Only explicit author goal sections; bounded and never command/path text."""
    lines = text[:16000].splitlines()[:120]
    for index, line in enumerate(lines):
        section = re.match(
            r"^(?:#{1,6}\s*)?(Obiettivo|Scopo|Consegna corrente)\b\s*:?(.*)$",
            line,
            re.I,
        )
        if not section:
            continue
        inline = _goal_sentence(section.group(2))
        if inline:
            return inline
        following = [section.group(2)]
        for candidate in lines[index + 1 : index + 9]:
            if candidate.startswith("#"):
                break
            following.append(candidate)
        block = "\n".join(following)[:4096]
        if title := _scoped_goal(block):
            return title
        if title := authored_title(block.strip()):
            return title
    return ""


def _scoped_goal(block: str) -> str:
    for scoped in re.finditer(
        r"\b(?:nuovo\s*scope|obiettivo|scopo)\s*:\s*", block, re.I
    ):
        if title := _goal_sentence(block[scoped.end() :]):
            return title
    # A declared uppercase action may follow context containing a path. Never
    # select an arbitrary procedural sentence from the surrounding paragraph.
    for action in re.finditer(
        r"\b(?:IMPLEMENTA|CORREGGI|INTEGRA|VERIFICA|PREPARA|COMPLETA)\b", block
    ):
        if title := _goal_sentence(block[action.start() :]):
            return title
    return ""


def _goal_sentence(value: str) -> str:
    sentence = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ù])|\n", value, maxsplit=1)[0]
    return authored_title(sentence)


def task_display_title(task: dict[Any, Any]) -> str:
    """Read author context only for presentation; leave task identity input intact."""
    for key in ("goal", "header"):
        value = task.get(key)
        if isinstance(value, str) and (title := authored_title(value)):
            return title
    body = task.get("text")
    return (_body_heading(body) or _body_goal(body)) if isinstance(body, str) else ""


def _body_heading(text: str) -> str:
    # COMMON may precede the author's H1; identity goal/header stay untouched.
    for line in text[:16000].splitlines()[:120]:
        if line.startswith("# "):
            return authored_title(line)
    return ""


def tasks(root: Path) -> dict[str, dict[Any, Any]]:
    out = {}
    for p in sorted((root / "tasks").glob("*.md")):
        if p.stem == "COMMON":
            continue
        text = p.read_text(errors="replace")
        first = (text.splitlines() or [""])[0]
        provenance, errors = parse_task_provenance(text)
        wrapper = re.fullmatch(rf"# Task: {re.escape(p.stem)} \((.*)\)", first)
        goal = wrapper.group(1) if wrapper else re.sub("^#\\s*(Task:\\s*)?", "", first)
        out[p.stem] = {
            "slug": p.stem,
            "goal": goal.strip(),
            "header": first,
            "text": text,
            "work_provenance": provenance,
            "provenance_errors": errors,
            "mtime": p.stat().st_mtime,
        }
    return out
