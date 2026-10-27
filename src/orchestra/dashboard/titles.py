"""Single admission policy shared by start, completion and title selection."""

from __future__ import annotations

import re
from typing import Any

_GENERIC = {
    "lavoro",
    "revisione indipendente",
    "correzione dopo la revisione",
    "nuova funzione",
    "correzione",
    "documentazione",
    "manutenzione",
    "test",
    "riorganizzazione",
    "prestazioni",
    "ci",
}
_REPOS = {"orchestra", "nexus", "atrium", "himalaia", "ratio", "adlimen-ui", "dotfiles"}


def generic_title(value: str) -> bool:
    if re.fullmatch(r"[A-Za-z0-9_]+(?:[-.][A-Za-z0-9_]+){2,}", value):
        return True
    parts = [part.strip().casefold() for part in value.split("·")]
    return all(
        part in _GENERIC | _REPOS or re.fullmatch(r"(?:pr|issue|task)\s*#?\d+", part)
        for part in parts
    )


def validate_title_it(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("title_type")
    value = value.strip()
    if not 12 <= len(value) <= 180:
        raise ValueError("title_length")
    if (
        any(ord(char) < 32 or ord(char) == 127 for char in value)
        or value.startswith("#")
        or len(re.findall(r"[^\W_]+", value)) < 3
        or value.startswith(("http://", "https://"))
    ):
        raise ValueError("title_shape")
    if generic_title(value):
        raise ValueError("title_generic")
    return value


def meaningful_title(value: object) -> str:
    try:
        return validate_title_it(value)
    except ValueError:
        return ""


def note_title(note: dict[str, Any]) -> tuple[str, str]:
    for key in ("title_it", "title"):
        value = note.get(key)
        if isinstance(value, str) and value.strip():
            return key, value
    return "", ""
