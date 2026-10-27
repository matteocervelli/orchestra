"""Explicit work roles and read-only, exact-mandate reconciliation proposals."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from .common import repository_authority, short_repo

_MARKER = re.compile(r"^```json orchestra-task-meta[ \t]*$", re.M)


def qualified_pr(raw: object, repo: str) -> dict[str, Any] | None:
    if (
        not isinstance(raw, dict)
        or type(raw.get("number")) is not int
        or raw["number"] < 1
    ):
        return None
    location = _pr_location(raw.get("url"))
    if location is None:
        return None
    host, path, url = location
    repository = _pr_path_repository(path, host, repo, raw["number"])
    if repository is None or not _pr_fields_match(raw, host, repository):
        return None
    return {"host": host, "repo": repository, "number": raw["number"], "url": url}


def declaration(raw: object, source: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or set(raw) != {"kind", "subject", "relation"}:
        return None
    if raw["kind"] not in ("local_artifact_review", "primary_integration") or raw[
        "relation"
    ] not in ("primary", "dependency"):
        return None
    subject = _normalized_subject(raw["subject"])
    if subject is None:
        return None
    return {
        "kind": raw["kind"],
        "subject": subject,
        "relation": raw["relation"],
        "source": source,
        "validation": "unverified" if source == "child_report" else "validated",
    }


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate_key")
        out[key] = value
    return out


def _bounded_json(text: str) -> bool:
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 16:
                return False
        elif char in "]}":
            depth -= 1
    return True


def parse_task_provenance(text: str) -> tuple[dict[str, Any] | None, list[str]]:
    block, errors = _task_metadata_block(text)
    if block is None:
        return None, errors
    try:
        obj = json.loads(block, object_pairs_hook=_unique_pairs)
    except (ValueError, RecursionError):
        return None, ["invalid_task_metadata_json"]
    if (
        not isinstance(obj, dict)
        or set(obj) != {"schema", "work_provenance"}
        or obj["schema"] != "orchestra-task-meta/v1"
    ):
        return None, ["task_metadata_schema"]
    value = declaration(obj["work_provenance"], "task_contract")
    return (value, []) if value else (None, ["invalid_work_provenance"])


def resolve_work_provenance(
    note: dict[str, Any], task_rows: list[dict[str, Any]], card: dict[str, Any]
) -> dict[str, Any]:
    trusted, invalid = _trusted_declarations(note, task_rows)
    child = declaration(card.get("work_provenance"), "child_report")
    if "work_provenance" in card and child is None:
        invalid = True
    declarations = trusted + ([child] if child else [])
    if invalid or len(_declaration_signatures(declarations)) > 1:
        return {"kind": "unknown", "validation": "conflict", "source": "unverified"}
    return (
        declarations[0]
        if declarations
        else {"kind": "unknown", "validation": "unverified", "source": "unverified"}
    )


def local_review(item: dict[str, Any]) -> bool:
    value = item.get("work_provenance")
    if (
        not isinstance(value, dict)
        or value.get("validation") != "validated"
        or value.get("source") not in ("task_contract", "curated_note")
    ):
        return False
    parsed = declaration(
        {key: value.get(key) for key in ("kind", "subject", "relation")},
        str(value["source"]),
    )
    return bool(
        parsed
        and parsed["kind"] == "local_artifact_review"
        and parsed["relation"] == "primary"
        and "artifact" in parsed["subject"]
        and not item.get("pr")
        and not item.get("prs")
    )


def _date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except ValueError:
        return None


def propose_request_reconciliation(
    requests: list[dict[str, Any]], receipts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    out = []
    for request in requests:
        match = _matching_receipt(request, receipts)
        out.append(
            {
                "request_id": request.get("id"),
                "result": "satisfied_candidate" if match else "unverified",
                "receipt": match["id"] if match else None,
                "reason": "later receipt for the exact mandate"
                if match
                else "no exact later successful receipt",
            }
        )
    return out


def github_primary(raw: object, repo: str) -> bool:
    value = qualified_pr(raw, repo)
    return bool(value and value["host"] == "github.com")


def identity_delta(
    before: list[dict[str, Any]], after: list[dict[str, Any]]
) -> dict[str, Any]:
    """Describe supplied snapshots only; this never authorizes or performs rekey."""
    old = {row["id"]: row for row in before}
    new = {row["id"]: row for row in after}
    if len(old) != len(before) or len(new) != len(after):
        raise ValueError("duplicate_snapshot_id")
    fields = (
        "ask",
        "steps",
        "priority",
        "answers",
        "approval",
        "status",
        "hide",
        "pages",
        "aliases",
    )
    return {
        "added_ids": sorted(new.keys() - old.keys()),
        "removed_ids": sorted(old.keys() - new.keys()),
        "changed_ids": sorted(
            key for key in old.keys() & new.keys() if old[key] != new[key]
        ),
        "preservation": {
            key: {field: old[key].get(field) == new[key].get(field) for field in fields}
            for key in sorted(old.keys() & new.keys())
        },
        "old_link_ids_preserved": old.keys() <= new.keys(),
        "runtime_ready": False,
    }


def _pr_location(url: object) -> tuple[str, str, str] | None:
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.netloc not in ("github.com", "git.adlimen.dev")
        or parsed.query
        or parsed.fragment
    ):
        return None
    return parsed.netloc, parsed.path, url


def _pr_path_repository(path: str, host: str, repo: str, number: int) -> str | None:
    match = re.fullmatch(r"/([\w.-]+)/([\w.-]+)/(pull|pulls)/(\d+)/?", path)
    if not match:
        return None
    repository = f"{match[1]}/{match[2]}"
    if int(match[4]) != number or repository != repository_authority(repo):
        return None
    if match[3] != ("pull" if host == "github.com" else "pulls"):
        return None
    return repository


def _pr_fields_match(raw: dict[str, Any], host: str, repository: str) -> bool:
    return ("host" not in raw or raw["host"] == host) and (
        "repo" not in raw or raw["repo"] == repository
    )


def _artifact_identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= 500
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _declared_pr(raw: object, repo: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or set(raw) != {"host", "repo", "number", "url"}:
        return None
    return qualified_pr(raw, repo)


def _normalized_subject(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or set(raw) not in (
        {"repo", "artifact"},
        {"repo", "pr"},
    ):
        return None
    repo = raw["repo"]
    if not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", repo):
        return None
    subject = {**raw, "repo": short_repo(repo)}
    if "artifact" in subject:
        if not _artifact_identifier(subject["artifact"]):
            return None
    else:
        pr = _declared_pr(subject["pr"], repo)
        if not pr:
            return None
        subject["pr"] = pr
    return subject


def _task_metadata_block(text: str) -> tuple[str | None, list[str]]:
    markers = list(_MARKER.finditer(text))
    if not markers:
        return None, []
    if len(markers) != 1:
        return None, ["duplicate_task_metadata"]
    block, errors = _task_metadata_location(text, markers[0])
    if block is None:
        return None, errors
    if len(block.encode("utf-8")) > 4096:
        return None, ["task_metadata_limit"]
    if not _bounded_json(block):
        return None, ["task_metadata_depth"]
    return block, []


def _task_metadata_location(
    text: str, marker: re.Match[str]
) -> tuple[str | None, list[str]]:
    before = text[: marker.start()].splitlines()
    if (
        not before
        or not re.fullmatch(r"#{1,6}\s+\S.*", before[0])
        or any(line.strip() for line in before[1:])
    ):
        return None, ["misplaced_task_metadata"]
    rest = text[marker.end() :]
    closing = re.search(r"^```[ \t]*$", rest, re.M)
    if not closing:
        return None, ["unclosed_task_metadata"]
    return rest[: closing.start()], []


def _trusted_declarations(
    note: dict[str, Any], task_rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], bool]:
    trusted = []
    invalid = any(row.get("provenance_errors") for row in task_rows)
    if "work_provenance" in note:
        parsed = declaration(note["work_provenance"], "curated_note")
        if parsed:
            trusted.append(parsed)
        else:
            invalid = True
    for row in task_rows:
        raw = row.get("work_provenance")
        if raw is not None:
            payload = (
                {key: raw.get(key) for key in ("kind", "subject", "relation")}
                if isinstance(raw, dict)
                else raw
            )
            parsed = declaration(payload, "task_contract")
            if parsed:
                trusted.append(parsed)
            else:
                invalid = True
    return trusted, invalid


def _declaration_signatures(declarations: list[dict[str, Any]]) -> set[str]:
    return {
        json.dumps(
            {key: row[key] for key in ("kind", "subject", "relation")}, sort_keys=True
        )
        for row in declarations
    }


def _matching_receipt(
    request: dict[str, Any], receipts: list[dict[str, Any]]
) -> dict[str, Any] | None:
    created = _date(request.get("created_at"))
    keys = ("mandate_id", "repo", "target", "action", "scope")
    if not created or not all(request.get(key) for key in keys):
        return None
    for receipt in receipts:
        if _receipt_satisfies(request, receipt, created, keys):
            return receipt
    return None


def _receipt_satisfies(
    request: dict[str, Any],
    receipt: dict[str, Any],
    created: datetime,
    keys: tuple[str, ...],
) -> bool:
    received = _date(receipt.get("recorded_at"))
    return bool(
        all(receipt.get(key) == request[key] for key in keys)
        and receipt.get("status") == "succeeded"
        and receipt.get("id")
        and received
        and received > created
    )
