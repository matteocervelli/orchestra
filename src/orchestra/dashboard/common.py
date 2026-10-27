"""Canonical dashboard helpers, extracted from reviewed producer source."""

from __future__ import annotations

import re

REPOS = {
    "app-himalaia": "himalaia",
    "himalaia": "himalaia",
    "app-ratio": "ratio",
    "ratio": "ratio",
    "adlimen-ui": "adlimenui",
    "adlimenui": "adlimenui",
    "claude-dotfiles": "dotfiles",
    "dotfiles": "dotfiles",
    "nexus": "nexus",
    "atrium": "atrium",
}
FULL = {
    "himalaia": "app-himalaia",
    "ratio": "app-ratio",
    "adlimenui": "adlimen-ui",
    "dotfiles": "claude-dotfiles",
    "nexus": "nexus",
    "atrium": "atrium",
}
REF_RE = re.compile(
    "(?:\\b(" + "|".join(sorted(REPOS, key=len, reverse=True)) + ")\\s?)?#(\\d+)"
)


def short_repo(name: str) -> str:
    return REPOS.get(name.split("/")[-1], name.split("/")[-1])


def refs(
    text: str, pr_prefix: bool = False, default: str | None = None
) -> list[tuple[str, int]]:
    """Read references; unqualified numbers inherit prior context or default."""
    out: list[tuple[str, int]] = []
    last = default
    for m in REF_RE.finditer(text or ""):
        repo = short_repo(m.group(1)) if m.group(1) else last
        if not repo:
            continue
        last = repo
        if pr_prefix and (
            not re.search("\\bPR\\s*$", text[max(0, m.start() - 4) : m.start()])
        ):
            continue
        out.append((repo, int(m.group(2))))
    return out


STATUSES = [
    "Backlog",
    "Doing",
    "PR review",
    "PR fix",
    "Merge",
    "Integration",
    "Main",
    "Deployed",
    "Dropped",
]
CLOSED = ("Integration", "Main", "Deployed", "Dropped")


def repository_authority(repo: str) -> str | None:
    """Known repo aliases assert only the configured owner's repository."""
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return repo if owner == "matteocervelli" and name in FULL.values() else None
    short = short_repo(repo)
    return "matteocervelli/" + FULL[short] if short in FULL else None
