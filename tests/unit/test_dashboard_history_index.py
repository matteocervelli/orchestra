"""Synthetic history publication contract; no runtime import or discovery."""

import copy
import json

import pytest

from orchestra.dashboard.history_index import (
    HISTORY_BYTE_LIMIT,
    HISTORY_FIELDS,
    history_item,
    history_terminal,
    prepare_history_index,
)
from orchestra.dashboard.quality import bind_detail, board_digest

GENERATED = "2026-11-04T12:00:00.000001Z"


def projection(item, ledger):
    return {
        "id": item["id"],
        "status": item.get("status"),
        "history": item.get("history", [])[-5:],
    }


def snapshot():
    active = {"id": "active", "status": "Doing", "your_call": False}
    terminal = {"id": "closed", "status": "Deployed", "your_call": False}
    board = {
        "generated": GENERATED,
        "statuses": ["Doing", "Deployed", "Dropped"],
        "items": [projection(active, [])],
    }
    details = [bind_detail(item, board) for item in [active, terminal]]
    return board, [terminal], details


def prepare(board, terminal, details):
    return prepare_history_index(board, terminal, details, [], projection)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def test_projection_preserves_every_present_field_and_hidden_without_mutation():
    values = [None, "", False, 0, {}, []]
    item = {
        key: copy.deepcopy(values[i % len(values)])
        for i, key in enumerate(HISTORY_FIELDS)
    }
    item.update(
        id="closed",
        status="Dropped",
        your_call=False,
        hidden=False,
        hide=None,
        history=list(range(45)),
        children=[{"slug": "x"}],
        raw="unpublished",
    )
    before = copy.deepcopy(item)
    row = history_item(item, [], projection)
    for key in (*HISTORY_FIELDS, "hidden", "hide"):
        assert row[key] == item[key]
        assert type(row[key]) is type(item[key])
    assert row["history"] == list(range(40, 45))
    assert "raw" not in row
    assert "title" not in history_item({"id": "minimal"}, [], projection)
    assert item == before


def test_index_metadata_order_and_full_details_are_preserved():
    board, terminal, details = snapshot()
    terminal.append({"id": "second", "status": "dRoPpEd", "your_call": True})
    terminal[0]["history"] = list(range(45))
    details = [bind_detail(item, board) for item in [board["items"][0], *terminal]]
    before = copy.deepcopy(details)
    index = prepare(board, terminal, details)
    assert index == {
        "version": 1,
        "generated": GENERATED,
        "board_sha256": board_digest(board),
        "statuses": board["statuses"],
        "items": [
            {
                "id": "closed",
                "status": "Deployed",
                "your_call": False,
                "history": [40, 41, 42, 43, 44],
            },
            {"id": "second", "status": "dRoPpEd", "your_call": True, "history": []},
        ],
    }
    assert index["items"][0]["your_call"] is False
    assert index["items"][1]["your_call"] is True
    assert details == before
    assert len(details[1]["history"]) == 45
    assert len(index["items"][0]["history"]) == 5


def test_generation_requires_ascii_digits():
    board, terminal, details = snapshot()
    board["generated"] = "٢٠٢٦" + GENERATED[4:]
    details = [bind_detail(row, board) for row in details]
    with pytest.raises(ValueError, match="generated"):
        prepare(board, terminal, details)


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "changed"),
        ("ask", [{"id": "new"}]),
        ("hidden", True),
        ("history", ["changed"]),
    ],
)
def test_same_stamp_cannot_publish_divergent_terminal_summary(field, value):
    board, terminal, details = snapshot()
    terminal[0][field] = value
    with pytest.raises(ValueError, match="summary"):
        prepare(board, terminal, details)


def test_same_stamp_cannot_publish_divergent_active_summary():
    board, terminal, details = snapshot()
    board["items"][0]["history"] = ["changed"]
    details = [bind_detail(row, board) for row in details]
    with pytest.raises(ValueError, match="summary"):
        prepare(board, terminal, details)


@pytest.mark.parametrize(
    "status,expected",
    [
        ("DEPLOYED", True),
        ("dropped", True),
        ("Doing", False),
        (None, False),
        (False, False),
    ],
)
def test_terminal_comparison_is_case_insensitive(status, expected):
    assert history_terminal({"status": status}) is expected


@pytest.mark.parametrize(
    "mutation",
    [
        "bad_generation",
        "bad_calendar",
        "bad_statuses",
        "bad_active_id",
        "bad_terminal_id",
        "duplicate_active",
        "duplicate_terminal",
        "overlap",
        "missing_your_call",
        "null_your_call",
        "int_your_call",
        "nonterminal",
        "missing_detail",
        "extra_detail",
        "duplicate_detail",
        "bad_detail_id",
        "bad_stamp",
        "bool_version",
        "bad_detail_status",
        "nonfinite",
        "bad_digest",
    ],
)
def test_invalid_snapshot_is_rejected(mutation):
    board, terminal, details = snapshot()
    if mutation == "bad_generation":
        board["generated"] = GENERATED[:-1] + "+00:00"
    elif mutation == "bad_calendar":
        board["generated"] = "2026-99-04T12:00:00.000001Z"
    elif mutation == "bad_statuses":
        board["statuses"] = [False]
    elif mutation == "bad_active_id":
        board["items"][0]["id"] = "../escape"
    elif mutation == "bad_terminal_id":
        terminal[0]["id"] = "../escape"
    elif mutation == "duplicate_active":
        board["items"] *= 2
    elif mutation == "duplicate_terminal":
        terminal *= 2
    elif mutation == "overlap":
        terminal[0]["id"] = "active"
    elif mutation == "missing_your_call":
        terminal[0].pop("your_call")
    elif mutation == "null_your_call":
        terminal[0]["your_call"] = None
    elif mutation == "int_your_call":
        terminal[0]["your_call"] = 0
    elif mutation == "nonterminal":
        terminal[0]["status"] = "Doing"
    elif mutation == "missing_detail":
        details.pop()
    elif mutation == "extra_detail":
        details.append(bind_detail({"id": "extra", "status": "Doing"}, board))
    elif mutation == "duplicate_detail":
        details.append(copy.deepcopy(details[0]))
    elif mutation == "bad_detail_id":
        details[0]["id"] = "/unsafe"
    elif mutation == "bad_stamp":
        details[0]["_producer_snapshot"]["generated"] = "old"
    elif mutation == "bool_version":
        details[0]["_producer_snapshot"]["version"] = True
    elif mutation == "bad_detail_status":
        details[1]["status"] = "Doing"
    elif mutation == "nonfinite":
        details[0]["evidence"] = float("nan")
    elif mutation == "bad_digest":
        details[0]["_producer_snapshot"]["board_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        prepare(board, terminal, details)


@pytest.mark.parametrize("surface", ["index", "detail"])
def test_actual_serialized_byte_limit_is_inclusive(surface):
    board, terminal, details = snapshot()
    if surface == "index":
        terminal[0]["title"] = "é"
        details[1]["title"] = terminal[0]["title"]
        empty = prepare(board, terminal, details)
        terminal[0]["title"] += "x" * (HISTORY_BYTE_LIMIT - len(encoded(empty)))
        details[1]["title"] = terminal[0]["title"]
        assert len(encoded(prepare(board, terminal, details))) == HISTORY_BYTE_LIMIT
        terminal[0]["title"] += "x"
        details[1]["title"] = terminal[0]["title"]
    else:
        details[1]["evidence"] = "é"
        details[1]["evidence"] += "x" * (HISTORY_BYTE_LIMIT - len(encoded(details[1])))
        assert len(encoded(details[1])) == HISTORY_BYTE_LIMIT
        prepare(board, terminal, details)
        details[1]["evidence"] += "x"
    with pytest.raises(ValueError, match="byte_limit"):
        prepare(board, terminal, details)
