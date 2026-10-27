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
        candidate = _repo_from_task(slug, tasks.get(slug, {}).get("text", ""))
        if candidate is not None:
            return candidate
    return short_repo(repo or "")


def explicit_refs(text: str, repo: str) -> dict[str, set[int]]:
    found = _keyword_refs(text, repo)
    for kind, numbers in _url_refs(text, repo).items():
        found[kind].update(numbers)
    return found


def identity(
    it: dict[str, Any],
    notes: dict[str, Any],
    tasks: dict[str, Any],
    pr_issues: dict[Any, Any],
    known_prs: set[Any] | None = None,
) -> tuple[str, int | None, int | None]:
    """Resolve qualified evidence; known_prs remains a discarded legacy argument."""
    del known_prs
    repo = repo_of(it, notes, tasks)
    asserted_repo = str(notes.get("repo") or it.get("repo") or "")
    if "/" in asserted_repo and not repository_authority(asserted_repo):
        return repo, None, None
    primary, conflict = _primary_reference(it, notes, tasks, repo)
    if conflict:
        return repo, None, None
    pr = primary["number"] if primary and primary["host"] == "github.com" else None
    issue = _issue_for_primary(it, repo, pr, pr_issues)
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
        anchor = _group_anchor(ref, members, items, notes)
        if anchor is None:
            for iid in members:
                result[iid] = [iid]
        else:
            result[anchor] = members
    return result, identities


def _repo_from_task(slug: str, text: str) -> str | None:
    path = re.search(r"/data/dev/(?:projects|services|libs)/([\w.-]+)", text)
    if path:
        return short_repo(path[1].rstrip("."))
    mentioned = {repo for repo, _ in refs(text)} | {
        short_repo(match[1]) for match in URL.finditer(text)
    }
    if len(mentioned) == 1:
        return next(iter(mentioned))
    return _slug_repo(slug)


def _slug_repo(slug: str) -> str | None:
    for name in sorted(set(FULL) | set(FULL.values()), key=len, reverse=True):
        if slug.startswith((name + "-", "issue-" + name + "-", "review-" + name + "-")):
            return short_repo(name)
    return None


def _keyword_repo_matches(match: re.Match[str], repo: str) -> bool:
    return bool(
        (match[2] and (short_repo(match[2]) == repo or repo.endswith("-" + match[2])))
        or (not match[2] and repo not in ("", "orchestra"))
    )


def _keyword_refs(text: str, repo: str) -> dict[str, set[int]]:
    found: dict[str, set[int]] = {"issue": set(), "pr": set()}
    for match in KEYWORD.finditer(text or ""):
        if text[: match.start()].rstrip().lower().endswith("forgejo"):
            continue
        if _keyword_repo_matches(match, repo):
            kind = (
                "pr" if match[1].lower() in ("pr", "prs", "pull request") else "issue"
            )
            found[kind].add(int(match[3]))
    return found


def _url_refs(text: str, repo: str) -> dict[str, set[int]]:
    found: dict[str, set[int]] = {"issue": set(), "pr": set()}
    authority = repository_authority(repo)
    for match in URL.finditer(text or ""):
        if (
            short_repo(match[1]) == repo
            and authority
            and match[0].split("/")[3:5] == authority.split("/")
        ):
            found["issue" if match[2] == "issues" else "pr"].add(int(match[3]))
    return found


def _primary_reference(
    it: dict[str, Any], notes: dict[str, Any], tasks: dict[str, Any], repo: str
) -> tuple[dict[str, Any] | None, bool]:
    from .provenance import qualified_pr, resolve_work_provenance

    primary = qualified_pr(it.get("pr"), repo)
    declaration = resolve_work_provenance(
        notes, [tasks[slug] for slug in it.get("slugs", []) if slug in tasks], {}
    )
    if declaration.get("validation") == "conflict" or _primary_conflict(
        primary, declaration, repo
    ):
        return None, True
    if not primary:
        primary = _declared_primary(declaration, repo)
    return primary, False


def _primary_conflict(
    primary: dict[str, Any] | None, declaration: dict[str, Any], repo: str
) -> bool:
    from .provenance import qualified_pr

    declared = declaration.get("subject", {}).get("pr")
    return bool(
        primary
        and declaration.get("validation") == "validated"
        and declaration.get("relation") == "primary"
        and (
            declaration.get("kind") == "local_artifact_review"
            or (declared and qualified_pr(declared, repo) != primary)
        )
    )


def _declared_primary(declaration: dict[str, Any], repo: str) -> dict[str, Any] | None:
    from .provenance import qualified_pr

    if (
        declaration.get("validation"),
        declaration.get("relation"),
        declaration.get("kind"),
    ) != ("validated", "primary", "primary_integration"):
        return None
    subject = declaration.get("subject", {})
    return (
        qualified_pr(subject.get("pr"), repo) if subject.get("repo") == repo else None
    )


def _issue_for_primary(
    it: dict[str, Any], repo: str, pr: int | None, pr_issues: dict[Any, Any]
) -> int | None:
    reference = it.get("issue") or {}
    issue = None
    if (
        type(reference.get("number")) is int
        and isinstance(reference.get("url"), str)
        and _same_repo_issue_url(reference["url"], repo, reference["number"])
    ):
        issue = reference["number"]
    linked = pr_issues.get((repo, pr)) if pr else None
    if type(linked) is int and linked > 0:
        issue = issue or linked
    return issue


def _same_repo_issue_url(url: str, repo: str, number: int) -> bool:
    parsed = URL.fullmatch(url)
    authority = repository_authority(repo)
    return bool(
        parsed
        and parsed[2] == "issues"
        and short_repo(parsed[1]) == repo
        and int(parsed[3]) == number
        and authority
        and url.split("/")[3:5] == authority.split("/")
    )


def _protected_member(iid: str, item: dict[str, Any], notes: dict[str, Any]) -> bool:
    return bool(
        notes.get(iid)
        or any(notes.get(alias) for alias in item.get("aliases", []))
        or item.get("approval")
        or item.get("ask")
        or item.get("steps")
    )


def _group_anchor(
    ref: tuple[str, int | None, int | None],
    members: list[str],
    items: dict[str, Any],
    notes: dict[str, Any],
) -> str | None:
    protected = [iid for iid in members if _protected_member(iid, items[iid], notes)]
    if len(protected) > 1:
        return None
    repo, issue, pr = ref
    canonical = f"issue-{repo}-{issue}" if issue else f"pr-{repo}-{pr}"
    return (
        protected[0]
        if protected
        else canonical
        if canonical in members
        else min(members, key=lambda value: (len(value), value))
    )
