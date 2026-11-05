from __future__ import annotations

import itertools
import json
import runpy
from asyncio import CancelledError
from copy import deepcopy
from pathlib import Path

import pytest

from orchestra.dashboard import collector as core

FIXTURE = runpy.run_path(
    str(Path(__file__).parents[1] / "fixtures/collector_caller.py.txt")
)
NOW, payload, MemoryStore = (FIXTURE[k] for k in ("NOW", "payload", "MemoryStore"))
REPO = core.Repository("github.com", "matteocervelli", "synthetic")


def row(number=1, **changes):
    request = core.Request(REPO.full_name, "auto/integration", "open", 1, None)
    return core._normalize(payload(number), request) | changes


def candidate(value, observed_at, source="collector"):
    return {"row": value, "observed_at": observed_at, "source": source}


def test_precedence_is_permutation_invariant_and_never_merges_provider_fields():
    from orchestra.dashboard.collector_caller import select_prs

    fresh = row(title="fresh", body="current", labels=[])
    old = row(title="old", body="outdated", labels=[{"name": "stale-label"}])
    values = [
        candidate(old, NOW - 1000, "health"),
        candidate(fresh, NOW),
        candidate(row(title="unknown"), None, "release"),
    ]
    before = deepcopy(values)
    for permutation in itertools.permutations(values):
        result = select_prs(permutation, [], now=NOW)
        assert result.rows == [fresh] and result.issues == []
    assert values == before


def test_newer_qualified_provider_version_wins_with_same_freshness_tier():
    from orchestra.dashboard.collector_caller import select_prs

    newer = row(updatedAt="2026-10-24T00:00:00Z", title="later real edit")
    result = select_prs(
        [candidate(row(), NOW), candidate(newer, NOW - 1, "health")], [], now=NOW
    )
    assert result.rows == [newer]


@pytest.mark.parametrize("have_prior", [False, True])
def test_conflicting_same_version_has_no_source_order_winner(have_prior):
    from orchestra.dashboard.collector_caller import select_prs

    previous = row(title="known")
    first, second = row(), row(headRefOid="c" * 40)
    for values in (
        [candidate(first, NOW), candidate(second, NOW)],
        [candidate(second, NOW), candidate(first, NOW)],
    ):
        result = select_prs(values, [previous] if have_prior else [], now=NOW)
        assert result.rows == ([previous] if have_prior else [])
        assert result.issues[0]["code"] == "conflicting_records"


def test_owner_host_repo_number_keys_never_coalesce():
    from orchestra.dashboard.collector_caller import select_prs

    github = row()
    foreign = row(
        url="https://github.com/foreign/synthetic/pull/1",
        repository={"name": "synthetic", "nameWithOwner": "foreign/synthetic"},
    )
    forgejo = row(url="https://git.adlimen.dev/matteocervelli/synthetic/pulls/1")
    result = select_prs(
        [candidate(r, NOW) for r in (github, foreign, forgejo)], [], now=NOW
    )
    assert {r["url"] for r in result.rows} == {
        r["url"] for r in (github, foreign, forgejo)
    }
    malformed = row(url="https://github.com/matteocervelli/other/pull/1")
    result = select_prs([candidate(malformed, NOW)], [github], now=NOW)
    assert result.rows == [github]
    assert result.issues[0]["code"] == "invalid_reference"


def test_prior_without_new_observation_survives_and_input_is_unchanged():
    from orchestra.dashboard.collector_caller import select_prs

    prior = [row()]
    before = deepcopy(prior)
    result = select_prs([], prior, now=NOW)
    assert result.rows == prior and prior == before


def test_conflicting_prior_is_rejected_instead_of_last_writer_wins():
    from orchestra.dashboard.collector_caller import select_prs

    with pytest.raises(ValueError):
        select_prs([], [row(), row(headRefOid="b" * 40)], now=NOW)


def test_525_bulk_rows_have_no_fanout_and_missing_fields_remain_unknown(monkeypatch):
    import socket
    import subprocess

    def forbidden(*args, **kwargs):
        pytest.fail("pure helper must not use transport or subprocess")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    from orchestra.dashboard.collector_caller import bulk_meta, qualified_key

    rows = [row(n) for n in range(1, 526)]
    original = deepcopy(rows)
    result = bulk_meta(rows, [], now=NOW)
    assert len(result) == 525
    for value in rows:
        meta = result[qualified_key(value)]
        assert meta["state"] == "OPEN" and meta["headRefOid"] == value["headRefOid"]
        assert (
            not {
                "reviewDecision",
                "mergeable",
                "closingIssuesReferences",
                "mergeCommit",
                "files",
                "baseRefName",
            }
            & meta.keys()
        )
    assert rows == original


@pytest.mark.parametrize(
    "age,head,owner,accepted",
    [
        (100, "a", "matteocervelli", True),
        (301, "a", "matteocervelli", False),
        (100, "b", "matteocervelli", False),
        (100, "a", "foreign", False),
    ],
)
def test_optional_meta_requires_qualified_head_and_fresh_observation(
    age, head, owner, accepted
):
    from orchestra.dashboard.collector_caller import bulk_meta, qualified_key

    selected = row()
    cached = row(
        headRefOid=head * 40,
        reviewDecision="APPROVED",
        mergeable="MERGEABLE",
        repository={"name": "synthetic", "nameWithOwner": owner + "/synthetic"},
        url=f"https://github.com/{owner}/synthetic/pull/1",
    )
    result = bulk_meta([selected], [candidate(cached, NOW - age, "cache")], now=NOW)
    meta = result[qualified_key(selected)]
    assert (meta.get("reviewDecision") == "APPROVED") is accepted
    assert (meta.get("mergeable") == "MERGEABLE") is accepted
    assert "closingIssuesReferences" not in meta


def test_reseed_from_selected_rows_keeps_matching_core_metadata():
    from orchestra.dashboard.collector_caller import (
        bulk_meta,
        qualified_key,
        select_prs,
    )

    selected = row(headRefOid="d" * 40, updatedAt="2026-10-24T00:00:00Z")
    old = row(headRefOid="a" * 40, reviewDecision="APPROVED")
    result = select_prs(
        [candidate(selected, NOW), candidate(old, NOW - 1000)], [], now=NOW
    )
    meta = bulk_meta(result.rows, [candidate(old, NOW - 1, "cache")], now=NOW)[
        qualified_key(selected)
    ]
    assert meta["headRefOid"] == selected["headRefOid"] and meta["state"] == "OPEN"
    assert "reviewDecision" not in meta


def test_malformed_optional_cache_is_ignored_without_claiming_approval():
    from orchestra.dashboard.collector_caller import bulk_meta, qualified_key

    selected = row()
    malformed = [candidate({}, NOW), candidate(row(reviewDecision={"bad": True}), NOW)]
    result = bulk_meta([selected], malformed, now=NOW)
    assert "reviewDecision" not in result[qualified_key(selected)]


def test_optional_cache_order_does_not_override_newer_review_with_older():
    from orchestra.dashboard.collector_caller import bulk_meta, qualified_key

    values = [
        candidate(row(reviewDecision="APPROVED"), NOW - 10),
        candidate(row(reviewDecision="CHANGES_REQUESTED"), NOW - 1),
    ]
    for ordering in itertools.permutations(values):
        result = bulk_meta([row()], ordering, now=NOW)
        assert result[qualified_key(row())]["reviewDecision"] == "CHANGES_REQUESTED"


def test_invalid_claimed_merge_fact_fails_closed():
    from orchestra.dashboard.collector_caller import bulk_meta

    with pytest.raises(ValueError):
        bulk_meta(
            [row(state="merged", mergedAt="not-a-date", mergeCommit={"oid": "bad"})],
            [],
            now=NOW,
        )


@pytest.mark.parametrize("changes", [{"state": {}}, {"headRefOid": []}])
def test_malformed_provider_scalars_cannot_replace_prior(changes):
    from orchestra.dashboard.collector_caller import select_prs

    prior = row()
    result = select_prs([candidate(row(**changes), NOW)], [prior], now=NOW)
    assert result.rows == [prior]
    assert result.issues == [{"code": "invalid_reference"}]


def test_serialized_conflict_preserves_invalidated_known_lastgood_and_recovers():
    from orchestra.dashboard.collector_caller import (
        Budget,
        decode_checkpoint,
        prepare_collection,
    )

    store = MemoryStore()
    context = {"now": NOW, "title": "known", "conflict": False}

    def attempt(request):
        if request.base == "main":
            return core.Page([], context["now"], False)
        title = request.state if context["conflict"] else context["title"]
        return core.Page([payload(title=title)], context["now"], False)

    first = prepare_collection(
        [REPO],
        Budget(25),
        attempt,
        store.read,
        store.commit,
        now=NOW,
        clock=lambda: context["now"],
    )
    previous_mirror = store.data["prs.json"]
    old = decode_checkpoint(store.data["prs-rest-v1.json"], [REPO], now=NOW)
    context.update(now=NOW + 1000, conflict=True)
    second = prepare_collection(
        [REPO],
        Budget(25),
        attempt,
        store.read,
        store.commit,
        now=context["now"],
        clock=lambda: context["now"],
    )
    restored = decode_checkpoint(
        store.data["prs-rest-v1.json"], [REPO], now=context["now"]
    )
    assert restored.state.known == old.state.known
    assert sum(p.invalidated for p in restored.state.progress.values()) == 2
    for key, good in old.state.last_good.items():
        if restored.state.progress[key].invalidated:
            assert restored.state.last_good[key] == good
    assert second.rows == first.rows and store.data["prs.json"] == previous_mirror
    assert next(iter(restored.lineage.values()))["observed_at"] == NOW
    context.update(now=NOW + 1001, conflict=False, title="new")
    recovered = prepare_collection(
        [REPO],
        Budget(25),
        attempt,
        store.read,
        store.commit,
        now=context["now"],
        clock=lambda: context["now"],
    )
    assert (
        recovered.receipt["status"] == "complete"
        and recovered.rows[0]["title"] == "new"
    )


def test_checkpoint_retains_prefix_then_recovers_real_shift_and_page_lineage():
    from orchestra.dashboard.collector_caller import Budget, prepare_collection

    old = [
        payload(n, state="closed", closed_at="2026-10-23T00:00:00Z")
        for n in range(300, 100, -1)
    ]
    context = {"now": NOW, "rows": old}
    store, calls = MemoryStore(), []

    def attempt(request):
        calls.append((request.state, request.page))
        if request.state == "open":
            return core.Page([], context["now"], False)
        start = (request.page - 1) * 100
        return core.Page(
            context["rows"][start : start + 100],
            context["now"],
            start + 100 < len(context["rows"]),
        )

    first = prepare_collection(
        [REPO],
        Budget(8),
        attempt,
        store.read,
        store.commit,
        now=NOW,
        clock=lambda: context["now"],
    )
    assert first.receipt["status"] == "partial" and len(first.rows) == 100
    changed = deepcopy(old)
    next(r for r in changed if r["number"] == 201)["title"] = "updated boundary"
    context.update(
        now=NOW + 120,
        rows=[payload(301, state="closed", closed_at="2026-10-23T00:00:00Z"), *changed],
    )
    failed = prepare_collection(
        [REPO],
        Budget(25),
        attempt,
        store.read,
        store.commit,
        now=context["now"],
        clock=lambda: context["now"],
    )
    assert failed.receipt["status"] == "error" and failed.rows == first.rows
    context["now"] += 120
    start = len(calls)
    recovered = prepare_collection(
        [REPO],
        Budget(25),
        attempt,
        store.read,
        store.commit,
        now=context["now"],
        clock=lambda: context["now"],
    )
    assert recovered.receipt["status"] == "complete" and len(recovered.rows) == 201
    assert [p for p in calls[start:] if p[0] == "all"] == [
        ("all", 1),
        ("all", 2),
        ("all", 3),
    ]
    assert (
        next(r for r in recovered.rows if r["number"] == 201)["title"]
        == "updated boundary"
    )


def test_normal_cadence_82_attempts_under20_needs5_runs_without_false_complete():
    from orchestra.dashboard.collector_caller import Budget, prepare_collection

    repos = [
        core.Repository("github.com", "matteocervelli", f"synthetic-{n}")
        for n in range(27)
    ]
    store = MemoryStore()
    now = [NOW]
    calls = []

    def attempt(request):
        calls.append((request.cache_key, now[0]))
        if request.repository.endswith("/synthetic-0") and request.state == "all":
            numbers = range(1, 101) if request.page == 1 else [101]
            values = [
                payload(
                    n,
                    repository="synthetic-0",
                    state="closed",
                    closed_at="2026-10-24T00:00:00Z",
                    updated_at="2026-10-24T00:00:00Z",
                )
                for n in numbers
            ]
            return core.Page(values, now[0], request.page == 1)
        return core.Page([], now[0], False)

    statuses = []
    spent = []
    for tick in range(5):
        now[0] = NOW + tick * 120
        budget = Budget(25)
        result = prepare_collection(
            repos,
            budget,
            attempt,
            store.read,
            store.commit,
            now=now[0],
            clock=lambda: now[0],
        )
        statuses.append(result.receipt["status"])
        spent.append(budget.attempts)
        if tick < 4:
            assert store.data["prs.json"] == b"[]"
    assert statuses == ["partial"] * 4 + ["complete"]
    assert spent == [20] * 4 + [2] and len(calls) == 82
    assert len(result.rows) == 101
    second_page_time = next(stamp for key, stamp in calls if key.endswith(":2"))
    url = "https://github.com/matteocervelli/synthetic-0/pull/101"
    assert result.receipt["lineage"][url]["observed_at"] == second_page_time


@pytest.mark.parametrize("site", ["prior_read", "checkpoint_read", "commit"])
@pytest.mark.parametrize(
    "exception,handled",
    [
        (RuntimeError, True),
        (SystemExit, False),
        (KeyboardInterrupt, False),
        (CancelledError, False),
    ],
)
def test_storage_exception_boundaries_preserve_control_and_private_text(
    site, exception, handled
):
    from orchestra.dashboard.collector_caller import Budget, prepare_collection

    marker = "SYNTHETIC_PRIVATE_STORAGE_SENTINEL"
    store, budget = MemoryStore(), Budget(25)
    before = dict(store.data)
    reads, commits = [], []

    def read(name, limit):
        reads.append(name)
        if (name == "prs.json" and site == "prior_read") or (
            name == "prs-rest-v1.json" and site == "checkpoint_read"
        ):
            raise exception(marker)
        return store.read(name, limit)

    def commit(checkpoint, mirror):
        commits.append((checkpoint, mirror))
        if site == "commit":
            raise exception(marker)  # atomic callback: no bytes published
        store.commit(checkpoint, mirror)

    def prepare():
        return prepare_collection(
            [REPO],
            budget,
            lambda r: core.Page([], NOW, False),
            read,
            commit,
            now=NOW,
            clock=lambda: NOW,
        )

    if handled:
        result = prepare()
        assert result.receipt["status"] == "error"
        assert result.receipt["reason"] == (
            "storage_error" if site == "commit" else "load_error"
        )
        assert result.receipt["checkpoint_saved"] is False
        assert result.receipt["mirror_saved"] is False
        # A failed first read cannot expose bytes it never obtained or retry it.
        assert result.mirror == (None if site == "prior_read" else before["prs.json"])
        assert marker not in json.dumps(result.receipt)
    else:
        with pytest.raises(exception):
            prepare()
    expected = 3 if site == "commit" else 0
    assert budget.attempts == expected and budget.remaining == 25 - expected
    assert len(commits) == int(site == "commit")
    assert reads == (
        ["prs.json"] if site == "prior_read" else ["prs.json", "prs-rest-v1.json"]
    )
    assert store.data == before


@pytest.mark.parametrize(
    "available,status,attempts,failure",
    [
        (0, "partial", 0, ""),
        (6, "partial", 1, ""),
        (25, "complete", 3, ""),
        (25, "error", 3, "mirror_staged"),
    ],
)
def test_legacy_zero_closed_time_is_private_unknown_until_complete(
    available, status, attempts, failure
):
    from orchestra.dashboard.collector_caller import Budget, prepare_collection

    original = FIXTURE["legacy_prior"]()
    original["opaque_note"] = "0001-01-01T00:00:00Z"
    raw = json.dumps([original], indent=2).encode()
    store, budget = MemoryStore(), Budget(available)
    store.data["prs.json"], store.fail = raw, failure
    result = prepare_collection(
        [REPO],
        budget,
        lambda r: core.Page([], NOW, False),
        store.read,
        store.commit,
        now=NOW,
        clock=lambda: NOW,
    )
    assert result.receipt["status"] == status
    assert budget.attempts == attempts and budget.remaining == available - attempts
    assert result.rows == [original | {"closedAt": None}]
    assert original["closedAt"] == "0001-01-01T00:00:00Z"
    assert result.receipt["lineage"][original["url"]]["observed_at"] is None
    if status == "complete":
        assert json.loads(store.data["prs.json"]) == result.rows
    else:
        assert store.data["prs.json"] == raw and result.mirror == raw


def test_legacy_zero_time_warm_checkpoint_resume_and_cache_hit():
    from orchestra.dashboard.collector_caller import (
        Budget,
        decode_checkpoint,
        prepare_collection,
    )

    original = FIXTURE["legacy_prior"]()
    store, current = MemoryStore(), [NOW]
    raw = store.data["prs.json"] = json.dumps([original], indent=2).encode()

    def run(available):
        budget = Budget(available)
        result = prepare_collection(
            [REPO],
            budget,
            lambda r: core.Page([], current[0], False),
            store.read,
            store.commit,
            now=current[0],
            clock=lambda: current[0],
        )
        return result, budget

    first, initial_budget = run(6)
    assert first.receipt["status"] == "partial" and initial_budget.attempts == 1
    assert store.data["prs.json"] == raw
    saved = decode_checkpoint(store.data["prs-rest-v1.json"], [REPO], now=NOW)
    assert saved.state.known[original["url"]]["closedAt"] is None
    current[0] += 120
    second, resumed = run(25)
    assert second.receipt["status"] == "complete" and resumed.attempts == 2
    assert second.receipt["lineage"][original["url"]]["observed_at"] is None
    current[0] += 120
    third, warm = run(0)
    assert third.receipt["status"] == "complete" and warm.attempts == 0
    assert third.rows == [original | {"closedAt": None}]


@pytest.mark.parametrize("invalid", [None, True, 7, "not-an-object", []])
def test_legacy_prior_members_must_be_objects_before_core(invalid):
    from orchestra.dashboard.collector_caller import Budget, prepare_collection

    store, budget = MemoryStore(), Budget(25)
    raw = store.data["prs.json"] = json.dumps([invalid]).encode()
    result = prepare_collection(
        [REPO],
        budget,
        lambda r: pytest.fail("bad prior must not fetch"),
        store.read,
        store.commit,
        now=NOW,
        clock=lambda: NOW,
    )
    assert (result.receipt["status"], result.receipt["reason"]) == (
        "error",
        "load_error",
    )
    assert budget.attempts == 0 and budget.remaining == 25 and store.writes == 0
    assert store.data["prs.json"] == raw
