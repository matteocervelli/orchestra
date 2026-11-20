"""Canonical dashboard helpers, extracted from reviewed producer source."""

from __future__ import annotations

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


@contextmanager
def notes_lock(root: Path) -> Iterator[None]:
    with (root / ".workitems-notes.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def ensure_title_it(root: Path, item_id: str, title_it: object, phase: str) -> str:
    """Write one missing title under the shared lock; never overwrite note content."""
    import re

    from .titles import note_title, validate_title_it

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", item_id):
        raise ValueError("item_id")
    if phase not in ("start", "complete"):
        raise ValueError("phase")
    title = validate_title_it(title_it)
    with notes_lock(root):
        path = root / "workitems-notes.json"
        data, note = _read_note_for_title(path, item_id)
        if note_title(note)[0]:
            return "preserved"
        data[item_id] = {**note, "title_it": title}
        _replace_notes(path, root, data)
    return "written"


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Admit one explicit dashboard title")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--item", required=True)
    parser.add_argument("--title-it", required=True)
    parser.add_argument("--phase", choices=("start", "complete"), required=True)
    args = parser.parse_args()
    print(ensure_title_it(args.root, args.item, args.title_it, args.phase))
    return 0


def _read_note_for_title(
    path: Path, item_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("notes_root")
    note = data.get(item_id, {})
    if not isinstance(note, dict):
        raise ValueError("notes_item")
    for key in ("title_it", "title"):
        if key in note and not isinstance(note[key], str):
            raise ValueError("notes_title_type")
    return data, note


def _replace_notes(path: Path, root: Path, data: dict[str, Any]) -> None:
    import json
    import os
    import tempfile

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=".notes-title-", dir=root, delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
