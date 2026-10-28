"""Prior ownership and normal-call preservation use synthetic caller handoffs."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from orchestra.dashboard.shadow_graph import ShadowBlocked
from orchestra.dashboard.shadow_prior import (
    Artifact,
    PriorBindingInput,
    PriorOwner,
    PriorWitness,
    derive_prior_bindings,
)


def prior_input(owners=()):
    now = datetime(2026, 10, 27, 12, tzinfo=UTC)
    prior = PriorBindingInput(
        generated="2026-10-27T11:00:00.000001Z",
        board_digest="a" * 64,
        artifacts=(
            Artifact("work-items.json", "b" * 64, 100),
            Artifact("work-items-archive.json", "c" * 64, 100),
        ),
        coverage="live_and_terminal",
        owners=tuple(owners),
    )
    witness = PriorWitness(prior, "d" * 64, now - timedelta(minutes=30))
    return prior, witness, now


def test_prior_empty_is_valid_and_distinct_from_missing() -> None:
    prior, witness, now = prior_input()
    assert derive_prior_bindings(prior, witness, now=now, max_age=7200) == []
    with pytest.raises(ShadowBlocked, match="prior_missing"):
        derive_prior_bindings(None, None, now=now, max_age=7200)


def test_prior_exact_task_and_qualified_pr_only() -> None:
    url = "https://github.com/matteocervelli/nexus/pull/207"
    prior, witness, now = prior_input(
        (PriorOwner("opaque-324", "nexus", ("synthetic",), 207, url),)
    )
    assert derive_prior_bindings(prior, witness, now=now, max_age=7200) == [
        {"kind": "task", "key": "synthetic", "owner": "opaque-324"},
        {"kind": "pr", "key": url, "owner": "opaque-324"},
    ]
    assert prior.owners[0].id == "opaque-324"


@pytest.mark.parametrize(
    "mutation",
    ["foreign", "conflict", "partial", "future", "stale", "witness", "artifact"],
)
def test_prior_negative_is_atomic(mutation: str) -> None:
    owner = PriorOwner("opaque-324", "nexus", ("synthetic",))
    prior, witness, now = prior_input((owner,))
    if mutation == "foreign":
        prior = replace(
            prior,
            owners=(
                replace(
                    owner,
                    repo="foreign/nexus",
                    pr_number=207,
                    pr_url="https://github.com/matteocervelli/nexus/pull/207",
                ),
            ),
        )
    elif mutation == "conflict":
        prior = replace(prior, owners=(owner, replace(owner, id="other")))
    elif mutation == "partial":
        prior = replace(prior, coverage="live_only_partial")
    elif mutation == "future":
        now -= timedelta(days=1)
    elif mutation == "stale":
        now += timedelta(days=1)
    elif mutation == "artifact":
        prior = replace(prior, artifacts=(prior.artifacts[0],))
    # Only an independently handed-off exact input is witnessed.
    if mutation != "witness":
        witness = replace(witness, prior=prior)
    else:
        witness = replace(witness, prior=replace(prior))
    with pytest.raises(ShadowBlocked, match="prior_invalid"):
        derive_prior_bindings(prior, witness, now=now, max_age=7200)
    assert owner.slugs == ("synthetic",)


def test_default_off_calls_only_baseline_and_preserves_exception(monkeypatch) -> None:
    import orchestra.dashboard.shadow as module
    from orchestra.dashboard.shadow import ShadowObserver

    calls = []

    def baseline(asm, notes, tasks):
        calls.append((asm, notes, tasks))
        return notes

    def forbidden(*args, **kwargs):
        raise AssertionError("observer touched")

    monkeypatch.setattr(module, "Graph", forbidden)
    observer = ShadowObserver()
    marker = object()
    assert (
        observer.observe_boundary(
            baseline,
            forbidden,
            marker,
            marker,
            marker,
            shared_roots=marker,
            callbacks=marker,
            prior=marker,
            witness=marker,
            profile=marker,
        )
        is marker
    )
    assert len(calls) == 1 and observer.pending is None
    error = RuntimeError("synthetic producer error")

    def raises(*args):
        raise error

    with pytest.raises(RuntimeError) as caught:
        observer.observe_boundary(
            raises,
            forbidden,
            marker,
            marker,
            marker,
            shared_roots=marker,
            callbacks=marker,
            prior=marker,
            witness=marker,
            profile=marker,
        )
    assert caught.value is error


def test_full_real_nonempty_boundary_and_publish_commit(tmp_path) -> None:
    from dashboard_shadow_fixture import boundary

    from orchestra.dashboard.shadow import ShadowObserver, ShadowRequest
    from orchestra.dashboard.shadow_profile import approved_profile
    from orchestra.dashboard.shadow_store import CommitState, read_receipt

    data = boundary()
    prior, witness, now = prior_input(
        (PriorOwner("synthetic", "atrium", tuple(data["tasks"])),)
    )
    data["ctx"].now = now.timestamp()
    root = tmp_path / "shadow"
    root.mkdir(mode=0o700)
    request = ShadowRequest("1" * 32, root, 7200)
    profile = approved_profile(
        data["baseline"], data["candidate"], data["asm"], data["ctx"], data["callbacks"]
    )
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
        profile=profile,
        request=request,
    )
    assert result["synthetic"]["steps_checked"]["check"] is True
    assert len(data["asm"].items["synthetic"]["children"]) == 2
    assert (
        sum(child["cost"] for child in data["asm"].items["synthetic"]["children"]) == 2
    )
    assert observer.pending is not None
    assert observer.pending.equivalent is True, observer.pending.differences
    committed = observer.seal_after_publish(
        observer.pending, "2026-10-27T12:01:00.000001Z", "f" * 64
    )
    assert committed.state is CommitState.COMMITTED
    receipt = read_receipt(root, committed.receipt)
    assert receipt["verdict"] == "PASS" and all(receipt["coverage"].values())
    assert receipt["counts"]["callbacks"] == 2
    serialized = str(receipt)
    assert (
        "synthetic opaque alpha" not in serialized
        and "synthetic opaque beta" not in serialized
    )


def run_shadow(tmp_path, data=None, *, swap=None):
    from dashboard_shadow_fixture import boundary

    from orchestra.dashboard.shadow import ShadowObserver, ShadowRequest
    from orchestra.dashboard.shadow_profile import approved_profile

    data = data or boundary()
    prior, witness, now = prior_input(
        (PriorOwner("synthetic", "atrium", tuple(data["tasks"])),)
    )
    data["ctx"].now = now.timestamp()
    profile = approved_profile(
        data["baseline"], data["candidate"], data["asm"], data["ctx"], data["callbacks"]
    )
    if swap is not None:
        swap(data)
    root = tmp_path / "shadow"
    root.mkdir(mode=0o700)
    request = ShadowRequest("2" * 32, root, 7200)
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
        profile=profile,
        request=request,
    )
    return data, observer, result, request


@pytest.mark.parametrize("mode,expected", [("same", 1), ("equal", 1), ("different", 2)])
def test_e1_real_native_child_report_multiplicity(tmp_path, mode, expected) -> None:
    from dashboard_shadow_fixture import boundary

    left = "".join(["synthetic", " report alpha"])
    right = (
        left
        if mode == "same"
        else "".join(
            ["synthetic", " report alpha" if mode == "equal" else " report beta"]
        )
    )
    if mode == "equal":
        assert right is not left and right == left
    data, observer, _, _ = run_shadow(tmp_path, boundary((left, right)))
    assert observer.pending.equivalent, observer.pending.differences
    children = data["asm"].items["synthetic"]["children"]
    assert (
        len(children) == expected and sum(row["cost"] for row in children) == expected
    )
    assert children[0]["report"] is left


@pytest.mark.parametrize("role", ["candidate", "baseline", "callback"])
def test_post_approval_swap_blocks_unattested_candidate(tmp_path, role) -> None:
    calls = []

    def fake_candidate(*args, **kwargs):
        calls.append("candidate")
        return {}

    def fake_baseline(asm, notes, tasks):
        calls.append("baseline")
        return notes

    def swap(data):
        if role == "candidate":
            data["candidate"] = fake_candidate
        elif role == "baseline":
            data["baseline"] = fake_baseline
        else:
            data["callbacks"]["effective_note"] = lambda *args: {}

    _, observer, _, _ = run_shadow(tmp_path, swap=swap)
    assert "candidate" not in calls
    assert calls.count("baseline") == int(role == "baseline")
    assert not observer.pending.equivalent
    assert observer.pending.differences[0]["code"] == "callable_drift"


@pytest.mark.parametrize("field", ["transcript", "auth", "headers", "env", "report"])
def test_forbidden_nested_input_blocks_and_normal_baseline_continues(
    tmp_path, field
) -> None:
    def inject(data):
        data["notes"]["synthetic"][field] = "PRIVATE_SENTINEL"

    _, observer, result, _ = run_shadow(tmp_path, swap=inject)
    assert result
    assert not observer.pending.equivalent
    assert observer.pending.differences[0]["code"] in {"forbidden", "root_schema"}
    assert "PRIVATE_SENTINEL" not in str(observer.pending.differences)


def test_default_off_does_not_open_pin_table_or_private_storage(monkeypatch) -> None:
    from pathlib import Path

    from orchestra.dashboard.shadow import ShadowObserver

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected file operation")

    monkeypatch.setattr(Path, "open", forbidden)
    notes = {"synthetic": {}}
    assert (
        ShadowObserver().observe_boundary(
            lambda *args: notes,
            object(),
            object(),
            notes,
            {},
            shared_roots=object(),
            callbacks=object(),
            prior=object(),
            witness=object(),
            profile=object(),
        )
        is notes
    )


def test_borrowed_global_cannot_alias_mutable_business_root(tmp_path) -> None:
    def swap(data):
        data["ctx"].acted = data["source"]["wi_assembly"]["_DETACHED"]

    _, observer, _, _ = run_shadow(tmp_path, swap=swap)
    assert not observer.pending.equivalent
    assert observer.pending.differences[0]["code"] == "global_drift"


@pytest.mark.parametrize("field", ["transcript", "auth", "headers", "env", "report"])
def test_privacy_negative_never_exports_unvalidated_payload(tmp_path, field) -> None:
    from orchestra.dashboard.shadow_store import CommitState, read_receipt

    def inject(data):
        data["notes"]["synthetic"][field] = "PRIVATE_SENTINEL"

    _, observer, _, request = run_shadow(tmp_path, swap=inject)
    pending = observer.pending
    assert pending.differences[0]["count"] >= 1
    assert pending.differences[0]["path"].startswith("$roots.")
    assert field not in pending.differences[0]["path"]
    result = observer.seal_after_publish(
        pending, "2026-10-27T12:01:00.000001Z", "f" * 64
    )
    assert result.state is CommitState.COMMITTED
    receipt = read_receipt(request.directory, result.receipt)
    assert receipt["verdict"] == "BLOCK" and not receipt["coverage"]["roots"]
    assert (
        b"PRIVATE_SENTINEL"
        not in (request.directory / "receipts" / result.receipt.final_name).read_bytes()
    )


def test_permitted_opaque_report_sentinel_absent_from_committed_receipt(
    tmp_path,
) -> None:
    from dashboard_shadow_fixture import boundary

    from orchestra.dashboard.shadow_store import read_receipt

    sentinel = "PRIVATE_REPORT_SENTINEL"
    _, observer, _, request = run_shadow(
        tmp_path, boundary((sentinel, "synthetic other"))
    )
    assert observer.pending.equivalent
    result = observer.seal_after_publish(
        observer.pending, "2026-10-27T12:01:00.000001Z", "f" * 64
    )
    payload = read_receipt(request.directory, result.receipt)
    assert payload["verdict"] == "PASS"
    assert (
        sentinel.encode()
        not in (request.directory / "receipts" / result.receipt.final_name).read_bytes()
    )


def test_full_boundary_records_actual_all_pr_roster_and_warm_probe(tmp_path) -> None:
    from dashboard_shadow_fixture import boundary

    data = boundary()
    row = {
        "repository": {"name": "nexus"},
        "number": 207,
        "url": "https://github.com/matteocervelli/nexus/pull/207",
        "state": "OPEN",
        "title": "synthetic",
        "body": "",
    }
    data["asm"].pr_by = {("nexus", 207): row}
    data["locals"]["all_prs"] = [row]
    data["asm"].probes._memo[("meta", "nexus")] = {
        207: {"number": 207, "state": "OPEN"}
    }
    _, observer, _, _ = run_shadow(tmp_path, data)
    assert observer.pending.equivalent, observer.pending.differences
    assert observer.pending.counts["probes"] == 2
    assert observer.pending.counts["callbacks"] == 6


@pytest.mark.parametrize(
    "method,args,memo,ancestry",
    [
        ("pr_meta", ("nexus",), {("meta", "nexus"): {}}, {}),
        (
            "main_contains",
            ("nexus", "a" * 40),
            {},
            {"nexus:" + "a" * 40 + ":main": True},
        ),
        (
            "tag_contains",
            ("ratio", "a" * 40, "v*"),
            {},
            {"ratio:" + "a" * 40 + ":tag:v*": True},
        ),
        (
            "is_ancestor",
            ("nexus", "a" * 40, "b" * 40),
            {},
            {"nexus:" + "a" * 40 + ":" + "b" * 40: False},
        ),
        (
            "is_ancestor",
            ("nexus", "a" * 40, "b" * 40, False),
            {("anc", "nexus:" + "a" * 40 + ":" + "b" * 40): None},
            {},
        ),
        ("atrium_version", (), {"atrium": ""}, {}),
        ("deploy_shas", ("nexus",), {("fj", "nexus"): ["a" * 40]}, {}),
    ],
)
def test_candidate_uses_actual_warm_probe_body_and_preserves_frame(
    method, args, memo, ancestry
) -> None:
    from dashboard_shadow_fixture import boundary

    from orchestra.dashboard.shadow_graph import Graph
    from orchestra.dashboard.shadow_probe import Recorder

    data = boundary()
    probe = data["asm"].probes
    probe._memo, probe._anc = memo, ancestry
    graph = Graph({"Probe": type(probe)})
    before = graph.clone(probe, "Probe")
    recorder = Recorder(candidate=True, opaque=set(), classes={"Probe": type(probe)})
    with recorder.loan(data["asm"], data["callbacks"]):
        result = getattr(probe, method)(*args)
    assert len(recorder.events) == 1
    if method == "pr_meta":
        assert result is memo[("meta", "nexus")]
    if method == "deploy_shas":
        assert result is memo[("fj", "nexus")]
    assert graph.equivalent(before, probe)


@pytest.mark.parametrize(
    "method,args",
    [
        ("pr_meta", ("nexus",)),
        ("main_contains", ("nexus", "a" * 40)),
        ("tag_contains", ("ratio", "a" * 40, "v*")),
        ("is_ancestor", ("nexus", "a" * 40, "b" * 40)),
        ("atrium_version", ()),
        ("deploy_shas", ("nexus",)),
    ],
)
def test_cold_candidate_probe_blocks_before_missing_io_backend(method, args) -> None:
    from dashboard_shadow_fixture import boundary

    from orchestra.dashboard.shadow_probe import Recorder

    data = boundary()
    recorder = Recorder(
        candidate=True, opaque=set(), classes={"Probe": type(data["asm"].probes)}
    )
    with (
        recorder.loan(data["asm"], data["callbacks"]),
        pytest.raises(ShadowBlocked, match="cold_probe"),
    ):
        getattr(data["asm"].probes, method)(*args)
    assert not data["asm"].probes.calls and data["asm"].probes._memo == {}


def test_exact_frozen_answer_records_participate_in_full_graph(tmp_path) -> None:
    from dashboard_shadow_fixture import boundary

    data = boundary()
    AnswerRec = data["source"]["wi_fields"]["AnswerRec"]
    data["ctx"].answered = [AnswerRec("synthetic", frozenset({"synthetic question"}))]
    _, observer, _, _ = run_shadow(tmp_path, data)
    assert observer.pending.equivalent, observer.pending.differences
    assert data["ctx"].answered[0].decision == "synthetic"


def test_observer_enter_failure_keeps_normal_result_and_private_diagnostic(
    tmp_path, monkeypatch
) -> None:
    import sys
    from contextlib import contextmanager

    from dashboard_shadow_fixture import boundary

    from orchestra.dashboard.shadow_probe import Recorder

    data = boundary()
    code, calls = data["baseline"].__code__, []

    # Test-only: count one fixed synthetic SOURCE code entry; never inspect locals.
    def count(frame, event, arg):
        if event == "call" and frame.f_code is code:
            calls.append(1)

    @contextmanager
    def failing(*args, **kwargs):
        raise RuntimeError("PRIVATE_OBSERVER_CANARY")
        yield

    monkeypatch.setattr(Recorder, "loan", failing)
    previous = sys.getprofile()
    sys.setprofile(count)
    try:
        data, observer, result, _ = run_shadow(tmp_path, data)
    finally:
        sys.setprofile(previous)
    assert calls == [1]
    assert result["synthetic"]["steps_checked"]["check"] is True
    assert len(data["asm"].items["synthetic"]["children"]) == 2
    assert not observer.pending.equivalent
    assert "PRIVATE_OBSERVER_CANARY" not in str(observer.pending.differences)


def test_recorder_restores_loan_even_when_normal_body_raises() -> None:
    from dashboard_shadow_fixture import boundary

    from orchestra.dashboard.shadow_probe import Recorder
    from orchestra.dashboard.shadow_schema import PROBE_FIELDS

    data = boundary()
    probe = data["asm"].probes
    values = {
        key: object.__getattribute__(probe, "__dict__")[key] for key in PROBE_FIELDS
    }
    callbacks = {key: data["baseline"].__globals__[key] for key in data["callbacks"]}
    error = RuntimeError("synthetic normal error")
    recorder = Recorder(candidate=False, opaque=set(), classes={"Probe": type(probe)})
    with (
        pytest.raises(RuntimeError) as caught,
        recorder.loan(data["asm"], data["callbacks"], data["baseline"]),
    ):
        raise error
    assert caught.value is error
    assert set(object.__getattribute__(probe, "__dict__")) == set(PROBE_FIELDS)
    assert all(
        object.__getattribute__(probe, "__dict__")[key] is value
        for key, value in values.items()
    )
    assert all(
        data["baseline"].__globals__[key] is value for key, value in callbacks.items()
    )


def test_error_inside_actual_baseline_is_same_exception_without_retry(
    tmp_path, monkeypatch
) -> None:
    import sys
    from contextlib import contextmanager

    from dashboard_shadow_fixture import boundary

    from orchestra.dashboard.shadow_probe import Recorder

    data = boundary()
    error = RuntimeError("synthetic normal failure")

    class FailingNote(dict):
        def get(self, *args):
            raise error

    real_loan = Recorder.loan

    @contextmanager
    def loan(self, asm, callbacks, baseline=None):
        with real_loan(self, asm, callbacks, baseline) as wrapped:
            # A synthetic normal input fault after admission, not a callback/pin swap.
            data["notes"]["synthetic"] = FailingNote()
            yield wrapped

    monkeypatch.setattr(Recorder, "loan", loan)
    code, calls = data["baseline"].__code__, []

    def count(frame, event, arg):
        if event == "call" and frame.f_code is code:
            calls.append(1)

    previous = sys.getprofile()
    sys.setprofile(count)
    try:
        with pytest.raises(RuntimeError) as caught:
            run_shadow(tmp_path, data)
    finally:
        sys.setprofile(previous)
    assert calls == [1] and caught.value is error
    assert error.__context__ is None
    assert "pr_issue" not in object.__getattribute__(data["asm"], "__dict__")
    assert "pr_meta" not in object.__getattribute__(data["asm"].probes, "__dict__")
