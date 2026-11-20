from __future__ import annotations

import hashlib
import json
import runpy
from copy import deepcopy
from pathlib import Path

import pytest

from orchestra.dashboard import collector as core

FIXTURE = runpy.run_path(
    str(Path(__file__).parents[1] / "fixtures/collector_caller.py.txt")
)
NOW, payload, MemoryStore = (FIXTURE[k] for k in ("NOW", "payload", "MemoryStore"))
REPO = core.Repository("github.com", "matteocervelli", "synthetic")


def collected(*, now=NOW, state=None, budget=25, rows=True):
    def fetch(request):
        data = [payload(base=request.base)] if rows else []
        return core.Page(data, now, False)

    return core.collect(
        [REPO], fetch, now=now, freshness=900, budget=budget, state=state
    )


def snapshot():
    from orchestra.dashboard.collector_caller import Snapshot

    result = collected()
    lineage = {
        row["url"]: {
            "row_sha256": hashlib.sha256(
                json.dumps(
                    row, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()
            ).hexdigest(),
            "observed_at": NOW,
            "source": "collector",
        }
        for row in result.rows
    }
    return Snapshot(result.state, lineage, NOW)


@pytest.mark.parametrize(
    "remaining,expected", [(0, 0), (4, 0), (5, 0), (6, 1), (25, 20)]
)
def test_shared_budget_allowance_and_attempts(remaining, expected):
    from orchestra.dashboard.collector_caller import Budget, prepare_collection

    budget = Budget(remaining)
    assert budget.allowance == expected
    store = MemoryStore()
    calls = []

    def fetch(request):
        calls.append(request.cache_key)
        return core.Page([], NOW, False)

    result = prepare_collection(
        [REPO], budget, fetch, store.read, store.commit, now=NOW, clock=lambda: NOW
    )
    assert len(calls) == min(expected, 3)
    assert budget.attempts == len(calls) and budget.remaining == remaining - len(calls)
    assert result.receipt["attempts"] == len(calls)
    assert result.receipt["status"] == ("complete" if expected >= 3 else "partial")
    assert {name for name, limit in store.reads} == {"prs.json", "prs-rest-v1.json"}
    assert all(limit == 64 * 1024 * 1024 + 1 for name, limit in store.reads)
    if expected < 3:
        assert store.data["prs.json"] == b"[]"


@pytest.mark.parametrize("bad", [True, -1, 26, 1.5])
def test_budget_rejects_invalid_domain(bad):
    from orchestra.dashboard.collector_caller import Budget

    with pytest.raises(ValueError):
        Budget(bad)


def test_budget_cannot_claim_more_than25_total_units():
    from orchestra.dashboard.collector_caller import Budget

    with pytest.raises(ValueError):
        Budget(25, attempts=1)


def test_codec_roundtrip_all_core_state_and_lineage():
    from orchestra.dashboard.collector_caller import (
        decode_checkpoint,
        encode_checkpoint,
    )

    value = snapshot()
    # An unconsumed diagnostic cache page exercises Page.error and unknown next.
    request = core.Request(REPO.full_name, "main", "open", 2, None)
    value.state.pages[request.cache_key] = core.Page([], NOW, None, "rate_limit")
    next(iter(value.state.progress.values())).invalidated = True
    value.state.next_feed = 2
    original = deepcopy(value)
    raw = encode_checkpoint(value, [REPO], now=NOW)
    assert decode_checkpoint(raw, [REPO], now=NOW) == value
    assert value == original
    wire = json.loads(raw)
    assert wire["state"]["known"]
    assert all(
        isinstance(p["digests"], list) for p in wire["state"]["progress"].values()
    )
    assert all(
        p["digests"] == sorted(set(p["digests"]))
        for p in wire["state"]["progress"].values()
    )


def test_core_accepted_empty_error_string_roundtrips_without_normalization():
    from orchestra.dashboard.collector_caller import (
        decode_checkpoint,
        encode_checkpoint,
    )

    value = snapshot()
    key = next(iter(value.state.pages))
    page = value.state.pages[key]
    value.state.pages[key] = core.Page(page.rows, page.fetched_at, page.has_next, "")
    raw = encode_checkpoint(value, [REPO], now=NOW)
    assert decode_checkpoint(raw, [REPO], now=NOW) == value


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "scope",
        "core",
        "future_clock",
        "bool_cursor",
        "extra_key",
        "duplicate_digest",
        "prefix_rows",
        "lineage_version",
        "future_page",
    ],
)
def test_codec_rejects_inconsistent_wire(mutation):
    from orchestra.dashboard.collector_caller import (
        decode_checkpoint,
        encode_checkpoint,
    )

    data = json.loads(encode_checkpoint(snapshot(), [REPO], now=NOW))
    progress = next(iter(data["state"]["progress"].values()))
    if mutation == "schema":
        data["schema"] = 999
    if mutation == "scope":
        data["scope"] = ["foreign/synthetic"]
    if mutation == "core":
        data["core_sha256"] = "f" * 64
    if mutation == "future_clock":
        data["clock"] = NOW + 1
    if mutation == "bool_cursor":
        data["state"]["next_feed"] = True
    if mutation == "extra_key":
        data["unexpected"] = 1
    if mutation == "duplicate_digest":
        progress["digests"] *= 2
    if mutation == "prefix_rows":
        progress["rows"] = {}
    if mutation == "lineage_version":
        next(iter(data["lineage"].values()))["row_sha256"] = "e" * 64
    if mutation == "future_page":
        next(iter(data["state"]["pages"].values()))["fetched_at"] = NOW + 1
    with pytest.raises(ValueError):
        decode_checkpoint(json.dumps(data).encode(), [REPO], now=NOW)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema":1,"schema":1}',
        b'{"x":NaN}',
        b'{"x":1e999}',
        b"\xff",
        b"[" * 17 + b"]" * 17,
    ],
)
def test_codec_rejects_ambiguous_nonfinite_utf8_and_depth(raw):
    from orchestra.dashboard.collector_caller import decode_checkpoint

    with pytest.raises(ValueError):
        decode_checkpoint(raw, [REPO], now=NOW)


def test_large_integer_parse_and_encode_errors_have_fixed_codes():
    from orchestra.dashboard.collector_caller import (
        decode_checkpoint,
        encode_checkpoint,
    )

    with pytest.raises(ValueError, match=r"^invalid_json$"):
        decode_checkpoint(b'{"n":' + b"9" * 5000 + b"}", [REPO], now=NOW)
    value = snapshot()
    value.lineage = {}
    next(iter(value.state.known.values()))["large"] = 10**5000
    with pytest.raises(ValueError, match=r"^invalid_json$"):
        encode_checkpoint(value, [REPO], now=NOW)


def test_complete_document_limits_and_python_objects_fail_closed():
    from orchestra.dashboard.collector_caller import (
        decode_checkpoint,
        encode_checkpoint,
    )

    value = snapshot()
    raw = encode_checkpoint(value, [REPO], now=NOW)
    assert decode_checkpoint(raw, [REPO], now=NOW, limit=len(raw)) == value
    with pytest.raises(ValueError):
        encode_checkpoint(value, [REPO], now=NOW, limit=len(raw) - 1)
    with pytest.raises(ValueError):
        decode_checkpoint(raw, [REPO], now=NOW, limit=len(raw) - 1)
    row = next(iter(value.state.known.values()))
    row["arbitrary"] = object()
    with pytest.raises(ValueError):
        encode_checkpoint(value, [REPO], now=NOW)


@pytest.mark.parametrize("target", ["snapshot", "state"])
def test_unknown_record_attributes_are_rejected_not_silently_dropped(target):
    from orchestra.dashboard.collector_caller import encode_checkpoint

    value = snapshot()
    record = value if target == "snapshot" else value.state
    record.extra = "not-a-wire-field"
    with pytest.raises(ValueError):
        encode_checkpoint(value, [REPO], now=NOW)


def test_exact_utf8_bound_includes_short_json_control_escapes():
    from orchestra.dashboard.collector_caller import (
        decode_checkpoint,
        encode_checkpoint,
    )

    value = snapshot()
    # Unknown retained fields are admitted JSON; all copies preserve their values.
    next(iter(value.state.known.values()))["control"] = '\n\t\r\b\f"\\è'
    value.lineage = {}
    raw = encode_checkpoint(value, [REPO], now=NOW)
    assert encode_checkpoint(value, [REPO], now=NOW, limit=len(raw)) == raw
    assert decode_checkpoint(raw, [REPO], now=NOW) == value


@pytest.mark.parametrize("bad_now", [True, float("inf"), float("nan")])
def test_codec_rejects_invalid_validation_clock(bad_now):
    from orchestra.dashboard.collector_caller import encode_checkpoint

    with pytest.raises(ValueError):
        encode_checkpoint(snapshot(), [REPO], now=bad_now)


@pytest.mark.parametrize("field", ["error", "reason"])
def test_malformed_enumerations_raise_fixed_value_errors(field):
    from orchestra.dashboard.collector_caller import (
        decode_checkpoint,
        encode_checkpoint,
    )

    data = json.loads(encode_checkpoint(snapshot(), [REPO], now=NOW))
    target = "pages" if field == "error" else "progress"
    next(iter(data["state"][target].values()))[field] = []
    with pytest.raises(ValueError):
        decode_checkpoint(json.dumps(data).encode(), [REPO], now=NOW)


@pytest.mark.parametrize("direction", ["encode", "decode"])
def test_last_created_false_cannot_equal_the_epoch_timestamp(direction):
    from orchestra.dashboard.collector_caller import (
        Snapshot,
        decode_checkpoint,
        encode_checkpoint,
    )

    def attempt(request):
        return core.Page(
            [payload(base=request.base, created_at="1970-01-01T00:00:00Z")], NOW, False
        )

    result = core.collect([REPO], attempt, now=NOW, freshness=900, budget=25)
    value = Snapshot(result.state, {}, NOW)
    assert all(p.last_created == 0.0 for p in value.state.progress.values())
    if direction == "decode":
        wire = json.loads(encode_checkpoint(value, [REPO], now=NOW))
        next(iter(wire["state"]["progress"].values()))["last_created"] = False
        with pytest.raises(ValueError):
            decode_checkpoint(json.dumps(wire).encode(), [REPO], now=NOW)
    else:
        next(iter(value.state.progress.values())).last_created = False
        with pytest.raises(ValueError):
            encode_checkpoint(value, [REPO], now=NOW)


@pytest.mark.parametrize(
    "field,state,value",
    [
        ("createdAt", "open", "0001-01-01T00:00:00Z"),
        ("updatedAt", "open", "0001-01-01T00:00:00Z"),
        ("mergedAt", "open", "0001-01-01T00:00:00Z"),
        ("closedAt", "closed", "0001-01-01T00:00:00Z"),
        ("closedAt", "merged", "0001-01-01T00:00:00Z"),
        ("closedAt", "OPEN", "0001-01-01T00:00:00Z"),
        ("closedAt", "open", "0001-01-01T00:00:00.000Z"),
        ("closedAt", "open", "not-a-date"),
        ("closedAt", "open", "1969-12-31T23:59:59Z"),
        ("closedAt", "open", "2100-01-01T00:00:00Z"),
    ],
)
def test_legacy_exception_does_not_relax_other_dates_or_states(field, state, value):
    from orchestra.dashboard.collector_caller import Budget, prepare_collection

    legacy = FIXTURE["legacy_prior"]() | {
        "closedAt": None,
        "state": state,
        field: value,
    }
    store, budget = MemoryStore(), Budget(25)
    raw = store.data["prs.json"] = json.dumps([legacy]).encode()
    result = prepare_collection(
        [REPO],
        budget,
        lambda r: pytest.fail("invalid prior must not fetch"),
        store.read,
        store.commit,
        now=NOW,
        clock=lambda: NOW,
    )
    assert (result.receipt["status"], result.receipt["reason"]) == (
        "error",
        "load_error",
    )
    assert budget.attempts == 0 and store.writes == 0 and store.data["prs.json"] == raw


@pytest.mark.parametrize("direction", ["encode", "decode"])
def test_checkpoint_codec_remains_strict_about_go_zero_time(direction):
    from orchestra.dashboard.collector_caller import (
        Snapshot,
        decode_checkpoint,
        encode_checkpoint,
    )

    legacy = FIXTURE["legacy_prior"]()
    state = core.CollectionState(known={legacy["url"]: legacy | {"closedAt": None}})
    value = Snapshot(state, {}, NOW)
    if direction == "encode":
        state.known[legacy["url"]]["closedAt"] = legacy["closedAt"]
        with pytest.raises(ValueError):
            encode_checkpoint(value, [REPO], now=NOW)
    else:
        data = json.loads(encode_checkpoint(value, [REPO], now=NOW))
        data["state"]["known"][legacy["url"]]["closedAt"] = legacy["closedAt"]
        with pytest.raises(ValueError):
            decode_checkpoint(json.dumps(data).encode(), [REPO], now=NOW)


def test_invalid_checkpoint_is_not_normalized_as_legacy_prior():
    from orchestra.dashboard.collector_caller import (
        Budget,
        Snapshot,
        encode_checkpoint,
        prepare_collection,
    )

    legacy = FIXTURE["legacy_prior"]()
    value = Snapshot(
        core.CollectionState(known={legacy["url"]: legacy | {"closedAt": None}}),
        {},
        NOW,
    )
    data = json.loads(encode_checkpoint(value, [REPO], now=NOW))
    data["state"]["known"][legacy["url"]]["closedAt"] = legacy["closedAt"]
    store, budget = MemoryStore(), Budget(25)
    store.data["prs.json"] = json.dumps([legacy]).encode()
    store.data["prs-rest-v1.json"] = json.dumps(data).encode()
    before = dict(store.data)
    result = prepare_collection(
        [REPO],
        budget,
        lambda r: pytest.fail("corrupt checkpoint must not fetch"),
        store.read,
        store.commit,
        now=NOW,
        clock=lambda: NOW,
    )
    assert (result.receipt["status"], result.receipt["reason"]) == (
        "error",
        "load_error",
    )
    assert budget.attempts == 0 and store.writes == 0 and store.data == before


def test_last_good_rows_cannot_belong_to_another_approved_feed():
    from orchestra.dashboard.collector_caller import (
        Snapshot,
        decode_checkpoint,
        encode_checkpoint,
    )

    second = core.Repository("github.com", "matteocervelli", "second")
    repos = [REPO, second]

    def fetch(request):
        return core.Page(
            [payload(repository=request.repository.split("/")[1], base=request.base)],
            NOW,
            False,
        )

    result = core.collect(repos, fetch, now=NOW, freshness=900, budget=25)
    data = json.loads(
        encode_checkpoint(Snapshot(result.state, {}, NOW), repos, now=NOW)
    )
    first_key = result.coverage[0]["fingerprint"]
    second_key = next(
        c["fingerprint"] for c in result.coverage if c["repository"] == second.full_name
    )
    data["state"]["last_good"][first_key]["rows"] = data["state"]["last_good"][
        second_key
    ]["rows"]
    with pytest.raises(ValueError):
        decode_checkpoint(json.dumps(data).encode(), repos, now=NOW)


@pytest.mark.parametrize("cache_budget", [0, 5, 25])
def test_cache_hit_zero_charge_and_absence_does_not_refresh_known_lineage(cache_budget):
    from orchestra.dashboard.collector_caller import Budget, prepare_collection

    store = MemoryStore()
    first = prepare_collection(
        [REPO],
        Budget(25),
        lambda r: core.Page([payload(base=r.base)], NOW, False),
        store.read,
        store.commit,
        now=NOW,
        clock=lambda: NOW,
    )
    second_budget = Budget(cache_budget)
    second = prepare_collection(
        [REPO],
        second_budget,
        lambda r: pytest.fail("cache hit must not fetch"),
        store.read,
        store.commit,
        now=NOW + 1,
        clock=lambda: NOW + 1,
    )
    assert second_budget.attempts == 0 and second_budget.remaining == cache_budget
    assert second.rows == first.rows
    third = prepare_collection(
        [REPO],
        Budget(25),
        lambda r: core.Page([], NOW + 1000, False),
        store.read,
        store.commit,
        now=NOW + 1000,
        clock=lambda: NOW + 1000,
    )
    assert third.rows == first.rows
    assert next(iter(third.receipt["lineage"].values()))["observed_at"] == NOW


@pytest.mark.parametrize("failure", ["provider", "exception", "clock", "codec"])
def test_failures_keep_spent_counter_and_previous_bytes(failure):
    from orchestra.dashboard.collector_caller import Budget, prepare_collection

    budget = Budget(6)
    store = MemoryStore()
    before = dict(store.data)
    called = []

    def attempt(request):
        called.append(request.cache_key)
        if failure == "exception":
            raise TimeoutError("synthetic")
        if failure == "provider":
            return core.Page([], NOW, None, "unavailable")
        return core.Page([payload(base=request.base)], NOW, False)

    result = prepare_collection(
        [REPO],
        budget,
        attempt,
        store.read,
        store.commit,
        now=NOW,
        clock=lambda: float("nan") if failure == "clock" and called else NOW,
        limit=256 if failure == "codec" else 64 * 1024 * 1024,
    )
    assert called and budget.attempts == 1 and budget.remaining == 5
    assert store.data["prs.json"] == before["prs.json"]
    assert result.receipt["status"] != "complete"
    if failure in ("clock", "codec"):
        assert store.data == before and store.writes == 0


@pytest.mark.parametrize(
    "phase", ["before_stage", "checkpoint_staged", "mirror_staged"]
)
def test_staged_storage_faults_leave_both_previous_bytes(phase):
    from orchestra.dashboard.collector_caller import Budget, prepare_collection

    store = MemoryStore()
    previous = dict(store.data)
    store.fail = phase
    budget = Budget(25)
    result = prepare_collection(
        [REPO],
        budget,
        lambda r: core.Page([], NOW, False),
        store.read,
        store.commit,
        now=NOW,
        clock=lambda: NOW,
    )
    assert store.data == previous
    assert budget.attempts == 3 and budget.remaining == 22
    assert (
        result.receipt["status"] == "error"
        and result.receipt["reason"] == "storage_error"
    )
    store.fail = ""
    recovered = prepare_collection(
        [REPO],
        Budget(25),
        lambda r: core.Page([], NOW + 1, False),
        store.read,
        store.commit,
        now=NOW + 1,
        clock=lambda: NOW + 1,
    )
    assert recovered.receipt["status"] == "complete"


def test_corrupt_checkpoint_is_not_empty_complete_or_overwritten():
    from orchestra.dashboard.collector_caller import Budget, prepare_collection

    store = MemoryStore()
    store.data["prs-rest-v1.json"] = b'{"bad":true}'
    store.data["prs.json"] = json.dumps(collected().rows).encode()
    previous = dict(store.data)
    budget = Budget(25)
    result = prepare_collection(
        [REPO],
        budget,
        lambda r: pytest.fail("corrupt load must fail closed"),
        store.read,
        store.commit,
        now=NOW,
        clock=lambda: NOW,
    )
    assert result.rows == collected().rows and result.receipt["status"] == "error"
    assert store.data == previous and budget.attempts == 0
    assert set(result.receipt["lineage"]) == {r["url"] for r in result.rows}
    assert all(v["observed_at"] is None for v in result.receipt["lineage"].values())


def test_transport_double_charge_is_detected_without_refund():
    from orchestra.dashboard.collector_caller import Budget, prepare_collection

    store, budget = MemoryStore(), Budget(6)

    def attempt(request):
        budget.remaining -= 1  # an invalid transport wrapper would double debit
        return core.Page([], NOW, False)

    result = prepare_collection(
        [REPO], budget, attempt, store.read, store.commit, now=NOW, clock=lambda: NOW
    )
    assert budget.attempts == 1 and budget.remaining == 4
    assert result.receipt["status"] == "error" and store.writes == 0


def test_clock_advance_during_transport_makes_collection_stale():
    from orchestra.dashboard.collector_caller import Budget, prepare_collection

    store = MemoryStore()
    clock = [NOW]

    def attempt(request):
        clock[0] += 500
        return core.Page([], clock[0], False)

    result = prepare_collection(
        [REPO],
        Budget(25),
        attempt,
        store.read,
        store.commit,
        now=NOW,
        clock=lambda: clock[0],
    )
    assert result.receipt["status"] == "stale" and store.data["prs.json"] == b"[]"


@pytest.mark.parametrize("newline", ["\r\n", "\n"])
def test_response_decoder_is_pure_and_does_not_follow_next_url(newline):
    from orchestra.dashboard.collector_caller import decode_page

    text = newline.join(
        ["HTTP/2 200 OK", 'Link: <https://foreign.test/evil>; rel="next"', "", "[]"]
    )
    page = decode_page(text, 0, NOW)
    assert page == core.Page([], NOW, True)
    assert decode_page("HTTP/2 429 Limit\n\n{}", 1, NOW).error == "rate_limit"
    assert decode_page("HTTP/2 403 Forbidden\n\n{}", 1, NOW).error == "unavailable"
    assert decode_page("HTTP/2 200 OK\n\nNaN", 0, NOW).error == "invalid_json"


def test_non_http_envelope_cannot_be_valid_empty_observation():
    from orchestra.dashboard.collector_caller import decode_page

    assert decode_page("unexpected 200 OK\n\n[]", 0, NOW).error == "invalid_json"
    assert decode_page("HTTP/2.0 200 OK\n\n[]", 0, NOW) == core.Page([], NOW, False)
