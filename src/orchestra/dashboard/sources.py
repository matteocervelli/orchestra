"""Canonical dashboard helpers, extracted from reviewed producer source."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .provenance import parse_task_provenance


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
