"""Loaded code admission is pinned, not inferred from a supplied function name."""

import pytest
from dashboard_shadow_fixture import boundary

from orchestra.dashboard.shadow_graph import ShadowBlocked
from orchestra.dashboard.shadow_profile import approved_profile


def test_real_canonical_legacy_and_callbacks_admitted() -> None:
    data = boundary()
    profile = approved_profile(
        data["baseline"], data["candidate"], data["asm"], data["ctx"], data["callbacks"]
    )
    assert profile.profile_id == "m3s-full-boundary/1"
    assert profile.pins and profile.classes["Assembly"] is type(data["asm"])
    profile.recheck()


def test_same_name_fake_function_is_not_admitted() -> None:
    data = boundary()

    def collapse(asm, notes, tasks):
        return notes

    collapse.__module__ = "wi_dedupe"
    with pytest.raises(ShadowBlocked, match="callable_drift"):
        approved_profile(
            collapse, data["candidate"], data["asm"], data["ctx"], data["callbacks"]
        )


def test_global_mutation_and_callback_replacement_rejected() -> None:
    data = boundary()
    profile = approved_profile(
        data["baseline"], data["candidate"], data["asm"], data["ctx"], data["callbacks"]
    )
    function = data["source"]["wi_identity"]["repo_of"]
    old = function.__globals__["FULL"]
    function.__globals__["FULL"] = {**old, "synthetic": "other"}
    try:
        with pytest.raises(ShadowBlocked, match="global_drift"):
            profile.recheck()
    finally:
        function.__globals__["FULL"] = old
    data["callbacks"]["effective_note"] = lambda *args: {}
    with pytest.raises(ShadowBlocked, match="callable_drift"):
        approved_profile(
            data["baseline"],
            data["candidate"],
            data["asm"],
            data["ctx"],
            data["callbacks"],
        )


@pytest.mark.parametrize(
    "role,method", [("Probe", "pr_meta"), ("Assembly", "pr_issue")]
)
def test_post_approval_class_method_swap_rejected(role, method) -> None:
    data = boundary()
    profile = approved_profile(
        data["baseline"], data["candidate"], data["asm"], data["ctx"], data["callbacks"]
    )
    cls = profile.classes[role]
    original = getattr(cls, method)
    setattr(cls, method, lambda *args: None)
    try:
        with pytest.raises(ShadowBlocked, match="callable_drift"):
            profile.recheck()
    finally:
        setattr(cls, method, original)


def test_mutated_defaults_and_missing_pin_table_fail_closed(monkeypatch) -> None:
    from pathlib import Path

    data = boundary()
    function = data["source"]["wi_identity"]["identity"]
    original = function.__defaults__
    function.__defaults__ = (False,)
    try:
        with pytest.raises(ShadowBlocked, match="callable_drift"):
            approved_profile(
                data["baseline"],
                data["candidate"],
                data["asm"],
                data["ctx"],
                data["callbacks"],
            )
    finally:
        function.__defaults__ = original

    def missing(*args, **kwargs):
        raise FileNotFoundError("PRIVATE_CANARY")

    monkeypatch.setattr(Path, "open", missing)
    with pytest.raises(ShadowBlocked, match="callable_drift") as caught:
        approved_profile(
            data["baseline"],
            data["candidate"],
            data["asm"],
            data["ctx"],
            data["callbacks"],
        )
    assert caught.value.__suppress_context__ and "PRIVATE_CANARY" not in str(
        caught.value
    )


def test_mutated_stdlib_member_is_not_the_attested_module(monkeypatch) -> None:
    import copy

    data = boundary()
    monkeypatch.setattr(copy, "deepcopy", lambda value, memo=None: value)
    with pytest.raises(ShadowBlocked, match="callable_drift"):
        approved_profile(
            data["baseline"],
            data["candidate"],
            data["asm"],
            data["ctx"],
            data["callbacks"],
        )


def _isolated_candidate(data):
    from types import FunctionType

    original = data["candidate"]
    namespace = dict(original.__globals__)
    namespace["__builtins__"] = dict(original.__builtins__)
    candidate = FunctionType(
        original.__code__,
        namespace,
        original.__name__,
        original.__defaults__,
        original.__closure__,
    )
    candidate.__qualname__ = original.__qualname__
    candidate.__kwdefaults__ = dict(original.__kwdefaults__ or {})
    data["candidate"] = candidate
    return candidate


def _approve(data):
    return approved_profile(
        data["baseline"], data["candidate"], data["asm"], data["ctx"], data["callbacks"]
    )


def _observe_negative_with_real_baseline(data, profile):
    import sys
    from pathlib import Path

    from test_dashboard_shadow import prior_input

    from orchestra.dashboard.shadow import ShadowObserver, ShadowRequest
    from orchestra.dashboard.shadow_prior import PriorOwner

    prior, witness, now = prior_input(
        (PriorOwner("synthetic", "atrium", tuple(data["tasks"])),)
    )
    data["ctx"].now = now.timestamp()
    observer = ShadowObserver()
    code, calls = data["baseline"].__code__, []

    def count(frame, event, arg):
        if event == "call" and frame.f_code is code:
            calls.append(1)

    previous = sys.getprofile()
    sys.setprofile(count)
    try:
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
            request=ShadowRequest("4" * 32, Path("synthetic-no-storage"), 7200),
        )
    finally:
        sys.setprofile(previous)
    assert calls == [1]
    assert result["synthetic"]["steps_checked"]["check"] is True
    assert observer.pending.differences[0]["code"] == "callable_drift"
    assert not observer.pending.equivalent


@pytest.mark.parametrize("slot", ["builtin", "stdlib", "class", "class_ctor"])
def test_review_b1_resolved_slot_change_after_approval_blocks(
    slot, monkeypatch
) -> None:
    import copy
    from types import SimpleNamespace

    from orchestra.dashboard import curation, history

    data = boundary()
    candidate = _isolated_candidate(data) if slot == "builtin" else data["candidate"]
    profile = _approve(data)
    seen = []
    if slot == "builtin":

        def spy(*args, **kwargs):
            seen.append(1)
            return dict(*args, **kwargs)

        candidate.__builtins__["dict"] = spy
    elif slot == "stdlib":
        real = copy.deepcopy

        def spy(*args, **kwargs):
            seen.append(1)
            return real(*args, **kwargs)

        monkeypatch.setattr(curation, "copy", SimpleNamespace(deepcopy=spy))
    elif slot == "class":

        class DifferentConflict(ValueError):
            pass

        monkeypatch.setattr(history, "HistoricalBindingConflict", DifferentConflict)
    else:
        monkeypatch.setattr(
            history.HistoricalBindingConflict, "__init__", lambda *args: None
        )
    with pytest.raises(ShadowBlocked, match="callable_drift"):
        profile.recheck()
    _observe_negative_with_real_baseline(data, profile)
    assert seen == []


@pytest.mark.parametrize(
    "caller,name,target",
    [
        ("identity", "identity", "identity"),
        ("curation", "groups", "groups"),
        ("curation", "unique", "unique"),
    ],
)
def test_review_b2_wrong_role_pinned_function_not_approved(
    caller, name, target, monkeypatch
) -> None:
    from orchestra.dashboard import curation, identity

    data = boundary()
    module = {"identity": identity, "curation": curation}[caller]
    donor = "wi_dedupe" if target == "unique" else "wi_identity"
    monkeypatch.setattr(module, name, data["source"][donor][target])
    with pytest.raises(ShadowBlocked, match="callable_drift"):
        _approve(data)


@pytest.mark.parametrize(
    "timing", ["before_approval", "after_approval", "before_candidate"]
)
@pytest.mark.parametrize("name", ["qualified_pr", "resolve_work_provenance"])
def test_review_b2r_local_import_target_blocks_at_every_timing(
    timing, name, monkeypatch
) -> None:
    from orchestra.dashboard import provenance, shadow

    data = boundary()
    real = getattr(provenance, name)
    seen = []

    def spy(*args, **kwargs):
        seen.append(1)
        return real(*args, **kwargs)

    if timing == "before_approval":
        monkeypatch.setattr(provenance, name, spy)
        with pytest.raises(ShadowBlocked, match="callable_drift"):
            _approve(data)
        _observe_negative_with_real_baseline(data, None)
    else:
        profile = _approve(data)
        if timing == "after_approval":
            monkeypatch.setattr(provenance, name, spy)
        else:
            original = shadow._preflight

            def change(*args, **kwargs):
                monkeypatch.setattr(provenance, name, spy)
                return original(*args, **kwargs)

            monkeypatch.setattr(shadow, "_preflight", change)
        _observe_negative_with_real_baseline(data, profile)
    assert seen == []


def test_local_import_positive_runs_real_helper_and_attests_four_callers(tmp_path):
    import sys

    from test_dashboard_shadow import run_shadow

    from orchestra.dashboard import provenance

    data = boundary()
    profile = _approve(data)
    assert {entry.function.__name__ for entry in profile.imports} == {
        "_primary_reference",
        "_primary_conflict",
        "_declared_primary",
        "_historical_repo_valid",
    }
    calls = []
    code = provenance.resolve_work_provenance.__code__

    def count(frame, event, arg):
        if event == "call" and frame.f_code is code:
            calls.append(1)

    previous = sys.getprofile()
    sys.setprofile(count)
    try:
        _, observer, result, _ = run_shadow(tmp_path, data)
    finally:
        sys.setprofile(previous)
    assert calls == [1, 1]
    assert observer.pending.equivalent and not observer.pending.differences
    assert result["synthetic"]["steps_checked"]["check"] is True


@pytest.mark.parametrize("slot", ["module", "package", "import_hook"])
def test_local_import_resolution_metadata_changes_block(slot, monkeypatch):
    import sys
    from types import FunctionType, ModuleType

    from orchestra.dashboard import identity, provenance

    data = boundary()
    original = identity._primary_reference
    namespace = dict(original.__globals__)
    namespace["__builtins__"] = dict(original.__builtins__)
    function = FunctionType(original.__code__, namespace, original.__name__)
    function.__qualname__ = original.__qualname__
    monkeypatch.setattr(identity, "_primary_reference", function)
    profile = _approve(data)
    seen = []

    def spy(*args, **kwargs):
        seen.append(1)
        raise AssertionError("unattested import executed")

    if slot == "module":
        monkeypatch.setitem(
            sys.modules, provenance.__name__, ModuleType(provenance.__name__)
        )
    elif slot == "package":
        namespace["__package__"] = "unapproved"
    else:
        namespace["__builtins__"]["__import__"] = spy
    _observe_negative_with_real_baseline(data, profile)
    assert seen == []
