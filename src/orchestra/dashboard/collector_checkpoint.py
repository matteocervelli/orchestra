"""Bounded lossless codec for accepted collector state; no I/O."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from . import collector as core

CORE_SHA = "1944831ec5e73bfea0f5f86934dec1eae125ca6748d0b818338417bbe4d6a97c"
MAX_BYTES = 64 * 1024 * 1024
Row = dict[str, Any]
Key = tuple[str, str, str, int]
HEX = re.compile(r"[0-9a-f]{64}")


class CheckpointError(ValueError):
    """Fixed public validation code, never an input value or parser diagnostic."""


def _require(value: bool, code: str = "invalid_checkpoint") -> None:
    if not value:
        raise CheckpointError(code)


def _stamp(value: object, now: float) -> bool:
    if type(value) not in (int, float):
        return False
    assert isinstance(value, (int, float))
    try:
        return math.isfinite(value) and 0 <= value <= now
    except OverflowError:
        return False


def _limit(limit: int) -> None:
    _require(type(limit) is int and 1 <= limit <= MAX_BYTES, "invalid_limit")


def _string_size(value: str, limit: int) -> int:
    size = 2
    for char in value:
        if char in '\\"\b\f\n\r\t':
            size += 2
        else:
            size += 6 if ord(char) < 32 else len(char.encode())
        _require(size <= limit, "document_limit")
    return size


def _container_size(value: dict[str, Any] | list[Any], limit: int, depth: int) -> int:
    size = 2
    entries = value.items() if isinstance(value, dict) else enumerate(value)
    for index, (key, child) in enumerate(entries):
        if isinstance(value, dict):
            _require(type(key) is str, "invalid_json")
            size += _size(key, limit, depth + 1) + 1
        size += _size(child, limit, depth + 1) + int(index > 0)
        _require(size <= limit, "document_limit")
    return size


def _size(value: object, limit: int, depth: int = 0) -> int:
    _require(depth <= 16, "json_depth")
    if type(value) is str:
        return _string_size(value, limit)
    if value is None or type(value) in (bool, int, float):
        if type(value) is float:
            _require(math.isfinite(value), "invalid_json")
        return len(json.dumps(value, allow_nan=False))
    _require(type(value) in (dict, list), "invalid_json")
    assert isinstance(value, (dict, list))
    return _container_size(value, limit, depth)


def _encode(value: object, limit: int) -> bytes:
    _limit(limit)
    try:
        _require(_size(value, limit) <= limit, "document_limit")
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        _require(len(raw) <= limit, "document_limit")
        return raw
    except CheckpointError:
        raise
    except (
        ValueError,
        TypeError,
        UnicodeError,
        OverflowError,
        RecursionError,
        MemoryError,
    ) as error:
        raise CheckpointError("invalid_json") from error


def _pairs(entries: list[tuple[str, Any]]) -> Row:
    result = {}
    for key, value in entries:
        _require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def _parse(raw: bytes, limit: int) -> Any:
    _limit(limit)
    _require(type(raw) is bytes and len(raw) <= limit, "document_limit")
    try:
        text = raw.decode("utf-8")
        depth, quoted, escaped = 0, False, False
        for char in text:
            if escaped:
                escaped = False
            elif quoted and char == "\\":
                escaped = True
            elif char == '"':
                quoted = not quoted
            elif not quoted:
                depth += int(char in "[{") - int(char in "]}")
                _require(depth <= 16, "json_depth")
        value = json.loads(text, object_pairs_hook=_pairs)
        _size(value, limit)
        return value
    except CheckpointError:
        raise
    except (
        UnicodeError,
        ValueError,
        OverflowError,
        RecursionError,
        MemoryError,
    ) as error:
        raise CheckpointError("invalid_json") from error


def _object(value: object, keys: set[str]) -> Row:
    _require(type(value) is dict and set(value) == keys)
    assert isinstance(value, dict)
    return value


def _url_key(url: str) -> Key:
    parsed = urlsplit(url)
    _require(
        parsed.scheme == "https" and not parsed.query and not parsed.fragment,
        "invalid_reference",
    )
    routes = {"github.com": "pull", "git.adlimen.dev": "pulls"}
    _require(parsed.netloc in routes, "invalid_reference")
    match = re.fullmatch(
        r"/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/(pull|pulls)/([1-9][0-9]*)", parsed.path
    )
    _require(match is not None, "invalid_reference")
    assert match
    owner, name, route, number = match.groups()
    _require(
        owner not in (".", "..")
        and name not in (".", "..")
        and route == routes[parsed.netloc],
        "invalid_reference",
    )
    return parsed.netloc, owner, name, int(number)


def qualified_key(row: Row) -> Key:
    _require(type(row) is dict, "invalid_reference")
    try:
        number, repo, url = row["number"], row["repository"], row["url"]
        _require(
            type(number) is int and number > 0 and type(url) is str, "invalid_reference"
        )
        _require(type(repo) is dict, "invalid_reference")
        key = _url_key(url)
        _require(
            repo.get("nameWithOwner") == key[1] + "/" + key[2]
            and repo.get("name") == key[2]
            and number == key[3],
            "invalid_reference",
        )
        return key
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise ValueError("invalid_reference") from error


def _rows(value: object, names: list[str], now: float) -> dict[str, Row]:
    _require(type(value) is dict)
    assert isinstance(value, dict)
    for url, row in value.items():
        key = qualified_key(row)
        _require(
            url == row["url"]
            and key[0] == "github.com"
            and key[1] + "/" + key[2] in names
        )
        for name in ("createdAt", "updatedAt", "closedAt", "mergedAt"):
            if row.get(name) is not None:
                _require(_stamp(core._date(row[name]), now))
        if "headRefOid" in row:
            core._sha(row["headRefOid"])
        if "state" in row:
            _require(row["state"] in ("open", "closed", "merged"))
    return value


@dataclass
class Snapshot:
    state: core.CollectionState
    lineage: dict[str, Row] = field(default_factory=dict)
    clock: float = 0.0


def _wire(snapshot: Snapshot) -> Row:
    _require(type(snapshot) is Snapshot)
    _require(set(vars(snapshot)) == {"state", "lineage", "clock"})
    state = snapshot.state
    _require(type(snapshot) is Snapshot and type(state) is core.CollectionState)
    _require(
        set(vars(state)) == {"pages", "progress", "last_good", "next_feed", "known"}
    )
    components = (
        (state.pages, core.Page),
        (state.progress, core.Progress),
        (state.last_good, core.LastGood),
    )
    for values, kind in components:
        _require(type(values) is dict and all(type(v) is kind for v in values.values()))
    progress = {}
    for key, value in state.progress.items():
        _require(type(value.digests) is set)
        _require(
            all(type(d) is str and HEX.fullmatch(d) is not None for d in value.digests)
        )
        progress[key] = vars(value) | {"digests": sorted(value.digests)}
    return {
        "pages": {k: vars(v) for k, v in state.pages.items()},
        "progress": progress,
        "last_good": {k: vars(v) for k, v in state.last_good.items()},
        "known": state.known,
        "next_feed": state.next_feed,
    }


def _page(value: object, now: float) -> core.Page:
    data = _object(value, {"rows", "fetched_at", "has_next", "error"})
    _require(_stamp(data["fetched_at"], now))
    _require(type(data["has_next"]) is bool or data["has_next"] is None)
    _require(
        data["error"] is None
        or (type(data["error"]) is str and data["error"] in core.ERRORS | {""})
    )
    page = core.Page(**data)
    if not page.error:
        core._envelope(page, now)
    return page


def _prefix(
    feed: core.Request, count: int, pages: dict[str, core.Page], now: float
) -> core.Progress:
    expected = core.Progress()
    for number in range(1, count + 1):
        request = core.Request(
            feed.repository, feed.base, feed.state, number, feed.cutoff
        )
        _require(request.cache_key in pages and not expected.done)
        page = pages[request.cache_key]
        rows = core._validated(page, request, expected, now)
        core._accept(page, request, expected, rows)
    return expected


def _digests(value: object) -> set[str]:
    _require(type(value) is list)
    assert isinstance(value, list)
    _require(all(type(d) is str and HEX.fullmatch(d) is not None for d in value))
    _require(value == sorted(set(value)))
    return set(value)


def _progress(
    value: object,
    feed: core.Request,
    pages: dict[str, core.Page],
    names: list[str],
    now: float,
) -> core.Progress:
    data = _object(
        value,
        {
            "page",
            "rows",
            "times",
            "digests",
            "last_created",
            "done",
            "reason",
            "invalidated",
        },
    )
    _require(type(data["times"]) is list and all(_stamp(t, now) for t in data["times"]))
    _require(
        type(data["page"]) is int and data["page"] == len(data["times"]) + 1 <= 101
    )
    _require(type(data["done"]) is bool and type(data["invalidated"]) is bool)
    digests = _digests(data["digests"])
    _rows(data["rows"], names, now)
    _require(data["last_created"] is None or _stamp(data["last_created"], now))
    expected = _prefix(feed, len(data["times"]), pages, now)
    for key in ("page", "rows", "times", "last_created", "done"):
        _require(data[key] == getattr(expected, key))
    _require(digests == expected.digests)
    _require(
        type(data["reason"]) is str and data["reason"] in core.ERRORS | core.RESUMABLE
    )
    terminal = {"exhausted", "cutoff"}
    _require(
        data["reason"] == expected.reason
        if data["done"]
        else data["reason"] not in terminal
    )
    return core.Progress(**(data | {"digests": digests}))


def _restore_pages(
    wire: Row, feeds: dict[str, core.Request], names: list[str], now: float
) -> dict[str, core.Page]:
    pages = {}
    for key, value in wire.items():
        fingerprint, separator, index = key.rpartition(":")
        _require(separator == ":" and fingerprint in feeds and index.isdigit())
        _require(str(int(index)) == index and 1 <= int(index) <= 100)
        page = pages[key] = _page(value, now)
        if page.error:
            continue
        feed = feeds[fingerprint]
        request = core.Request(
            feed.repository, feed.base, feed.state, int(index), feed.cutoff
        )
        assert isinstance(page.rows, list)
        for raw in page.rows:
            row = core._normalize(raw, request)
            _rows({row["url"]: row}, names, now)
    return pages


def _restore_good(
    wire: Row, feeds: dict[str, core.Request], now: float
) -> dict[str, core.LastGood]:
    good = {}
    for key, value in wire.items():
        v = _object(value, {"rows", "completed_at", "oldest_at"})
        _require(
            _stamp(v["completed_at"], now) and _stamp(v["oldest_at"], v["completed_at"])
        )
        rows = _rows(v["rows"], [feeds[key].repository], now)
        if feeds[key].state == "open":
            _require(all(row.get("state") == "open" for row in rows.values()))
        good[key] = core.LastGood(rows, v["completed_at"], v["oldest_at"])
    return good


def _restore(data: Row, names: list[str], now: float) -> core.CollectionState:
    wire = _object(data, {"pages", "progress", "last_good", "next_feed", "known"})
    feeds = {f.feed_key: f for f in core._plan(names, "2026-10-13T00:00:00Z")}
    for key in ("pages", "progress", "last_good"):
        _require(type(wire[key]) is dict)
    _require(
        set(wire["progress"]) <= feeds.keys() and set(wire["last_good"]) <= feeds.keys()
    )
    pages = _restore_pages(wire["pages"], feeds, names, now)
    progress = {
        k: _progress(v, feeds[k], pages, names, now)
        for k, v in wire["progress"].items()
    }
    good = _restore_good(wire["last_good"], feeds, now)
    cursor = wire["next_feed"]
    _require(type(cursor) is int and 0 <= cursor < len(feeds))
    return core.CollectionState(
        pages, progress, good, cursor, _rows(wire["known"], names, now)
    )


def _document(
    value: object, repositories: Sequence[core.Repository], now: float
) -> Snapshot:
    data = _object(
        value, {"schema", "core_sha256", "scope", "state", "lineage", "clock"}
    )
    names = core._scope(repositories)
    _require(data["schema"] == 1 and type(data["schema"]) is int)
    _require(data["core_sha256"] == CORE_SHA and data["scope"] == names)
    _require(_stamp(data["clock"], now))
    state = _restore(data["state"], names, data["clock"])
    _require(
        type(data["lineage"]) is dict and data["lineage"].keys() <= state.known.keys()
    )
    for url, value in data["lineage"].items():
        evidence = _object(value, {"row_sha256", "observed_at", "source"})
        _require(
            evidence["row_sha256"]
            == hashlib.sha256(_encode(state.known[url], MAX_BYTES)).hexdigest()
        )
        _require(
            evidence["observed_at"] is None
            or _stamp(evidence["observed_at"], data["clock"])
        )
        _require(type(evidence["source"]) is str and len(evidence["source"]) <= 32)
    return Snapshot(state, data["lineage"], data["clock"])


def encode_checkpoint(
    snapshot: Snapshot,
    repositories: Sequence[core.Repository],
    *,
    now: float,
    limit: int = MAX_BYTES,
) -> bytes:
    _require(_stamp(now, now), "invalid_clock")
    data = {
        "schema": 1,
        "core_sha256": CORE_SHA,
        "scope": core._scope(repositories),
        "state": _wire(snapshot),
        "lineage": snapshot.lineage,
        "clock": snapshot.clock,
    }
    raw = _encode(data, limit)
    _document(data, repositories, now)
    return raw


def decode_checkpoint(
    raw: bytes,
    repositories: Sequence[core.Repository],
    *,
    now: float,
    limit: int = MAX_BYTES,
) -> Snapshot:
    _require(_stamp(now, now), "invalid_clock")
    return _document(_parse(raw, limit), repositories, now)
