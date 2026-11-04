"""Detail/index bounds and snapshot membership preflight; no filesystem access."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from .quality import board_digest, detail_matches_board

HISTORY_BYTE_LIMIT = 10 * 1024 * 1024
HISTORY_FIELDS = (
    "id",
    "title",
    "status",
    "repo",
    "kind",
    "issue",
    "pr",
    "priority",
    "priority_src",
    "order",
    "updated",
    "your_call",
    "call_kind",
    "ask",
    "steps",
    "links",
    "gates",
    "blocked",
    "agent",
    "taken",
    "child",
    "slugs",
)
_ITEM_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_GENERATED = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z"
)
type Row = dict[str, Any]
type Projector = Callable[[Row, list[Row]], Row]


def history_terminal(item: Row) -> bool:
    """Use the consumer's existing case-insensitive terminal membership."""
    status = item.get("status")
    return isinstance(status, str) and status.casefold() in {"deployed", "dropped"}


def history_item(item: Row, ledger: list[Row], projector: Projector) -> Row:
    """Keep bounded summaries, restoring every present compatibility value."""
    result = dict(projector(item, ledger))
    for key in (*HISTORY_FIELDS, "hidden", "hide"):
        if key in item:
            result[key] = item[key]
        else:
            result.pop(key, None)
    return result


def _members(rows: object) -> dict[str, Row]:
    if not isinstance(rows, list):
        raise ValueError("history_items")
    members = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("history_item")
        if not isinstance(row.get("status"), str):
            raise ValueError("history_item_status")
        item_id = row.get("id")
        if not isinstance(item_id, str) or not _ITEM_ID.fullmatch(item_id):
            raise ValueError("history_item_id")
        if item_id in members:
            raise ValueError("history_duplicate_id")
        members[item_id] = row
    return members


def _bounded_json(value: Row) -> None:
    # Matches _write_compact's actual UTF-8 representation, with NaN rejected.
    raw = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if len(raw) > HISTORY_BYTE_LIMIT:
        raise ValueError("history_byte_limit")


def _metadata(board: Row) -> str:
    generated = board.get("generated")
    if not isinstance(generated, str) or not _GENERATED.fullmatch(generated):
        raise ValueError("history_generated")
    datetime.strptime(generated, "%Y-%m-%dT%H:%M:%S.%fZ")
    statuses = board.get("statuses")
    if not isinstance(statuses, list) or any(not isinstance(s, str) for s in statuses):
        raise ValueError("history_statuses")
    return board_digest(board)


def _publication_members(board: Row, terminal: list[Row]) -> tuple[Row, Row]:
    active = _members(board.get("items"))
    archived = _members(terminal)
    if active.keys() & archived.keys():
        raise ValueError("history_active_overlap")
    if any(history_terminal(row) for row in active.values()):
        raise ValueError("history_active_status")
    for row in terminal:
        if not history_terminal(row) or type(row.get("your_call")) is not bool:
            raise ValueError("history_terminal_schema")
    return active, archived


def _validate_details(
    board: Row,
    terminal: list[Row],
    details: list[Row],
    ledger: list[Row],
    projector: Projector,
    digest: str,
) -> None:
    active, archived = _publication_members(board, terminal)
    rich = _members(details)
    expected = active | archived
    if rich.keys() != expected.keys():
        raise ValueError("history_detail_membership")
    for item_id, row in rich.items():
        if row.get("status") != expected[item_id].get(
            "status"
        ) or not detail_matches_board(row, board, item_id, snapshot_digest=digest):
            raise ValueError("history_detail_snapshot")
        if item_id in archived:
            coherent = history_item(row, ledger, projector) == history_item(
                archived[item_id], ledger, projector
            )
        else:
            coherent = projector(row, ledger) == active[item_id]
        if not coherent:
            raise ValueError("history_detail_summary")
        _bounded_json(row)


def prepare_history_index(
    board: Row,
    terminal: list[Row],
    details: list[Row],
    ledger: list[Row],
    projector: Projector,
) -> Row:
    """Validate membership/stamps and detail/index bounds before artifact writes."""
    digest = _metadata(board)
    _validate_details(board, terminal, details, ledger, projector, digest)
    index = {
        "version": 1,
        "generated": board["generated"],
        "board_sha256": digest,
        "statuses": board["statuses"],
        "items": [history_item(row, ledger, projector) for row in terminal],
    }
    _bounded_json(index)
    return index
