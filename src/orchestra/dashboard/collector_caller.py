"""Pure injected collection, storage and metadata contracts; no runtime wiring."""

from __future__ import annotations

import copy
import hashlib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from . import collector as core
from .collector_checkpoint import (
    CORE_SHA as CORE_SHA,
)
from .collector_checkpoint import (
    MAX_BYTES as MAX_BYTES,
)
from .collector_checkpoint import (
    Key,
    Row,
    _encode,
    _limit,
    _parse,
    _require,
    _rows,
    _size,
    _stamp,
)
from .collector_checkpoint import (
    Snapshot as Snapshot,
)
from .collector_checkpoint import (
    decode_checkpoint as decode_checkpoint,
)
from .collector_checkpoint import (
    encode_checkpoint as encode_checkpoint,
)
from .collector_checkpoint import (
    qualified_key as qualified_key,
)

FRESHNESS = 900


@dataclass
class Budget:
    remaining: int
    attempts: int = 0

    def __post_init__(self) -> None:
        _require(
            type(self.remaining) is int
            and type(self.attempts) is int
            and 0 <= self.remaining <= 25
            and 0 <= self.attempts <= 25,
            "invalid_budget",
        )
        _require(self.remaining + self.attempts <= 25, "invalid_budget")

    @property
    def allowance(self) -> int:
        return min(20, max(0, self.remaining - 5))

    def attempt(
        self, request: core.Request, fetch: Callable[[core.Request], core.Page]
    ) -> core.Page:
        _require(self.remaining > 5, "budget_exhausted")
        self.remaining -= 1
        self.attempts += 1
        return fetch(request)


@dataclass
class Prepared:
    rows: list[Row]
    checkpoint: bytes | None
    mirror: bytes | None
    receipt: Row


def _known_lineage(rows: dict[str, Row], previous: dict[str, Row]) -> dict[str, Row]:
    result = {}
    for url, row in rows.items():
        digest = hashlib.sha256(_encode(row, MAX_BYTES)).hexdigest()
        old = previous.get(url, {})
        result[url] = (
            copy.deepcopy(old)
            if old.get("row_sha256") == digest
            else {"row_sha256": digest, "observed_at": None, "source": "unknown"}
        )
    return result


def _page_rows(key: str, page: core.Page, feeds: dict[str, core.Request]) -> list[Row]:
    if page.error:
        return []
    fingerprint, _, number = key.rpartition(":")
    feed = feeds[fingerprint]
    request = core.Request(
        feed.repository, feed.base, feed.state, int(number), feed.cutoff
    )
    assert isinstance(page.rows, list)
    return [core._normalize(raw, request) for raw in page.rows]


def _lineage(
    result: core.Collection,
    previous: dict[str, Row],
    repositories: Sequence[core.Repository],
) -> dict[str, Row]:
    evidence = _known_lineage(result.state.known, previous)
    conflicts = {issue["url"] for issue in result.issues}
    feeds = {
        f.feed_key: f
        for f in core._plan(core._scope(repositories), "2026-10-13T00:00:00Z")
    }
    for key, page in result.state.pages.items():
        for row in _page_rows(key, page, feeds):
            url = row["url"]
            if url in conflicts or result.state.known.get(url) != row:
                continue
            old = evidence[url]["observed_at"]
            if old is None or page.fetched_at > old:
                evidence[url] = evidence[url] | {
                    "observed_at": page.fetched_at,
                    "source": "collector",
                }
    return evidence


@dataclass
class _ObservedClock:
    read: Callable[[], float]
    latest: float
    failed: bool = False

    def __call__(self) -> float:
        try:
            value = self.read()
            _require(_stamp(value, value) and value >= self.latest, "invalid_clock")
            self.latest = value
            return value
        except Exception as error:
            self.failed = True
            raise ValueError("invalid_clock") from error


def _prior(
    raw: bytes | None, repositories: Sequence[core.Repository], now: float, limit: int
) -> list[Row]:
    value = _parse(raw, limit) if raw is not None else []
    _require(type(value) is list)
    _require(all(type(row) is dict for row in value))
    value = [row.copy() for row in value]
    for row in value:
        if row.get("state") == "open" and row.get("closedAt") == "0001-01-01T00:00:00Z":
            row["closedAt"] = None
    names = core._scope(repositories)
    rows = core._retained(value, names)
    _rows(rows, names, now)
    return list(rows.values())


def _run_collection(
    repositories: Sequence[core.Repository],
    snapshot: Snapshot,
    prior: list[Row],
    budget: Budget,
    attempt: Callable[[core.Request], core.Page],
    now: float,
    clock: _ObservedClock,
) -> core.Collection:
    allowance, before, remaining = budget.allowance, budget.attempts, budget.remaining
    result = core.collect(
        repositories,
        lambda r: budget.attempt(r, attempt),
        now=now,
        clock=clock,
        freshness=FRESHNESS,
        budget=allowance,
        state=snapshot.state,
        retained=prior,
    )
    _require(not clock.failed, "invalid_clock")
    spent = budget.attempts - before
    _require(
        spent == allowance - result.budget_remaining == remaining - budget.remaining,
        "budget_mismatch",
    )
    return result


def _stage(
    result: core.Collection,
    snapshot: Snapshot,
    repositories: Sequence[core.Repository],
    now: float,
    limit: int,
) -> tuple[bytes, bytes | None, Row]:
    lineage = _lineage(result, snapshot.lineage, repositories)
    statuses = {c["status"] for c in result.coverage}
    status = "complete" if statuses == {"complete"} and not result.issues else "partial"
    if "error" in statuses:
        status = "error"
    elif "stale" in statuses:
        status = "stale"
    encoded = encode_checkpoint(
        Snapshot(result.state, lineage, now), repositories, now=now, limit=limit
    )
    mirror = _encode(result.rows, limit) if status == "complete" else None
    receipt = {
        "status": status,
        "reason": "conflicting_records" if result.issues else status,
        "lineage": lineage,
        "feeds": result.coverage,
    }
    return encoded, mirror, receipt


def _fallback(
    prior: list[Row], snapshot: Snapshot | None
) -> tuple[list[Row], dict[str, Row]]:
    rows = {row["url"]: row for row in prior}
    previous = {}
    if snapshot is not None:
        rows.update(snapshot.state.known)
        previous = snapshot.lineage
    return list(rows.values()), _known_lineage(rows, previous)


def _storage_call[T](callback: Callable[..., T], *args: object) -> T:
    try:
        return callback(*args)
    except Exception:
        raise OSError("storage_callback_error") from None


def prepare_collection(
    repositories: Sequence[core.Repository],
    budget: Budget,
    attempt: Callable[[core.Request], core.Page],
    read: Callable[[str, int], bytes | None],
    commit: Callable[[bytes, bytes | None], None],
    *,
    now: float,
    clock: Callable[[], float],
    limit: int = MAX_BYTES,
) -> Prepared:
    prior_raw = checkpoint = None
    prior: list[Row] = []
    snapshot = None
    before = budget.attempts
    receipt: Row = {
        "status": "error",
        "reason": "load_error",
        "lineage": {},
        "feeds": [],
    }
    try:
        _limit(limit)
        _require(_stamp(now, now), "invalid_clock")
        prior_raw = _storage_call(read, "prs.json", limit + 1)
        prior = _prior(prior_raw, repositories, now, limit)
        checkpoint = _storage_call(read, "prs-rest-v1.json", limit + 1)
        snapshot = (
            decode_checkpoint(checkpoint, repositories, now=now, limit=limit)
            if checkpoint is not None
            else Snapshot(core.CollectionState(), {}, now)
        )
        observed = _ObservedClock(clock, now)
        receipt["reason"] = "collection_error"
        result = _run_collection(
            repositories, snapshot, prior, budget, attempt, now, observed
        )
        receipt["reason"] = "codec_error"
        encoded, mirror, staged = _stage(
            result, snapshot, repositories, observed.latest, limit
        )
        receipt["reason"] = "storage_error"
        _storage_call(commit, encoded, mirror)
        staged.update(
            checkpoint_saved=True,
            mirror_saved=mirror is not None,
            attempts=budget.attempts - before,
            budget_remaining=budget.remaining,
        )
        return Prepared(
            result.rows, encoded, mirror if mirror is not None else prior_raw, staged
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        OverflowError,
        RecursionError,
        MemoryError,
    ):
        rows, lineage = _fallback(prior, snapshot)
        receipt.update(
            status="error",
            checkpoint_saved=False,
            mirror_saved=False,
            attempts=budget.attempts - before,
            budget_remaining=budget.remaining,
            lineage=lineage,
        )
        return Prepared(rows, checkpoint, prior_raw, receipt)


def decode_page(stdout: str, returncode: int, observed_at: float) -> core.Page:
    try:
        header, separator, body = stdout.replace("\r\n", "\n").partition("\n\n")
        _require(bool(separator), "invalid_json")
        lines = header.splitlines()
        _require(
            re.fullmatch(r"HTTP/(?:1\.[01]|[23](?:\.0)?) [0-9]{3}(?: .*)?", lines[0])
            is not None,
            "invalid_json",
        )
        status = int(lines[0].split()[1])
        if status == 429:
            return core.Page([], observed_at, None, "rate_limit")
        if returncode or status != 200:
            return core.Page([], observed_at, None, "unavailable")
        rows = _parse(body.encode(), core.MAX_BYTES)
        _require(type(rows) is list, "invalid_json")
        links = [
            line.partition(":")[2] for line in lines if line.lower().startswith("link:")
        ]
        return core.Page(rows, observed_at, any('rel="next"' in line for line in links))
    except (ValueError, TypeError, IndexError, UnicodeError):
        return core.Page([], observed_at, None, "invalid_json")


@dataclass
class Selection:
    rows: list[Row]
    issues: list[Row]


def _rank(candidate: Row, now: float) -> tuple[int, float, float]:
    observed = candidate["observed_at"]
    _require(observed is None or _stamp(observed, now), "invalid_reference")
    version = (
        core._date(candidate["row"]["updatedAt"])
        if candidate["row"].get("updatedAt")
        else -1.0
    )
    _require(version <= now, "invalid_reference")
    return (
        -1 if observed is None else int(now - observed <= FRESHNESS),
        version,
        -1.0 if observed is None else observed,
    )


def _group_candidates(
    candidates: Sequence[Row], now: float
) -> tuple[dict[Key, list[tuple[tuple[int, float, float], Row]]], list[Row]]:
    grouped: dict[Key, list[tuple[tuple[int, float, float], Row]]] = {}
    issues = []
    for candidate in candidates:
        try:
            row = candidate["row"]
            _size(row, MAX_BYTES)
            key = qualified_key(row)
            _provider_scalars(row)
            grouped.setdefault(key, []).append((_rank(candidate, now), row))
        except (ValueError, TypeError, KeyError, AttributeError):
            issues.append({"code": "invalid_reference"})
    return grouped, issues


def _version_rows(
    values: list[tuple[tuple[int, float, float], Row]],
) -> list[tuple[tuple[int, float, float], Row]]:
    version = max(rank[:2] for rank, row in values)
    return [(rank, row) for rank, row in values if rank[:2] == version]


def _incompatible(current: list[tuple[tuple[int, float, float], Row]]) -> bool:
    states = {row["state"] for rank, row in current if row.get("state")}
    heads = {row["headRefOid"] for rank, row in current if row.get("headRefOid")}
    return len(states) > 1 or len(heads) > 1


def _winner(values: list[tuple[tuple[int, float, float], Row]]) -> Row | None:
    current = _version_rows(values)
    if _incompatible(current):
        return None
    newest = max(rank for rank, row in current)
    winners = [row for rank, row in current if rank == newest]
    return winners[0] if all(row == winners[0] for row in winners) else None


def select_prs(
    candidates: Sequence[Row], prior: Sequence[Row], *, now: float
) -> Selection:
    _require(_stamp(now, now), "invalid_clock")
    retained: dict[Key, Row] = {}
    for row in prior:
        _size(row, MAX_BYTES)
        key = qualified_key(row)
        _require(key not in retained or retained[key] == row, "conflicting_prior")
        retained[key] = copy.deepcopy(row)
    grouped, issues = _group_candidates(candidates, now)
    for key, values in grouped.items():
        selected = _winner(values)
        if selected is None:
            issues.append({"code": "conflicting_records", "key": list(key)})
        else:
            retained[key] = copy.deepcopy(selected)
    return Selection([retained[k] for k in sorted(retained)], issues)


def _eligible_cache(
    row: Row, cached: Sequence[Row], now: float
) -> list[tuple[float, Row]]:
    eligible = []
    key = qualified_key(row)
    for observation in cached:
        try:
            old, stamp = observation["row"], observation["observed_at"]
            _require(_stamp(stamp, now) and now - stamp <= 300)
            _require(
                qualified_key(old) == key
                and bool(row.get("headRefOid"))
                and old.get("headRefOid") == row["headRefOid"]
            )
            _size(old, MAX_BYTES)
            eligible.append((stamp, old))
        except (ValueError, TypeError, KeyError):
            continue
    return eligible


def _review_fields(current: list[Row]) -> Row:
    result = {}
    enums = {
        "reviewDecision": {"APPROVED", "CHANGES_REQUESTED", "REVIEW_REQUIRED", ""},
        "mergeable": {"MERGEABLE", "CONFLICTING", "UNKNOWN"},
    }
    for name, allowed in enums.items():
        values = {
            old[name]
            for old in current
            if type(old.get(name)) is str and old[name] in allowed
        }
        if len(values) == 1:
            result[name] = next(iter(values))
    return result


def _cached_fields(row: Row, cached: Sequence[Row], now: float) -> Row:
    eligible = _eligible_cache(row, cached, now)
    if not eligible:
        return {}
    latest = max(stamp for stamp, old in eligible)
    return _review_fields([old for stamp, old in eligible if stamp == latest])


def _provider_scalars(row: Row) -> None:
    if "state" in row:
        _require(
            type(row["state"]) is str and row["state"] in ("open", "closed", "merged"),
            "invalid_metadata",
        )
    if "headRefOid" in row:
        core._sha(row["headRefOid"])
    if "headRefName" in row:
        _require(type(row["headRefName"]) is str, "invalid_metadata")


def _row_meta(row: Row, now: float) -> Row:
    _size(row, MAX_BYTES)
    qualified_key(row)
    _provider_scalars(row)
    meta = {
        name: copy.deepcopy(row[name])
        for name in ("number", "headRefName", "headRefOid")
        if name in row
    }
    if "state" in row:
        meta["state"] = row["state"].upper()
    if row.get("state") == "merged":
        _require(_stamp(core._date(row.get("mergedAt")), now), "invalid_metadata")
        if row.get("mergeCommit") is not None:
            _require(type(row["mergeCommit"]) is dict, "invalid_metadata")
            oid = core._sha(row["mergeCommit"].get("oid"))
            meta["mergeCommit"] = {"oid": oid}
    return meta


def bulk_meta(
    rows: Sequence[Row], cached: Sequence[Row], *, now: float
) -> dict[Key, Row]:
    _require(_stamp(now, now), "invalid_clock")
    return {
        qualified_key(row): _row_meta(row, now) | _cached_fields(row, cached, now)
        for row in rows
    }
