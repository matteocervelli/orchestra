"""Explicit historical source ownership; no storage, inference or runtime I/O."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

from .common import short_repo
from .provenance import qualified_pr

HistoricalBindings = Sequence[Mapping[str, str]]
PROTECTED = (
    "ask",
    "steps",
    "approval",
    "pin",
    "hide",
    "status",
    "priority",
    "answers",
    "pr",
    "issue",
    "branch",
    "review",
)
SAFE_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class HistoricalBindingConflict(ValueError):
    """Activation-blocking ownership evidence, available without parsing text."""

    def __init__(self, reason: str, source: str, owners: Sequence[str] = ()) -> None:
        self.reason = reason
        self.source = source
        self.owners = tuple(sorted(set(owners)))
        super().__init__(f"{reason}: {source}; owners={self.owners!r}")


def _safe_key(value: object, limit: int) -> bool:
    return bool(
        isinstance(value, str) and len(value) <= limit and SAFE_KEY.fullmatch(value)
    )


def _pr_key(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 4 or not parts[3].isdigit():
            return False
        reference = qualified_pr(
            {"url": value, "number": int(parts[3])}, short_repo(parts[1])
        )
        return bool(reference and reference["url"] == value)
    except ValueError:
        return False


def _record(record: object) -> tuple[tuple[str, str], str]:
    if not isinstance(record, Mapping) or set(record) != {"kind", "key", "owner"}:
        raise HistoricalBindingConflict("invalid binding schema", "binding")
    kind, key, owner = (record[k] for k in ("kind", "key", "owner"))
    if not isinstance(key, str) or not _safe_key(owner, 64):
        raise HistoricalBindingConflict("invalid binding key/owner", "binding")
    valid = (kind == "task" and _safe_key(key, 200)) or (kind == "pr" and _pr_key(key))
    if not valid:
        raise HistoricalBindingConflict("invalid source key", key)
    return (kind, key), owner


def _registry(bindings: HistoricalBindings) -> dict[tuple[str, str], str]:
    registry: dict[tuple[str, str], str] = {}
    for record in bindings:
        key, owner = _record(record)
        old = registry.get(key)
        if old is not None and old != owner:
            raise HistoricalBindingConflict(
                "source has multiple owners", str(key), [old, owner]
            )
        registry[key] = owner
    return registry


def _source_keys(item: dict[str, Any]) -> list[tuple[str, str]]:
    keys = [("task", slug) for slug in item.get("slugs", [])]
    pr = qualified_pr(item.get("pr"), item.get("repo", ""))
    if pr:
        keys.append(("pr", pr["url"]))
    return keys


def _owner(iid: str, item: dict[str, Any], registry: dict[tuple[str, str], str]) -> str:
    owners = {registry[key] for key in _source_keys(item) if key in registry}
    if len(owners) > 1:
        raise HistoricalBindingConflict(
            "raw source has multiple owners", iid, sorted(owners)
        )
    return next(iter(owners), iid)


def historical_groups(
    items: dict[str, Any], bindings: HistoricalBindings
) -> dict[str, list[str]]:
    registry = _registry(bindings)
    result: dict[str, list[str]] = {}
    for iid, item in items.items():
        result.setdefault(_owner(iid, item, registry), []).append(iid)
    for target, members in result.items():
        if target in items and target not in members:
            raise HistoricalBindingConflict(
                "target occupied by another source", target, members
            )
        for iid in members:
            if (
                iid == target
                and len(members) > 1
                and not any(key in registry for key in _source_keys(items[iid]))
            ):
                # A matching raw ID is not itself evidence of source ownership.
                raise HistoricalBindingConflict(
                    "unbound target collision", target, members
                )
    return result


def protected_values(parts: list[dict[str, Any]], target: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key in PROTECTED:
        present = [
            part[key]
            for part in parts
            if key in part and part[key] not in (None, "", [], {})
        ]
        if present and any(value != present[0] for value in present[1:]):
            raise HistoricalBindingConflict(
                "conflicting protected field", f"{target}.{key}"
            )
        if present:
            values[key] = present[0]
    return values


def validate_primaries(
    mapping: dict[str, list[str]],
    items: dict[str, Any],
    primary_of: Callable[[str, str], tuple[dict[str, Any] | None, bool]],
) -> None:
    for target, members in mapping.items():
        primaries = []
        for iid in members:
            primary, conflict = primary_of(iid, target)
            if conflict:
                raise HistoricalBindingConflict(
                    "conflicting primary evidence", iid, [target]
                )
            if primary and primary not in primaries:
                primaries.append(primary)
        if len(primaries) > 1:
            raise HistoricalBindingConflict(
                "owner has different primary references", target, members
            )
        protected_values([items[iid] for iid in members], target)


def validate_note_owners(
    mapping: dict[str, list[str]], items: dict[str, Any], notes: dict[str, Any]
) -> None:
    for target, members in mapping.items():
        for iid in members:
            for alias in items[iid].get("aliases", []):
                if alias in notes and alias not in [target, *members]:
                    raise HistoricalBindingConflict(
                        "alias belongs to another curated owner", alias, [target, alias]
                    )
