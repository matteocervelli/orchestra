"""Display ownership from explicit source assignments; citations are not owners."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from .common import FULL, REPOS, short_repo
from .provenance import qualified_pr

ALIASES = {
    **REPOS,
    "orchestra": "orchestra",
    "adlimen-infra": "adlimen-infra",
    "adlimen-cicd": "adlimen-cicd",
}
NAME = re.compile(
    r"(?<![\w-])(" + "|".join(sorted(ALIASES, key=len, reverse=True)) + r")(?![\w-])",
    re.I,
)
URL = re.compile(
    r"https://(?:github\.com|git\.adlimen\.dev)/[\w.-]+/([\w.-]+)/(?:pulls?|issues)/\d+",
    re.I,
)
REF = re.compile(
    r"(?<![\w-])(" + "|".join(sorted(ALIASES, key=len, reverse=True)) + r")\s*#\d+",
    re.I,
)
_PATH = r"/data/dev/(?:projects|services|libs)/([\w.-]+)(?:/\.worktrees/[\w./-]+)?/?"
_TOKEN = r"(?:[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*"
_COMMIT = r"[a-f0-9]{7,40}"
_QUOTED = re.compile(r"(`+)(.*?)\1|\"[^\"\n]*\"|'[^'\n]*'")
_STOP = re.compile(
    r"^(?:reference|read-only reference|dependency|example|quote|other owners?)\b"
    r"|^(?:do not|don't|no changes|nessun\w*|non modificare)\b",
    re.I,
)
_FIELD = re.compile(r"^(repos?|source target|worktree):\s*(.+)$", re.I)
_ASSIGNMENTS = (
    rf"(?:Same privacy author/isolated worktree|Authorized worktree is NEW|"
    rf"Canonical repo|Read-only app worktree:)\s+({_PATH})",
    rf"(?:Resume ONLY|Worktree)\s+({_PATH})(?:,.*)?",
    rf"Resume SAME\s+({_PATH})\s+after author terminal(?:,.*)?",
    rf"Source worktree\s+({_PATH});\s*HEAD\s+{_COMMIT}",
    rf"Review only committed source delta\s+{_COMMIT}\s+in your dedicated "
    rf"detached worktree\s+({_PATH})",
)
_SOURCE = tuple(re.compile(pattern, re.I) for pattern in _ASSIGNMENTS)
_NAMED = re.compile(
    r"(" + "|".join(re.escape(alias) for alias in ALIASES) + r"): "
    r"nuovo worktree dedicato sotto \.worktrees dalla [\w./-]+ corrente"
    r"(?:, verificando .+)?",
    re.I,
)


def canonical(value: object) -> str:
    if not isinstance(value, str):
        return ""
    name = value.strip().lower()
    if re.fullmatch(r"[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*", name):
        name = name.split("/")[-1]
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,99}", name):
        return ""
    return FULL.get(short_repo(name), name)


def clean(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(r for v in values if (r := canonical(v))))


def reference_repos(text: str) -> list[str]:
    """Preserve the donor citation API, independently of display ownership."""
    hits = sorted([(m.start(), m[1]) for rx in (URL, REF) for m in rx.finditer(text)])
    return clean([name for _, name in hits])


def _mask_quote(match: re.Match[str]) -> str:
    # A backtick-wrapped value may fill a declared field, never start a clause.
    if match[1] and re.fullmatch(r"[/\w.-]+", match[2]):
        return match[0]
    return "\x00"


def _clauses(text: str) -> Iterator[str]:
    """Only line/sentence starts; quoted and excluded tails cannot start scope."""
    fence = ""
    for line in text.splitlines():
        line = line.strip()
        marker = re.match(r"(`{3,}|~{3,})", line)
        if marker:
            if not fence:
                fence = marker[1]
            elif (
                marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence)
                and not line[marker.end() :].strip()
            ):
                fence = ""
            continue
        if fence or line.startswith(">"):
            continue
        line = re.sub(r"^(?:[-*+] |\d+[.)] )", "", line)
        line = _QUOTED.sub(_mask_quote, line)
        for clause in re.split(r"(?<=[.!?])\s+", line):
            clause = clause.strip().removesuffix(".").strip()
            if _STOP.match(clause):
                break
            if clause:
                yield clause


def _repo_value(value: str, *, path_only: bool = False) -> str:
    if value.startswith("`") and value.endswith("`"):
        value = value.strip("`")
    if match := re.fullmatch(_PATH, value):
        if any(part in {".", ".."} for part in value.split("/")):
            return ""
        return canonical(match[1])
    return (
        canonical(value) if not path_only and re.fullmatch(_TOKEN, value, re.I) else ""
    )


def _assignment(clause: str) -> list[str]:
    if field := _FIELD.fullmatch(clause):
        values = [part.strip() for part in field[2].split(",")]
        repos = [
            _repo_value(value, path_only=field[1].lower() == "worktree")
            for value in values
        ]
        # Only Repo(s) declares several targets. A malformed value fails closed.
        if not all(repos) or (
            len(repos) != 1 and field[1].lower() not in {"repo", "repos"}
        ):
            return []
        return clean(repos)
    for pattern in _SOURCE:
        if match := pattern.fullmatch(clause):
            return clean([_repo_value(match[1], path_only=True)])
    if named := _NAMED.fullmatch(clause):
        return clean([named[1]])
    return []


def task_repos(text: str) -> list[str]:
    """Recognize bounded affirmative assignments, never arbitrary names/paths."""
    return clean([repo for clause in _clauses(text) for repo in _assignment(clause)])


def _primary_repo(raw: object) -> list[str]:
    if not isinstance(raw, dict) or not isinstance(raw.get("url"), str):
        return []
    candidates = reference_repos(raw["url"])
    return [repo for repo in candidates if qualified_pr(raw, repo)]


def derive(
    it: dict[str, Any],
    card: dict[str, Any],
    note: dict[str, Any],
    tasks: dict[str, Any],
    spawns: dict[str, Any],
    ledger: list[dict[str, Any]],
) -> list[str]:
    """Keep explicit display declarations; UNKNOWN is an empty ordered list."""
    del spawns, ledger  # Legacy call signature, not ownership evidence.
    declared = next(
        (
            repos
            for child in reversed(
                sorted(it.get("children", []), key=lambda c: c["start"])
            )
            if (repos := clean((child.get("card") or {}).get("repos")))
        ),
        [],
    )
    declared = declared or clean(card.get("repos")) or clean(note.get("repos"))
    declared = declared or clean([card.get("repo") or note.get("repo")])
    if declared:
        return declared
    if primary := _primary_repo(it.get("pr")):
        return primary
    return clean(
        [
            repo
            for slug in it.get("slugs", [])
            for repo in task_repos(tasks.get(slug, {}).get("text", ""))
        ]
    )
