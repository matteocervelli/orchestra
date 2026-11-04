"""Bounded authored PR descriptions; pure text evidence, never delivery proof."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .common import repository_authority
from .provenance import qualified_pr

FIELDS = ("problem", "solution")
ATTRIBUTION = "Descrizione PR (testo dell'autore):\n"
MISSING = {
    "problem": "Descrizione del problema non disponibile dalla PR primaria.",
    "solution": "Descrizione della soluzione non disponibile dalla PR primaria.",
}
_HEADINGS = {
    "problem": "problem",
    "problema": "problem",
    "solution": "solution",
    "soluzione": "solution",
    "summary": "summary",
}
_SENSITIVE = re.compile(
    r"(?im)(?:\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b|"
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"sk-[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16})\b|"
    r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|"
    r"\b(?:authorization|proxy-authorization|cookie|set-cookie)\s*[:=]|"
    r"\b[A-Z0-9_-]*(?:password|passwd|secret|secret[_-]?key|access[_-]?key|"
    r"access[_-]?token|api[_-]?key|auth[_-]?token|token)[\"']?\s*[:=]|"
    r"\bbearer[ \t]+\S+|(?-i:\b[A-Z_][A-Z0-9_]{2,})\s*=)"
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _head(row: dict[Any, Any]) -> object:
    head = row.get("head")
    return (
        row.get("head_sha")
        or row.get("headRefOid")
        or (head.get("sha") if isinstance(head, dict) else None)
    )


def _source_matches(
    row: dict[Any, Any], primary: dict[str, Any], repo: str, head: object
) -> bool:
    repository = row.get("repository")
    if not isinstance(repository, dict):
        return False
    if (
        repository.get("nameWithOwner") != primary["repo"]
        or repository.get("name") != primary["repo"].split("/")[1]
    ):
        return False
    other = _head(row)
    return bool(
        qualified_pr(row, repo) == primary and not (head and other and head != other)
    )


def _matching_rows(
    sources: list[dict[Any, Any]], primary: dict[str, Any]
) -> list[dict[Any, Any]]:
    return [
        row
        for row in sources
        if isinstance(row, dict)
        and (
            row.get("url") == primary["url"]
            or (
                row.get("number") == primary["number"]
                and _same_repository(row, primary)
            )
        )
    ]


def _same_repository(row: dict[Any, Any], primary: dict[str, Any]) -> bool:
    repository = row.get("repository")
    if not isinstance(repository, dict):
        return False
    name = repository.get("nameWithOwner", repository.get("name"))
    return isinstance(name, str) and repository_authority(name) == primary["repo"]


def _unique_body(
    rows: list[dict[Any, Any]], primary: dict[str, Any], repo: str, head: object
) -> str | None:
    bodies: set[str] = set()
    heads: set[str] = set()
    for row in rows:
        if not _source_matches(row, primary, repo, head):
            return None
        right = _head(row)
        if right:
            if not isinstance(right, str):
                return None
            heads.add(right)
        body = row.get("body")
        if body is None:
            continue
        if not isinstance(body, str) or not _bounded_body(body):
            return None
        bodies.add(body)
    return next(iter(bodies)) if len(bodies) == 1 and len(heads) <= 1 else None


def _source_body(item: dict[Any, Any], sources: list[dict[Any, Any]]) -> str | None:
    repo = item.get("repo")
    if not isinstance(repo, str) or len(sources) > 4096:
        return None
    primary = qualified_pr(item.get("pr"), repo)
    if primary is None:
        return None
    # A malformed duplicate of this very primary must not silently lose.
    return _unique_body(
        _matching_rows(sources, primary), primary, repo, _head(item["pr"])
    )


def _bounded_body(body: str) -> bool:
    if len(body) > 65536:
        return False
    if re.search(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", body.replace("\r\n", "\n")):
        return False
    try:
        return len(body.encode("utf-8")) <= 65536
    except UnicodeEncodeError:
        return False


def _unsafe_section(value: str) -> bool:
    return bool(
        _SENSITIVE.search(value)
        or re.search(r"(?m)^\s*(?:`{3,}|~{3,})|<[/!A-Za-z]", value)
        or any(ord(char) < 32 and char not in "\n\t" for char in value)
        or re.search(r"[\x7f-\x9f\u200e\u200f\u202a-\u202e\u2066-\u2069]", value)
    )


def _next_fence(line: str, fence: str) -> str:
    marker = re.match(r"^(`{3,}|~{3,})", line.lstrip())
    if not marker:
        return fence
    run = marker.group(1)
    if not fence:
        return run
    return "" if run[0] == fence[0] and len(run) >= len(fence) else fence


def _markdown_sections(body: str) -> dict[str, set[str]] | None:
    sections: dict[str, set[str]] = {}
    current: str | None = None
    lines: list[str] = []
    fence = ""
    for line in [*body.replace("\r\n", "\n").split("\n"), "## "]:
        fence = _next_fence(line, fence)
        heading = (
            re.fullmatch(r"##[ \t]+([^ \t].*)?", line.rstrip()) if not fence else None
        )
        # Any top-level heading ends an H2 section, even unsupported headings.
        boundary = not fence and re.match(r"^#{1,2}(?:[ \t]|$)", line)
        if boundary:
            if current:
                value = "\n".join(lines).strip()
                sections.setdefault(current, set()).add(value)
            current = (
                _HEADINGS.get((heading.group(1) or "").casefold()) if heading else None
            )
            lines = []
        elif current:
            lines.append(line)
    return None if fence else sections


def _sections(body: str) -> dict[str, str] | None:
    sections = _markdown_sections(body)
    if sections is None:
        return None
    selected = {
        "problem": "problem",
        "solution": "solution" if "solution" in sections else "summary",
    }
    out = {}
    for field, key in selected.items():
        values = sections.get(key, set())
        if len(values) > 1:
            return None
        value = next(iter(values), "")
        if value:
            if len(value) > 1200 or _unsafe_section(value):
                return None
            out[field] = value
    return out


def recover_descriptions(
    item: dict[Any, Any], source_prs: list[dict[Any, Any]]
) -> dict[str, str] | None:
    """Return only explicit bounded sections plus the non-reversible body digest."""
    body = _source_body(item, source_prs)
    if body is None:
        return None
    sections = _sections(body)
    return {**sections, "body_sha256": _sha(body)} if sections else None


def technical_fallback(item: dict[Any, Any], field: str) -> bool:
    pr = item.get("pr")
    title = pr.get("title") if isinstance(pr, dict) else None
    return bool(isinstance(title, str) and title.strip() and item.get(field) == title)


def _provenance_record(raw: object, value: object) -> bool:
    if not isinstance(raw, dict) or set(raw) != {"url", "field_sha256", "body_sha256"}:
        return False
    if not isinstance(value, str) or not value.startswith(ATTRIBUTION):
        return False
    return bool(
        raw["field_sha256"] == _sha(value)
        and isinstance(raw["body_sha256"], str)
        and re.fullmatch(r"[a-f0-9]{64}", raw["body_sha256"])
    )


def valid_description_provenance(item: dict[Any, Any], field: str) -> bool:
    provenance = item.get("description_provenance")
    if not isinstance(provenance, dict):
        return False
    raw = provenance.get(field)
    if not isinstance(raw, dict) or not _provenance_record(raw, item.get(field)):
        return False
    primary = qualified_pr(item.get("pr"), str(item.get("repo") or ""))
    return bool(primary and raw["url"] == primary["url"])


def _retained_provenance(item: dict[Any, Any], curated: set[str]) -> dict[str, Any]:
    existing = item.get("description_provenance")
    if not isinstance(existing, dict):
        return {}
    return {
        field: existing[field]
        for field in FIELDS
        if field not in curated and valid_description_provenance(item, field)
    }


def _eligible(item: dict[Any, Any], curated: set[str], field: str) -> bool:
    return field not in curated and (
        not str(item.get(field) or "").strip() or technical_fallback(item, field)
    )


def fill_descriptions(
    item: dict[Any, Any], curated: set[str], source_prs: list[dict[Any, Any]]
) -> set[str]:
    """Recover after curation, with provenance tied to the final selected text."""
    retained = _retained_provenance(item, curated)
    item.pop("description_provenance", None)
    if not isinstance(item.get("pr"), dict):
        return set()
    recovered = recover_descriptions(item, source_prs)
    for field in FIELDS:
        if not _eligible(item, curated, field):
            continue
        if recovered and recovered.get(field):
            item[field] = ATTRIBUTION + recovered[field]
            retained[field] = {
                "url": item["pr"]["url"],
                "field_sha256": _sha(item[field]),
                "body_sha256": recovered["body_sha256"],
            }
        elif technical_fallback(item, field):
            item[field] = MISSING[field]
    if retained:
        item["description_provenance"] = retained
    return set(retained)


def description_findings(item: dict[Any, Any]) -> list[tuple[str, str]]:
    """Read-only deficits, independent of lifecycle and human request ownership."""
    rows = []
    if any(technical_fallback(item, field) for field in FIELDS):
        rows.append(
            (
                "technical_title_as_detail",
                "Un campo descrittivo ripete il titolo tecnico della PR.",
            )
        )
    if any(item.get(field) == MISSING[field] for field in FIELDS):
        rows.append(
            (
                "missing_pr_description",
                "La PR primaria non fornisce una descrizione utilizzabile "
                "per tutti i campi.",
            )
        )
    provenance = item.get("description_provenance")
    if provenance and (
        not isinstance(provenance, dict)
        or any(
            field not in FIELDS or not valid_description_provenance(item, field)
            for field in provenance
        )
    ):
        rows.append(
            (
                "stale_description_provenance",
                "La provenienza della descrizione non corrisponde "
                "al testo o alla PR primaria.",
            )
        )
    return rows
