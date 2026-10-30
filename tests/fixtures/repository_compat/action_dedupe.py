"""Synthetic dependencies around reviewed scope/matching function bodies."""

import hashlib
import json
from pathlib import Path

REPO_STEPS = ("promote", "release")


class ItemIndex:
    def get(self, item):
        return {}


def step_of(record, info):
    return record.get("intent", "")


def is_active(path, logs):
    return not path.with_suffix(".inactive").exists()


def scope_of(step: str, item: str, info: dict, rec: dict | None = None) -> str:
    if step in ("release_prepare", "deploy") and rec:
        snapshot = {key: rec.get(key) for key in ("project", "version", "base")}
        snapshot["candidates"] = sorted(
            rec.get("candidates", []), key=lambda c: json.dumps(c, sort_keys=True)
        )
        digest = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True).encode()
        ).hexdigest()
        return f"release:{rec.get('project', '')}:{rec.get('version', '')}:{digest}"
    repo = info.get("repo") or ""
    return f"repo:{repo}" if step in REPO_STEPS and repo else f"item:{item}"


def find_active(
    actions_dir: Path, logs: Path, index: ItemIndex, step: str, scope: str
) -> tuple[str, dict] | None:
    "Newest active action with the same step and scope: (file name, record) or None."
    if not step or not actions_dir.is_dir():
        return None
    for f in sorted(actions_dir.glob("*.json"), reverse=True):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        info = index.get(rec.get("item", ""))
        if (
            step_of(rec, info) != step
            or scope_of(step, rec.get("item", ""), info, rec) != scope
        ):
            continue
        if is_active(f, logs):
            return f.name, rec
    return None
