"""Explicit M4 handoffs use real Source helpers and invented caller data only."""

import json
from copy import copy
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path

import pytest
from dashboard_shadow_fixture import boundary
from test_dashboard_shadow import prior_input, run_shadow

from orchestra.dashboard.quality import board_digest
from orchestra.dashboard.shadow import ShadowObserver, ShadowRequest
from orchestra.dashboard.shadow_prior import PriorOwner
from orchestra.dashboard.shadow_store import CommitState, read_receipt


def test_profile_none_admits_the_actual_nonempty_boundary(tmp_path: Path) -> None:
    data = boundary()
    prior, witness, now = prior_input(
        (PriorOwner("synthetic", "atrium", tuple(data["tasks"])),)
    )
    data["ctx"].now = now.timestamp()
    directory = tmp_path / "shadow"
    directory.mkdir(mode=0o700)
    request = ShadowRequest("8" * 32, directory, 7200)
    observer = ShadowObserver()
    result = observer.observe_boundary(
        data["baseline"],
        data["candidate"],
        data["asm"],
        data["notes"],
        data["tasks"],
        shared_roots={"ctx": data["ctx"], "locals": data["locals"]},
        callbacks=data["callbacks"],
        prior=prior,
        witness=witness,
        profile=None,
        request=request,
    )
    assert request._consumed
    assert result["synthetic"]["steps_checked"]["check"] is True
    assert observer.pending.equivalent, observer.pending.differences


def test_seal_result_is_original_and_same_process_consumable(tmp_path: Path) -> None:
    _, observer, _, request = run_shadow(tmp_path)
    final = {"generated": "2026-10-27T13:00:00.000001Z", "items": []}
    result = observer.seal_after_publish(
        observer.pending, final["generated"], board_digest(final)
    )
    assert result.state is CommitState.COMMITTED
    assert observer.commit_result is result
    assert (
        read_receipt(request.directory, observer.commit_result.receipt)["verdict"]
        == "PASS"
    )
    repeat = observer.seal_after_publish(
        observer.pending, final["generated"], board_digest(final)
    )
    assert repeat.state is CommitState.NOT_COMMITTED
    assert observer.commit_result is result
    # NB1: copied capability is retained; JSON/replace without it is not trusted.
    assert read_receipt(request.directory, copy(result.receipt))["verdict"] == "PASS"
    fields = {
        key: value
        for key, value in asdict(result.receipt).items()
        if not key.startswith("_")
    }
    from_json = type(result.receipt)(**json.loads(json.dumps(fields)))
    for untrusted in (fields, from_json, replace(result.receipt)):
        with pytest.raises(ValueError, match="receipt"):
            read_receipt(request.directory, untrusted)


def publications():
    generated = "2026-10-27T11:00:00.000001Z"
    board = {
        "generated": generated,
        "items": [
            {
                "id": "opaque-324",
                "repo": "nexus",
                "slugs": [f"task-{i}" for i in range(8)],
                "pr": None,
                "children": [{"slug": f"task-{i}"} for i in range(5)],
            },
        ],
    }
    archive = {
        "generated": generated,
        "items": [
            {
                "id": "opaque-207",
                "repo": "nexus",
                "slugs": [],
                "pr": {
                    "number": 207,
                    "url": "https://github.com/matteocervelli/nexus/pull/207",
                },
            },
        ],
    }
    return board, archive


def project(
    board, archive, *, evidence=None, digest="a" * 64, coverage="live_and_terminal"
):
    from orchestra.dashboard import shadow_prior

    prior, _, _ = prior_input()
    return shadow_prior.project_prior_publications(
        board,
        archive,
        artifacts=prior.artifacts if evidence is None else evidence,
        board_digest=digest,
        coverage=coverage,
    )


def test_prior_projection_is_complete_metadata_not_current_expected():
    from orchestra.dashboard.shadow_prior import PriorWitness, derive_prior_bindings

    board, archive = publications()
    prior = project(board, archive)
    _, _, now = prior_input()
    witness = PriorWitness(prior, "d" * 64, now.replace(minute=30) - timedelta(hours=1))
    bindings = derive_prior_bindings(prior, witness, now=now, max_age=7200)
    assert [r["key"] for r in bindings[:8]] == [f"task-{i}" for i in range(8)]
    assert {r["owner"] for r in bindings[:8]} == {"opaque-324"}
    assert bindings[-1] == {
        "kind": "pr",
        "key": archive["items"][0]["pr"]["url"],
        "owner": "opaque-207",
    }
    current_expected = {"opaque-324": "different-current-output"}
    current_expected.clear()
    assert project(board, archive) == prior
    assert board["items"][0]["slugs"] == [f"task-{i}" for i in range(8)]


@pytest.mark.parametrize(
    "mutation",
    [
        "generation",
        "missing_slugs",
        "duplicate_id",
        "conflicting_task",
        "conflicting_pr",
        "unknown_repo",
        "foreign_owner",
        "number",
        "unknown_field",
        "forbidden",
        "partial",
        "artifact",
    ],
)
def test_prior_projection_rejects_incomplete_conflicting_or_untrusted_shape(mutation):
    from orchestra.dashboard.shadow_graph import ShadowBlocked

    board, archive = publications()
    kwargs = {}
    if mutation == "generation":
        archive["generated"] = "2026-10-27T10:00:00.000001Z"
    elif mutation == "missing_slugs":
        del board["items"][0]["slugs"]
    elif mutation == "duplicate_id":
        archive["items"][0]["id"] = "opaque-324"
    elif mutation == "conflicting_task":
        archive["items"][0]["slugs"] = ["task-0"]
    elif mutation == "conflicting_pr":
        board["items"][0]["pr"] = dict(archive["items"][0]["pr"])
    elif mutation == "unknown_repo":
        board["items"][0]["repo"] = "unregistered"
    elif mutation == "foreign_owner":
        archive["items"][0]["pr"]["url"] = "https://github.com/foreign/nexus/pull/207"
    elif mutation == "number":
        archive["items"][0]["pr"]["number"] = 208
    elif mutation in {"unknown_field", "forbidden"}:
        board["items"][0][
            "SYNTHETIC_PRIVATE_CANARY" if mutation == "unknown_field" else "auth"
        ] = object()
    elif mutation == "partial":
        kwargs["coverage"] = "live_only_partial"
    else:
        prior, _, _ = prior_input()
        kwargs["evidence"] = (
            replace(prior.artifacts[0], byte_count=10 * 1024 * 1024 + 1),
            prior.artifacts[1],
        )
    with pytest.raises(ShadowBlocked) as caught:
        project(board, archive, **kwargs)
    assert "SYNTHETIC_PRIVATE_CANARY" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("field", ["auth", "headers", "env", "transcript"])
def test_public_projection_rejects_secret_keys_without_accessing_values(field):
    class Secret:
        def __getattribute__(self, name):
            raise AssertionError("SYNTHETIC_PRIVATE_CANARY")

    board, archive = publications()
    board["items"][0][field] = Secret()
    with pytest.raises(Exception) as caught:
        project(board, archive)
    assert type(caught.value).__name__ == "ShadowBlocked"
    assert "SYNTHETIC_PRIVATE_CANARY" not in str(caught.value)


def test_projection_never_copies_reads_or_hashes_known_excluded_payloads():
    class Rich:
        def __getattribute__(self, name):
            raise AssertionError("SYNTHETIC_PRIVATE_CANARY")

    board, archive = publications()
    board["children"] = Rich()
    board["items"][0]["children"] = Rich()
    archive["items"][0]["pr"]["review"] = Rich()
    prior = project(board, archive)
    assert prior.owners[0].slugs == tuple(f"task-{i}" for i in range(8))
    assert "SYNTHETIC_PRIVATE_CANARY" not in repr(prior)


def test_projection_rejects_mapping_getters_and_nonexact_keys_without_callbacks():
    from collections.abc import Mapping

    from orchestra.dashboard.shadow_graph import ShadowBlocked

    class Getter(Mapping):
        def __getitem__(self, key):
            raise AssertionError("PRIVATE_VALUE")

        def __iter__(self):
            raise AssertionError("PRIVATE_ITERATOR")

        def __len__(self):
            raise AssertionError("PRIVATE_LENGTH")

    class Key(str):
        calls = 0
        armed = False

        def __hash__(self):
            if self.armed:
                self.calls += 1
                raise AssertionError("PRIVATE_KEY")
            return super().__hash__()

    board, archive = publications()
    with pytest.raises(ShadowBlocked):
        project(Getter(), archive)
    key = Key("unknown")
    board[key] = object()
    key.armed = True
    with pytest.raises(ShadowBlocked):
        project(board, archive)
    assert key.calls == 0


def test_actual_profile_factory_runs_after_consumption_before_baseline(
    tmp_path, monkeypatch
):
    import sys

    from orchestra.dashboard import shadow

    data = boundary()
    prior, witness, now = prior_input(
        (PriorOwner("synthetic", "atrium", tuple(data["tasks"])),)
    )
    data["ctx"].now = now.timestamp()
    request = ShadowRequest("9" * 32, tmp_path, 7200)
    original, phases = shadow.approved_profile, []
    code = data["baseline"].__code__

    def observe(frame, event, arg):
        if event == "call" and frame.f_code is code:
            phases.append("baseline")

    def factory(baseline, candidate, asm, ctx, callbacks):
        assert request._consumed and phases == []
        assert (
            asm is data["asm"] and ctx is data["ctx"] and callbacks is data["callbacks"]
        )
        phases.append("profile")
        return original(baseline, candidate, asm, ctx, callbacks)

    monkeypatch.setattr(shadow, "approved_profile", factory)
    observer = ShadowObserver()
    previous = sys.getprofile()
    sys.setprofile(observe)
    try:
        observer.observe_boundary(
            data["baseline"],
            data["candidate"],
            data["asm"],
            data["notes"],
            data["tasks"],
            shared_roots={"ctx": data["ctx"], "locals": data["locals"]},
            callbacks=data["callbacks"],
            prior=prior,
            witness=witness,
            profile=None,
            request=request,
        )
    finally:
        sys.setprofile(previous)
    assert phases == ["profile", "baseline"] and observer.pending.equivalent


@pytest.mark.parametrize(
    "state", [CommitState.NOT_COMMITTED, CommitState.COMMIT_UNKNOWN]
)
def test_first_failure_commit_result_is_retained_without_writer_retry(
    tmp_path, monkeypatch, state
):
    from orchestra.dashboard import shadow
    from orchestra.dashboard.shadow_store import CommitResult

    _, observer, _, _ = run_shadow(tmp_path)
    result, calls = CommitResult(state), []

    def commit(*args):
        calls.append(1)
        return result

    monkeypatch.setattr(shadow, "commit_receipt", commit)
    assert (
        observer.seal_after_publish(
            observer.pending, "2026-10-27T13:00:00.000001Z", "a" * 64
        )
        is result
    )
    observer.seal_after_publish(
        observer.pending, "2026-10-27T13:00:00.000001Z", "a" * 64
    )
    assert observer.commit_result is result and calls == [1]


def test_empty_projection_does_not_mint_a_witness_and_surrogates_do_not_bind():
    board, archive = publications()
    board["items"], archive["items"] = [], []
    prior = project(board, archive)
    assert prior.owners == ()
    board["items"] = [
        {
            "id": "opaque",
            "repo": "nexus",
            "slugs": [],
            "pr": None,
            "pr_no": 207,
            "links": {"pr": "https://github.com/matteocervelli/nexus/pull/207"},
        }
    ]
    assert project(board, archive).owners == (PriorOwner("opaque", "nexus", ()),)


@pytest.mark.parametrize("value", [True, "207", -1])
def test_projection_pr_number_requires_a_positive_exact_integer(value):
    from orchestra.dashboard.shadow_graph import ShadowBlocked

    board, archive = publications()
    archive["items"][0]["pr"]["number"] = value
    with pytest.raises(ShadowBlocked):
        project(board, archive)


def test_foreign_seal_never_replaces_the_original_commit_capability(tmp_path):
    _, observer, _, _ = run_shadow(tmp_path)
    foreign = replace(observer.pending)
    assert (
        observer.seal_after_publish(
            foreign, "2026-10-27T13:00:00.000001Z", "a" * 64
        ).state
        is CommitState.NOT_COMMITTED
    )
    assert observer.commit_result is None
    original = observer.seal_after_publish(
        observer.pending, "2026-10-27T13:00:00.000001Z", "a" * 64
    )
    assert original.state is CommitState.COMMITTED
    observer.seal_after_publish(foreign, "2026-10-27T13:00:00.000001Z", "a" * 64)
    assert observer.commit_result is original
    with pytest.raises(AttributeError):
        observer.commit_result = None
