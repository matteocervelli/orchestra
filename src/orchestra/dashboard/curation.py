"""Canonical dashboard helpers, extracted from reviewed producer source."""

from __future__ import annotations

import copy
from typing import Any

from .common import FULL, STATUSES
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
    for src in (card, note) if note.get("pin") else (note, card):
        for k in TEXT_KEYS:
            if isinstance(src.get(k), str) and (src.get(k) or k == "needs"):
                it[k] = src[k]
                curated.add(k)
        pages = src.get("pages")
        for k, v in (pages if isinstance(pages, dict) else {}).items():
            if (
                k == "preview"
                and isinstance(v, str)
                and (v or (src is note and note.get("pages_exact")))
            ):
                preview = v
            elif k in it["pages"] and (v or (src is note and note.get("pages_exact"))):
                if src is note and note.get("pages_exact"):
                    it["pages"][k] = []
                for link in v if isinstance(v, list) else [v]:
                    if link not in it["pages"][k]:
                        it["pages"][k].append(link)
        if isinstance(src.get("preview"), str) and src["preview"]:
            preview = src["preview"]
    edited = note.get("edited_fields")
    if isinstance(edited, list):
        for key in TEXT_KEYS:
            if key in edited and key in note and isinstance(note[key], str):
                it[key] = note[key]
                curated.add(key)
    key, protected = note_title(note)
    if key:
        it[key] = protected
        curated.add(key)
        if key == "title":
            it.pop("title_it", None)
            curated.discard("title_it")
    return (curated, preview)


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
    compute: Any,
    effective_note: Any,
    issue_ref: Any,
) -> dict[str, Any]:
    mapping, identities = groups(
        asm.items, notes, tasks, {r: asm.pr_issue(r) for r in asm.pr_by}
    )
    collapsed, effective = {}, dict(notes)
    for target, members in mapping.items():
        parts = [asm.items[i] for i in members]
        it = copy.deepcopy(parts[0])
        repo, issue, _ = identities[members[0]]
        real_aliases = unique(
            members
            + [s for part in parts for s in part["slugs"]]
            + [a for part in parts for a in part.get("aliases", [])]
            + [target]
        )
        proven = [
            pr
            for part in parts
            for pr in part.get("prs", [])
            if github_primary(pr, repo)
            and any((p.get("pr") or {}).get("url") == pr.get("url") for p in parts)
        ]
        pr_aliases = [
            alias
            for pr in proven
            if (alias := f"pr-{repo}-{pr['number']}") not in asm.items
            or alias in members
        ]
        aliases = unique(real_aliases + pr_aliases)
        note_aliases = unique(real_aliases + [a for a in pr_aliases if a in notes])
        if target not in notes and all(set(p["source"]) == {"pr"} for p in parts):
            # The issue id was derived from these PRs; it is not another visible source.
            note_aliases = [a for a in note_aliases if a != target]
        it["id"], it["aliases"] = target, aliases
        it["_note_aliases"] = note_aliases
        it["repo"] = FULL.get(repo, repo)
        if issue:
            it["issue"] = issue_ref(it["repo"], issue)
        else:
            it["issue"] = None
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
            rows = [v for part in parts for v in part.get(key, [])]
            it[key] = rows if key == "source" else unique(rows)
        it["updated"] = max(p["updated"] for p in parts)
        it["pages"] = {
            k: unique([v for p in parts for v in p["pages"][k]]) for k in it["pages"]
        }
        # Keep review/status attached to its proved primary PR.
        it["pr"] = next(
            (part.get("pr") for part in parts if github_primary(part.get("pr"), repo)),
            None,
        )
        candidates = []
        for pr in proven:
            candidate = {**it, "pr": pr, "review": pr.get("review"), "children": []}
            res = compute(candidate, it["outcomes"], asm.probes)
            candidates.append((res, pr))
        if candidates:
            real = [c for c in candidates if c[0]["status"] != "Dropped"] or candidates
            res, pr = max(
                real, key=lambda c: (STATUSES.index(c[0]["status"]), c[1]["number"])
            )
            it["pr"], it["review"] = pr, pr.get("review")
            it["branch"] = pr.get("branch", "")
        it["_deduped"] = (
            len(note_aliases) > 1
            or len(it["prs"]) > 1
            or any(a != target and a in notes for a in note_aliases)
        )
        if it["_deduped"]:
            effective[target] = effective_note(
                notes, note_aliases, target, it["children"]
            )
            it["_ask_overrides"] = effective[target].get("ask_overrides", [])
        collapsed[target] = it
    asm.items = collapsed
    return effective
