"""Canonical dashboard helpers, extracted from reviewed producer source."""

from __future__ import annotations

import copy
from typing import Any

from .common import FULL, STATUSES
from .history import HistoricalBindings, protected_values
from .identity import groups
from .provenance import github_primary
from .titles import note_title

TEXT_KEYS = ("problem", "solution", "needs", "title", "kind", "repo", "title_it")


def curate(
    it: dict[Any, Any], note: dict[Any, Any], card: dict[Any, Any]
) -> tuple[set[str], str]:
    """Apply text/pages, protecting either note title independently of pin."""
    curated: set[str] = set()
    preview = ""
    for source in (card, note) if note.get("pin") else (note, card):
        _apply_text_fields(it, source, curated)
        preview = _apply_pages(it, source, note, preview)
    _apply_edited_text(it, note, curated)
    key, protected = note_title(note)
    if key:
        it[key] = protected
        curated.add(key)
        if key == "title":
            it.pop("title_it", None)
            curated.discard("title_it")
    return curated, preview


def unique(rows: list[Any]) -> list[Any]:
    out = []
    for row in rows:
        if row not in out:
            out.append(row)
    return out


def collapse(
    asm: Any,
    notes: dict[str, Any],
    tasks: dict[str, Any],
    *,
    historical_bindings: HistoricalBindings | None = None,
    compute: Any,
    effective_note: Any,
    issue_ref: Any,
) -> dict[str, Any]:
    mapping, identities = groups(
        asm.items,
        notes,
        tasks,
        {ref: asm.pr_issue(ref) for ref in asm.pr_by},
        historical_bindings=historical_bindings,
    )
    collapsed, effective = {}, dict(notes)
    for target, members in mapping.items():
        collapsed[target] = _collapse_group(
            asm,
            notes,
            target,
            members,
            identities[members[0]],
            effective,
            compute=compute,
            effective_note=effective_note,
            issue_ref=issue_ref,
            historical=historical_bindings is not None,
        )
        if historical_bindings is not None:
            collapsed[target].update(
                copy.deepcopy(
                    protected_values([asm.items[iid] for iid in members], target)
                )
            )
    asm.items = collapsed
    return effective


def _apply_text_fields(
    it: dict[Any, Any], source: dict[Any, Any], curated: set[str]
) -> None:
    for key in TEXT_KEYS:
        if isinstance(source.get(key), str) and (source.get(key) or key == "needs"):
            it[key] = source[key]
            curated.add(key)


def _page_value_applies(
    value: Any, source: dict[Any, Any], note: dict[Any, Any]
) -> bool:
    return bool(value or (source is note and note.get("pages_exact")))


def _apply_pages(
    it: dict[Any, Any], source: dict[Any, Any], note: dict[Any, Any], preview: str
) -> str:
    pages = source.get("pages")
    for key, value in (pages if isinstance(pages, dict) else {}).items():
        if (
            key == "preview"
            and isinstance(value, str)
            and _page_value_applies(value, source, note)
        ):
            preview = value
        elif key in it["pages"] and _page_value_applies(value, source, note):
            _merge_page_links(it, key, value, source, note)
    if isinstance(source.get("preview"), str) and source["preview"]:
        preview = source["preview"]
    return preview


def _merge_page_links(
    it: dict[Any, Any],
    key: str,
    value: Any,
    source: dict[Any, Any],
    note: dict[Any, Any],
) -> None:
    if source is note and note.get("pages_exact"):
        it["pages"][key] = []
    for link in value if isinstance(value, list) else [value]:
        if link not in it["pages"][key]:
            it["pages"][key].append(link)


def _apply_edited_text(
    it: dict[Any, Any], note: dict[Any, Any], curated: set[str]
) -> None:
    edited = note.get("edited_fields")
    if isinstance(edited, list):
        for key in TEXT_KEYS:
            if key in edited and key in note and isinstance(note[key], str):
                it[key] = note[key]
                curated.add(key)


def _real_aliases(
    parts: list[dict[str, Any]], members: list[str], target: str
) -> list[str]:
    return unique(
        members
        + [slug for part in parts for slug in part["slugs"]]
        + [alias for part in parts for alias in part.get("aliases", [])]
        + [target]
    )


def _proven_prs(parts: list[dict[str, Any]], repo: str) -> list[dict[str, Any]]:
    return [
        pr
        for part in parts
        for pr in part.get("prs", [])
        if github_primary(pr, repo)
        and any(
            (candidate.get("pr") or {}).get("url") == pr.get("url")
            for candidate in parts
        )
    ]


def _primary_aliases(
    proven: list[dict[str, Any]], asm: Any, members: list[str], repo: str
) -> list[str]:
    return [
        alias
        for pr in proven
        if (alias := f"pr-{repo}-{pr['number']}") not in asm.items or alias in members
    ]


def _note_aliases(
    real: list[str],
    primary: list[str],
    parts: list[dict[str, Any]],
    target: str,
    notes: dict[str, Any],
) -> list[str]:
    aliases = unique(real + [alias for alias in primary if alias in notes])
    if target not in notes and all(set(part["source"]) == {"pr"} for part in parts):
        aliases = [alias for alias in aliases if alias != target]
    return aliases


def _merge_part_rows(it: dict[str, Any], parts: list[dict[str, Any]]) -> None:
    for key in (
        "children",
        "slugs",
        "labels",
        "source",
        "outcomes",
        "decisions",
        "_reftext",
        "prs",
        "reviews",
    ):
        rows = [value for part in parts for value in part.get(key, [])]
        it[key] = rows if key == "source" else unique(rows)
    it["updated"] = max(part["updated"] for part in parts)
    it["pages"] = _merged_part_pages(parts, it["pages"])


def _merged_part_pages(
    parts: list[dict[str, Any]], pages: dict[str, Any]
) -> dict[str, Any]:
    return {
        key: unique([value for part in parts for value in part["pages"][key]])
        for key in pages
    }


def _assign_primary(
    it: dict[str, Any],
    parts: list[dict[str, Any]],
    proven: list[dict[str, Any]],
    repo: str,
    compute: Any,
    probes: Any,
) -> None:
    it["pr"] = next(
        (part.get("pr") for part in parts if github_primary(part.get("pr"), repo)), None
    )
    candidates = []
    for pr in proven:
        candidate = {**it, "pr": pr, "review": pr.get("review"), "children": []}
        candidates.append((compute(candidate, it["outcomes"], probes), pr))
    if candidates:
        _, pr = _winning_primary(candidates)
        it["pr"], it["review"] = pr, pr.get("review")
        it["branch"] = pr.get("branch", "")


def _winning_primary(
    candidates: list[tuple[Any, dict[str, Any]]],
) -> tuple[Any, dict[str, Any]]:
    real = [
        candidate for candidate in candidates if candidate[0]["status"] != "Dropped"
    ] or candidates
    return max(
        real,
        key=lambda candidate: (
            STATUSES.index(candidate[0]["status"]),
            candidate[1]["number"],
        ),
    )


def _finish_collapse_notes(
    it: dict[str, Any],
    aliases: list[str],
    target: str,
    notes: dict[str, Any],
    effective: dict[str, Any],
    effective_note: Any,
) -> None:
    it["_deduped"] = (
        len(aliases) > 1
        or len(it["prs"]) > 1
        or any(alias != target and alias in notes for alias in aliases)
    )
    if it["_deduped"]:
        effective[target] = effective_note(notes, aliases, target, it["children"])
        it["_ask_overrides"] = effective[target].get("ask_overrides", [])


def _collapse_group(
    asm: Any,
    notes: dict[str, Any],
    target: str,
    members: list[str],
    ref: tuple[str, int | None, int | None],
    effective: dict[str, Any],
    *,
    compute: Any,
    effective_note: Any,
    issue_ref: Any,
    historical: bool = False,
) -> dict[str, Any]:
    parts = [asm.items[iid] for iid in members]
    it: dict[str, Any] = copy.deepcopy(parts[0])
    repo, issue, _ = ref
    real = _real_aliases(parts, members, target)
    proven = _proven_prs(parts, repo)
    primary = [] if historical else _primary_aliases(proven, asm, members, repo)
    aliases = real if historical else _note_aliases(real, primary, parts, target, notes)
    it["id"], it["aliases"] = target, unique(real + primary)
    it["_note_aliases"] = aliases
    it["repo"] = FULL.get(repo, repo)
    it["issue"] = issue_ref(it["repo"], issue) if issue and not historical else None
    _merge_part_rows(it, parts)
    if not historical:
        _assign_primary(it, parts, proven, repo, compute, asm.probes)
    _finish_collapse_notes(it, aliases, target, notes, effective, effective_note)
    return it
