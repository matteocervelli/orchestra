"""Conservative issue → PR → root-task identities, independent of display text."""

from __future__ import annotations

import re
from typing import Any

from .common import FULL, refs, repository_authority, short_repo

SUFFIX = re.compile("-(?:fix\\d*|next\\d*|cx|impl|followup|review|unified)$")
URL = re.compile("https://github\\.com/(?:[\\w.-]+/)([\\w.-]+)/(issues|pull)/(\\d+)")
KEYWORD = re.compile(
    "(?i)\\b(PRs?|pull request|issues?|closes|fixes|resolv"
    "es|addresses|refs?)\\s+(?:([\\w.-]+(?:/[\\w.-]+)?)\\s*)?"
    "#(\\d+)"
)


def root_task(slug: str) -> str:
    previous = None
    while previous != slug:
        previous, slug = (slug, SUFFIX.sub("", slug))
    return slug


def card_ids(it: dict[Any, Any]) -> set[str]:
    """Canonical card and historical issue/PR identities, distinct from task parts."""
    return {it["id"]} | {
        a for a in it.get("aliases", []) if re.fullmatch("(?:issue|pr)-.+-\\d+", a)
    }


def repo_of(it: dict[Any, Any], notes: dict[Any, Any], tasks: dict[Any, Any]) -> str:
    repo = notes.get("repo") or it["repo"]
    if repo and repo != "orchestra":
        return short_repo(repo)
    for slug in it["slugs"]:
        text = tasks.get(slug, {}).get("text", "")
        m = re.search("/data/dev/(?:projects|services|libs)/([\\w.-]+)", text)
        if m:
            return short_repo(m[1].rstrip("."))
        mentioned = {r for r, _ in refs(text)} | {
            short_repo(m[1]) for m in URL.finditer(text)
        }
        if len(mentioned) == 1:
            return next(iter(mentioned))
        for name in sorted(set(FULL) | set(FULL.values()), key=len, reverse=True):
            if slug.startswith(
                (name + "-", "issue-" + name + "-", "review-" + name + "-")
            ):
                return short_repo(name)
    return short_repo(repo or "")


def explicit_refs(text: str, repo: str) -> dict[str, set[int]]:
    found: dict[str, set[int]] = {"issue": set(), "pr": set()}
    authority = repository_authority(repo)
    for m in KEYWORD.finditer(text or ""):
        if text[: m.start()].rstrip().lower().endswith("forgejo"):
            continue
        if (m[2] and (short_repo(m[2]) == repo or repo.endswith("-" + m[2]))) or (
            not m[2] and repo not in ("", "orchestra")
        ):
            found[
                "pr" if m[1].lower() in ("pr", "prs", "pull request") else "issue"
            ].add(int(m[3]))
    for m in URL.finditer(text or ""):
        if (
            short_repo(m[1]) == repo
            and authority
            and m[0].split("/")[3:5] == authority.split("/")
        ):
            found["issue" if m[2] == "issues" else "pr"].add(int(m[3]))
    return found


def identity(
    it: dict[str, Any],
    notes: dict[str, Any],
    tasks: dict[str, Any],
    pr_issues: dict[Any, Any],
    known_prs: set[Any] | None = None,
) -> tuple[str, int | None, int | None]:
    from .provenance import qualified_pr, resolve_work_provenance

    repo = repo_of(it, notes, tasks)
    asserted_repo = str(notes.get("repo") or it.get("repo") or "")
    if "/" in asserted_repo and not repository_authority(asserted_repo):
        return repo, None, None
    primary = qualified_pr(it.get("pr"), repo)
    declaration = resolve_work_provenance(
        notes, [tasks[s] for s in it.get("slugs", []) if s in tasks], {}
    )
    if declaration.get("validation") == "conflict":
        return repo, None, None
    declared_pr = declaration.get("subject", {}).get("pr")
    if (
        primary
        and declaration.get("validation") == "validated"
        and declaration.get("relation") == "primary"
        and (
            declaration.get("kind") == "local_artifact_review"
            or (declared_pr and qualified_pr(declared_pr, repo) != primary)
        )
    ):
        return repo, None, None
    if (
        not primary
        and declaration.get("validation") == "validated"
        and declaration.get("relation") == "primary"
        and declaration.get("kind") == "primary_integration"
    ):
        subject = declaration.get("subject", {})
        if subject.get("repo") == repo:
            primary = qualified_pr(subject.get("pr"), repo)
    pr = primary["number"] if primary and primary["host"] == "github.com" else None
    issue = None
    issue_ref = it.get("issue") or {}
    authority = repository_authority(repo)
    if type(issue_ref.get("number")) is int and isinstance(issue_ref.get("url"), str):
        parsed = URL.fullmatch(issue_ref["url"])
        if (
            parsed
            and parsed[2] == "issues"
            and short_repo(parsed[1]) == repo
            and int(parsed[3]) == issue_ref["number"]
            and authority
            and issue_ref["url"].split("/")[3:5] == authority.split("/")
        ):
            issue = issue_ref["number"]
    linked = pr_issues.get((repo, pr)) if pr else None
    if type(linked) is int and linked > 0:
        issue = issue or linked
    return repo, issue, pr


def groups(
    items: dict[str, Any],
    notes: dict[str, Any],
    tasks: dict[str, Any],
    pr_issues: dict[Any, Any],
) -> tuple[dict[str, list[str]], dict[str, tuple[str, int | None, int | None]]]:
    identities = {
        iid: identity(it, notes.get(iid, {}), tasks, pr_issues, set(pr_issues))
        for iid, it in items.items()
    }
    by_primary: dict[tuple[str, int | None, int | None], list[str]] = {}
    result: dict[str, list[str]] = {}
    for iid, ref in identities.items():
        if ref[1] or ref[2]:
            by_primary.setdefault(ref, []).append(iid)
        else:
            result[iid] = [iid]
    for ref, members in by_primary.items():
        protected = [
            iid
            for iid in members
            if notes.get(iid)
            or any(notes.get(a) for a in items[iid].get("aliases", []))
            or items[iid].get("approval")
            or items[iid].get("ask")
            or items[iid].get("steps")
        ]
        if len(protected) > 1:
            for iid in members:
                result[iid] = [iid]
            continue
        repo, issue, pr = ref
        canonical = f"issue-{repo}-{issue}" if issue else f"pr-{repo}-{pr}"
        # Keep a current key. An alias is not an exact-ID consumer redirect.
        anchor = (
            protected[0]
            if protected
            else canonical
            if canonical in members
            else min(members, key=lambda value: (len(value), value))
        )
        result[anchor] = members
    return result, identities
