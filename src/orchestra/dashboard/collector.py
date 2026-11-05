"""Bounded REST PR traversal with injected transport, clock, cache and budget."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

Row = dict[str, Any]
PAGE_SIZE = 100
MAX_PAGES = 100
MAX_BYTES = 2 * 1024 * 1024
MAX_BUDGET = 25
ERRORS = frozenset(
    {
        "invalid_observation_time",
        "provider_error",
        "invalid_payload",
        "pagination_unknown",
        "payload_limit",
        "repeated_page",
        "invalid_row",
        "invalid_number",
        "invalid_pr_url",
        "invalid_branch",
        "invalid_base",
        "invalid_timestamp",
        "invalid_state",
        "invalid_head",
        "invalid_field",
        "invalid_merge",
        "invalid_labels",
        "invalid_ordering",
        "conflicting_records",
        "rate_limit",
        "invalid_json",
        "unavailable",
        "timeout",
    }
)
RESUMABLE = frozenset(
    {
        "pending",
        "budget",
        "exhausted",
        "cutoff",
        "fetch_error",
        "provider_error",
        "rate_limit",
        "timeout",
        "unavailable",
        "invalid_json",
    }
)


@dataclass(frozen=True)
class Repository:
    host: str
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True)
class Request:
    repository: str
    base: str
    state: str
    page: int
    cutoff: str | None

    @property
    def endpoint(self) -> str:
        return f"repos/{self.repository}/pulls"

    @property
    def query(self) -> Row:
        return {
            "state": self.state,
            "base": self.base,
            "sort": "created",
            "direction": "desc",
            "per_page": PAGE_SIZE,
            "page": self.page,
        }

    @property
    def feed_key(self) -> str:
        return _digest(
            ["pr-rest/v1", self.repository, self.base, self.state, self.cutoff]
        )

    @property
    def cache_key(self) -> str:
        return f"{self.feed_key}:{self.page}"


@dataclass(frozen=True)
class Page:
    rows: object
    fetched_at: float
    has_next: bool | None
    error: str | None = None


@dataclass
class Progress:
    page: int = 1
    rows: dict[str, Row] = field(default_factory=dict)
    times: list[float] = field(default_factory=list)
    digests: set[str] = field(default_factory=set)
    last_created: float | None = None
    done: bool = False
    reason: str = "pending"
    invalidated: bool = False


@dataclass
class LastGood:
    rows: dict[str, Row]
    completed_at: float
    oldest_at: float


@dataclass
class CollectionState:
    pages: dict[str, Page] = field(default_factory=dict)
    progress: dict[str, Progress] = field(default_factory=dict)
    last_good: dict[str, LastGood] = field(default_factory=dict)
    next_feed: int = 0
    known: dict[str, Row] = field(default_factory=dict)


@dataclass
class Collection:
    rows: list[Row]
    coverage: list[Row]
    issues: list[Row]
    state: CollectionState
    budget_remaining: int


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _date(value: object) -> float:
    if not isinstance(value, str) or "T" not in value or len(value) > 40:
        raise ValueError("invalid_timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("invalid_timestamp")
    return parsed.timestamp()


def _text(value: object, limit: int = 500) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise ValueError("invalid_field")
    return value


def _scope(repositories: Sequence[Repository]) -> list[str]:
    names = []
    for repo in repositories:
        if (
            repo.host != "github.com"
            or repo.owner != "matteocervelli"
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", repo.name)
        ):
            raise ValueError("invalid_authority")
        if repo.full_name in names:
            raise ValueError("duplicate_authority")
        names.append(repo.full_name)
    if not names:
        raise ValueError("empty_scope")
    return names


def _plan(names: list[str], cutoff: str) -> list[Request]:
    _date(cutoff)
    return [
        Request(name, base, state, 1, cutoff if state == "all" else None)
        for name in names
        for base, state in (
            ("auto/integration", "open"),
            ("main", "open"),
            ("auto/integration", "all"),
        )
    ]


def _reference(raw: object, request: Request) -> Row:
    if not isinstance(raw, dict):
        raise ValueError("invalid_row")
    n = raw.get("number")
    if type(n) is not int or n < 1:
        raise ValueError("invalid_number")
    html = f"https://github.com/{request.repository}/pull/{n}"
    api = f"https://api.github.com/repos/{request.repository}/pulls/{n}"
    if raw.get("html_url") != html or raw.get("url") != api:
        raise ValueError("invalid_pr_url")
    _branches(raw, request)
    return raw


def _branches(raw: Row, request: Request) -> None:
    base, head = raw.get("base"), raw.get("head")
    if not isinstance(base, dict) or not isinstance(head, dict):
        raise ValueError("invalid_branch")
    if (
        base.get("ref") != request.base
        or not isinstance(base.get("repo"), dict)
        or base["repo"].get("full_name") != request.repository
    ):
        raise ValueError("invalid_base")


def _sha(value: object) -> str:
    sha = _text(value, 40)
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise ValueError("invalid_head")
    return sha


def _normalize(raw: object, request: Request) -> Row:
    raw = _reference(raw, request)
    head = raw["head"]
    created, updated = _date(raw.get("created_at")), _date(raw.get("updated_at"))
    if updated < created:
        raise ValueError("invalid_timestamp")
    state = _state(raw, request, created, updated)
    row = {
        "number": raw["number"],
        "url": raw["html_url"],
        "title": _text(raw.get("title")),
        "state": state,
        "createdAt": raw["created_at"],
        "updatedAt": raw["updated_at"],
        "closedAt": raw.get("closed_at"),
        "headRefName": _text(head.get("ref"), 255),
        "headRefOid": _sha(head.get("sha")),
        "repository": {
            "name": request.repository.split("/")[1],
            "nameWithOwner": request.repository,
        },
        "labels": _labels(raw.get("labels")),
    }
    return _content(row, raw, state)


def _content(row: Row, raw: Row, state: str) -> Row:
    if raw.get("body") is not None:
        if not isinstance(raw["body"], str):
            raise ValueError("invalid_field")
        row["body"] = raw["body"]
    if state == "merged":
        row["mergedAt"] = raw["merged_at"]
        merge = raw.get("merge_commit_sha")
        if merge is not None:
            row["mergeCommit"] = {"oid": _sha(merge)}
    return row


def _labels(value: object) -> list[Row]:
    if not isinstance(value, list) or any(not isinstance(x, dict) for x in value):
        raise ValueError("invalid_labels")
    return [{"name": _text(label.get("name"), 100)} for label in value]


def _state(raw: Row, request: Request, created: float, updated: float) -> str:
    state = raw.get("state")
    if state not in ("open", "closed") or (request.state == "open" and state != "open"):
        raise ValueError("invalid_state")
    if state == "open":
        if raw.get("merged_at") is not None or raw.get("closed_at") is not None:
            raise ValueError("invalid_state")
        return "open"
    if not created <= _date(raw.get("closed_at")) <= updated:
        raise ValueError("invalid_timestamp")
    if raw.get("merged_at") is not None:
        if not created <= _date(raw["merged_at"]) <= updated:
            raise ValueError("invalid_timestamp")
        return "merged"
    return "closed"


def _observed_at(stamp: float, now: float) -> bool:
    return type(stamp) in (float, int) and math.isfinite(stamp) and 0 <= stamp <= now


def _instant(clock: Callable[[], float] | None, minimum: float) -> float:
    value = minimum if clock is None else clock()
    if not _observed_at(value, value) or value < minimum:
        raise ValueError("invalid_clock")
    return value


def _envelope(page: Page, now: float) -> None:
    if not _observed_at(page.fetched_at, now):
        raise ValueError("invalid_observation_time")
    if page.error:
        code = page.error if page.error in ERRORS else "provider_error"
        raise ValueError(code)
    if not isinstance(page.rows, list) or len(page.rows) > PAGE_SIZE:
        raise ValueError("invalid_payload")
    if type(page.has_next) is not bool or (not page.rows and page.has_next):
        raise ValueError("pagination_unknown")
    if len(json.dumps(page.rows).encode()) > MAX_BYTES:
        raise ValueError("payload_limit")


def _validated(
    page: Page, request: Request, progress: Progress, now: float
) -> list[Row]:
    _envelope(page, now)
    digest = _digest(page.rows)
    if digest in progress.digests:
        raise ValueError("repeated_page")
    assert isinstance(page.rows, list)
    rows = [_normalize(row, request) for row in page.rows]
    _ordering(rows, progress)
    candidate = {row["url"]: row for row in rows}
    if len(candidate) != len(rows) or any(
        url in progress.rows and progress.rows[url] != row
        for url, row in candidate.items()
    ):
        raise ValueError("conflicting_records")
    return rows


def _ordering(rows: list[Row], progress: Progress) -> None:
    dates = [_date(row["createdAt"]) for row in rows]
    if dates != sorted(dates, reverse=True) or (
        dates and progress.last_created is not None and dates[0] > progress.last_created
    ):
        raise ValueError("invalid_ordering")


def _accept(page: Page, request: Request, progress: Progress, rows: list[Row]) -> None:
    progress.digests.add(_digest(page.rows))
    progress.times.append(page.fetched_at)
    if rows:
        progress.last_created = _date(rows[-1]["createdAt"])
    cutoff = _date(request.cutoff) if request.cutoff else float("-inf")
    for row in rows:
        if _date(row["createdAt"]) >= cutoff:
            progress.rows[row["url"]] = row
    old_page = bool(rows and all(_date(row["createdAt"]) < cutoff for row in rows))
    progress.done = not page.has_next or old_page
    progress.reason = (
        "cutoff" if old_page else "exhausted" if progress.done else "pending"
    )
    progress.page += 1


def _fresh(page: Page, now: float, freshness: float) -> bool:
    return _observed_at(page.fetched_at, now) and now - page.fetched_at <= freshness


def _turn(
    request: Request,
    progress: Progress,
    state: CollectionState,
    fetch: Callable[[Request], Page],
    now: float,
    freshness: float,
    budget: int,
    clock: Callable[[], float] | None,
) -> tuple[int, int, bool]:
    now = _instant(clock, now)
    if request.page > MAX_PAGES:
        progress.reason = "page_limit"
        return budget, 0, False
    page = state.pages.get(request.cache_key)
    calls = 0
    if page is None or not _fresh(page, now, freshness):
        if not budget:
            progress.reason = "budget"
            return budget, 0, False
        budget, calls = budget - 1, 1
        try:
            page = fetch(request)
        except Exception:
            progress.reason = "fetch_error"
            return budget, calls, False
    try:
        if not isinstance(page, Page):
            raise ValueError("invalid_envelope")
        rows = _validated(page, request, progress, _instant(clock, now))
    except (ValueError, TypeError, OverflowError) as error:
        progress.reason = str(error) if str(error) in ERRORS else "invalid_page"
        return budget, calls, False
    state.pages[request.cache_key] = copy.deepcopy(page)
    _accept(page, request, progress, rows)
    return budget, calls, not progress.done


def _prepare(
    feeds: list[Request], state: CollectionState, now: float, freshness: float
) -> None:
    for feed in feeds:
        previous = state.progress.get(feed.feed_key)
        if previous is None:
            state.progress[feed.feed_key] = Progress()
            continue
        stale = any(now - stamp > freshness for stamp in previous.times)
        invalid = previous.invalidated or previous.reason not in RESUMABLE
        if stale or invalid:
            prefix = feed.feed_key + ":"
            state.pages = {
                key: page
                for key, page in state.pages.items()
                if not key.startswith(prefix)
            }
            state.progress[feed.feed_key] = Progress()
        elif previous.done:
            state.progress[feed.feed_key] = Progress()


def _walk(
    feeds: list[Request],
    state: CollectionState,
    fetch: Callable[[Request], Page],
    now: float,
    freshness: float,
    budget: int,
    clock: Callable[[], float] | None,
) -> tuple[int, dict[str, int]]:
    active = set(range(len(feeds)))
    calls: dict[str, int] = {}
    resume = None
    _prepare(feeds, state, now, freshness)
    while active:
        index = state.next_feed % len(feeds)
        state.next_feed = (index + 1) % len(feeds)
        if index not in active:
            continue
        feed = feeds[index]
        progress = state.progress[feed.feed_key]
        request = Request(
            feed.repository, feed.base, feed.state, progress.page, feed.cutoff
        )
        budget, used, more = _turn(
            request, progress, state, fetch, now, freshness, budget, clock
        )
        calls[feed.feed_key] = calls.get(feed.feed_key, 0) + used
        if progress.reason == "budget" and resume is None:
            resume = index
        if not more:
            active.remove(index)
    if resume is not None:
        state.next_feed = resume
    return budget, calls


def _receipt(
    feed: Request,
    state: CollectionState,
    calls: dict[str, int],
    now: float,
    freshness: float,
) -> Row:
    progress = state.progress[feed.feed_key]
    stale = any(not 0 <= now - stamp <= freshness for stamp in progress.times)
    status = "stale" if stale else "complete" if progress.done else "partial"
    if not progress.done and progress.reason not in ("pending", "budget"):
        status = "error"
    good = state.last_good.get(feed.feed_key)
    return {
        "query": feed.query,
        "repository": feed.repository,
        "fingerprint": feed.feed_key,
        "status": status,
        "reason": progress.reason,
        "pages": len(progress.times),
        "calls": calls.get(feed.feed_key, 0),
        "rows_valid": len(progress.rows),
        "observed_exhausted": progress.done,
        "oldest_observation_at": min(progress.times) if progress.times else None,
        "last_complete_at": good.completed_at if good else None,
        "fallback_stale": bool(good and now - good.oldest_at > freshness),
    }


def _retained(rows: Sequence[Row], names: list[str]) -> dict[str, Row]:
    result: dict[str, Row] = {}
    for row in rows:
        n = row.get("number")
        repository = row.get("repository")
        repo = repository.get("nameWithOwner") if isinstance(repository, dict) else None
        if type(n) is not int or n < 1 or repo not in names:
            raise ValueError("invalid_retained_reference")
        if row.get("url") != f"https://github.com/{repo}/pull/{n}":
            raise ValueError("invalid_retained_reference")
        if row["url"] in result and result[row["url"]] != row:
            raise ValueError("conflicting_retained_reference")
        result[row["url"]] = copy.deepcopy(row)
    return result


def _observations(
    feeds: list[Request], state: CollectionState
) -> tuple[dict[str, Row], list[Row]]:
    observed: dict[str, Row] = {}
    issues = []
    conflicted: set[str] = set()
    for feed in feeds:
        progress = state.progress[feed.feed_key]
        for url, row in progress.rows.items():
            if url in conflicted:
                continue
            if url in observed and observed[url] != row:
                issues.append({"code": "conflicting_records", "url": url})
                conflicted.add(url)
                del observed[url]
            else:
                observed[url] = copy.deepcopy(row)
    return observed, issues


def _flag_conflicts(
    receipts: list[Row], state: CollectionState, issues: list[Row]
) -> None:
    urls = {issue["url"] for issue in issues}
    for receipt in receipts:
        progress = state.progress[receipt["fingerprint"]]
        affected = sorted(urls.intersection(progress.rows))
        if not affected:
            continue
        receipt["conflicts"] = affected
        progress.invalidated = True
        if receipt["status"] == "complete":
            receipt["scan_status"] = receipt["status"]
            receipt["scan_reason"] = receipt["reason"]
            receipt.update(status="partial", reason="conflicting_records")


def _output(
    feeds: list[Request],
    state: CollectionState,
    receipts: list[Row],
    retained: dict[str, Row],
    now: float,
) -> tuple[list[Row], list[Row]]:
    observed, issues = _observations(feeds, state)
    _flag_conflicts(receipts, state, issues)
    for feed, receipt in zip(feeds, receipts, strict=True):
        good = state.last_good.get(feed.feed_key)
        if good:
            for url, row in good.rows.items():
                retained.setdefault(url, copy.deepcopy(row))
        if receipt["status"] == "complete":
            progress = state.progress[feed.feed_key]
            state.last_good[feed.feed_key] = LastGood(
                copy.deepcopy(progress.rows), now, min(progress.times)
            )
            receipt["last_complete_at"] = now
    retained.update(observed)
    state.known = copy.deepcopy(retained)
    return sorted(retained.values(), key=lambda row: row["url"]), issues


def collect(
    repositories: Sequence[Repository],
    fetch_page: Callable[[Request], Page],
    *,
    now: float,
    freshness: float,
    budget: int,
    clock: Callable[[], float] | None = None,
    state: CollectionState | None = None,
    retained: Sequence[Row] = (),
    cutoff: str = "2026-10-13T00:00:00Z",
) -> Collection:
    """Collect explicit feeds, returning resumable state without persisting it."""
    numeric = all(
        type(v) in (float, int) and math.isfinite(v) for v in (now, freshness)
    )
    if (
        not numeric
        or type(budget) is not int
        or not 0 <= budget <= MAX_BUDGET
        or freshness <= 0
        or now < 0
    ):
        raise ValueError("invalid_collection_parameters")
    names = _scope(repositories)
    feeds = _plan(names, cutoff)
    working = copy.deepcopy(state) if state is not None else CollectionState()
    previous = _retained(list(working.known.values()), names)
    previous.update(_retained(retained, names))
    remaining, calls = _walk(feeds, working, fetch_page, now, freshness, budget, clock)
    now = _instant(clock, now)
    coverage = [_receipt(feed, working, calls, now, freshness) for feed in feeds]
    rows, issues = _output(feeds, working, coverage, previous, now)
    return Collection(rows, coverage, issues, working, remaining)
