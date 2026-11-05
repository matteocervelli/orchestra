"""Dormant full-boundary shadow with a private candidate and publish seal."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import shadow_schema as S
from .shadow_graph import Graph, ShadowBlocked, _atom
from .shadow_prior import (
    PriorBindingInput,
    PriorWitness,
    derive_prior_bindings,
    generation,
)
from .shadow_probe import EVENT, Recorder
from .shadow_profile import ApprovedProfile, approved_profile
from .shadow_store import COUNTS, COVERAGE, CommitResult, CommitState, commit_receipt


@dataclass
class ShadowRequest:
    nonce: str
    directory: Path
    max_prior_age_seconds: int
    _consumed: bool = field(default=False, init=False, repr=False)

    def consume(self) -> None:
        used = self._consumed
        self._consumed = True
        if (
            used
            or type(self.nonce) is not str
            or re.fullmatch(r"[0-9a-f]{32}", self.nonce) is None
        ):
            raise ShadowBlocked("bounds", "$commit")
        if (
            type(self.max_prior_age_seconds) is not int
            or not 1 <= self.max_prior_age_seconds <= 604800
        ):
            raise ShadowBlocked("bounds", "$prior.generation")
        if type(self.directory) is not type(Path()):
            raise ShadowBlocked("bounds", "$commit")


@dataclass
class PendingShadow:
    request: ShadowRequest
    prior: PriorBindingInput | None = None
    witness: PriorWitness | None = None
    equivalent: bool = False
    differences: list[dict[str, Any]] = field(default_factory=list)
    coverage: dict[str, bool] = field(
        default_factory=lambda: dict.fromkeys(COVERAGE, False)
    )
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(COUNTS, 0))
    pins: list[dict[str, str]] = field(default_factory=list)
    shape_sha: str = "0" * 64
    alias_sha: str = "0" * 64
    baseline_ok: bool = False
    sealed: bool = False
    phase: str = "prepare"

    def block(self, failure: ShadowBlocked) -> None:
        path = failure.path
        if path.startswith("$roots.globals"):
            path = "$roots.globals"
        elif path.startswith("$roots._frame"):
            path = "$frame.requests"
        self.differences.append(
            {"code": failure.code, "path": path, "count": failure.count}
        )
        self.counts["differences"] += failure.count
        self.equivalent = False


def _shared_frame(shared: Any) -> dict[str, Any]:
    if (
        type(shared) is not dict
        or any(type(key) is not str for key in shared)
        or set(shared) != {"ctx", "locals"}
    ):
        raise ShadowBlocked("root_schema", "$roots")
    return shared


def _boundary_profile(
    baseline: Any,
    candidate: Any,
    asm: Any,
    shared: Any,
    callbacks: Any,
    profile: Any,
) -> ApprovedProfile:
    if profile is None:
        frame = _shared_frame(shared)
        profile = approved_profile(baseline, candidate, asm, frame["ctx"], callbacks)
    if type(profile) is not ApprovedProfile:
        raise ShadowBlocked("callable_drift", "$code[*]")
    profile.bind(baseline, candidate, callbacks)
    return profile


def _root(
    asm: Any, notes: Any, tasks: Any, shared: Any, profile: ApprovedProfile
) -> dict[str, Any]:
    _shared_frame(shared)
    return {
        "asm": asm,
        "ctx": shared["ctx"],
        "locals": shared["locals"],
        "original_notes": notes,
        "return_notes": None,
        "tasks": tasks,
        "globals": profile.globals,
        "_frame": [],
    }


def _schema() -> Any:
    return S.record({**S.ROOT_FIELDS, "_frame": S.seq(EVENT)})


def _disjoint(profile: ApprovedProfile, graph: Graph) -> None:
    for value in profile.globals.values():
        if not graph.first_path.get(id(value), "").startswith("$roots.globals"):
            raise ShadowBlocked("global_drift", "$roots.globals")
    for value, _ in profile.static:
        if id(value) in graph.memo:
            raise ShadowBlocked("global_drift", "$roots.globals")


def _prepare(
    asm: Any,
    notes: Any,
    tasks: Any,
    shared: Any,
    prior: Any,
    witness: Any,
    profile: Any,
    pending: PendingShadow,
) -> tuple[dict[str, Any], dict[str, Any], Graph, Any]:
    if type(profile) is not ApprovedProfile:
        raise ShadowBlocked("callable_drift", "$code[*]")
    profile.recheck()
    roots = _root(asm, notes, tasks, shared, profile)
    if type(roots["ctx"]) is not profile.classes["Ctx"]:
        raise ShadowBlocked("root_schema", "$roots.ctx")
    raw_now = object.__getattribute__(roots["ctx"], "__dict__").get("now")
    if not _atom(raw_now, "N0"):
        raise ShadowBlocked("root_schema", "$roots.ctx.now")
    now = datetime.fromtimestamp(raw_now, UTC)
    bindings = derive_prior_bindings(
        prior, witness, now=now, max_age=pending.request.max_prior_age_seconds
    )
    pending.prior, pending.witness = prior, witness
    graph = Graph(profile.classes, profile.globals_schema)
    clone = graph.clone(roots, _schema())
    pending.coverage.update(roots=True, opaque=True, callables=True)
    _disjoint(profile, graph)
    pending.pins = list(profile.pins)
    pending.counts.update(items=len(asm.items), nodes=graph.nodes, edges=graph.edges)
    if len(asm.items) > 5000:
        raise ShadowBlocked("bounds", "$roots.asm.items")
    return roots, clone, graph, bindings


def _preflight(
    profile: ApprovedProfile,
    roots: Any,
    baseline: Recorder,
    original_probe: Any,
    pending: PendingShadow,
) -> None:
    profile.recheck()
    if baseline.failure is not None:
        raise baseline.failure
    if baseline.pr_roster != list(roots["asm"].pr_by):
        raise ShadowBlocked("callback_roster", "$frame.requests")
    frame = Graph(profile.classes)
    frame.clone(original_probe, "Probe")
    if not frame.equivalent(original_probe, roots["asm"].probes):
        raise ShadowBlocked("frame_delta", "$frame.memo")
    pending.coverage.update(roster=True, frame=True)


def _compare(
    candidate: Any,
    roots: Any,
    clone: Any,
    graph: Graph,
    bindings: Any,
    callbacks: Any,
    baseline: Recorder,
    profile: ApprovedProfile,
    pending: PendingShadow,
) -> None:
    pending.phase = "preflight"
    _preflight(profile, roots, baseline, clone["asm"].probes, pending)
    recorder = Recorder(
        candidate=True, opaque=set(graph.opaque), classes=profile.classes
    )
    pending.phase = "candidate"
    with recorder.loan(clone["asm"], callbacks) as wrapped:
        clone["return_notes"] = candidate(
            clone["asm"],
            clone["original_notes"],
            clone["tasks"],
            historical_bindings=bindings,
            **wrapped,
        )
    if recorder.failure is not None:
        raise recorder.failure
    if recorder.pr_roster != list(clone["asm"].pr_by):
        raise ShadowBlocked("callback_roster", "$frame.requests")
    roots["_frame"], clone["_frame"] = baseline.events, recorder.events
    pending.phase = "compare"
    profile.recheck()
    pending.counts.update(
        callbacks=baseline.calls + recorder.calls,
        probes=baseline.probes + recorder.probes,
    )
    if not graph.equivalent(roots, clone):
        raise ShadowBlocked("post_delta", "$roots")
    pending.shape_sha, pending.alias_sha = graph.fingerprints()
    pending.coverage["postgraph"] = True
    pending.equivalent = True


def _publication_payload(
    handle: PendingShadow, final_generated: str, board_digest: str
) -> dict[str, Any]:
    if handle.prior is None or handle.witness is None:
        raise ShadowBlocked("prior_missing", "$prior.witness")
    if generation(handle.prior.generated) >= generation(final_generated):
        raise ShadowBlocked("prior_invalid", "$prior.generation")
    if (
        type(board_digest) is not str
        or re.fullmatch(r"[0-9a-f]{64}", board_digest) is None
    ):
        raise ShadowBlocked("publish_failed", "$publish.digest")
    handle.coverage["publish"] = True
    return {
        "schema": "shadow-observation/1",
        "nonce": handle.request.nonce,
        "verdict": "PASS"
        if handle.equivalent and all(handle.coverage.values())
        else "BLOCK",
        "phase": "publish",
        "profile_id": "m3s-full-boundary/1",
        "final_generated": final_generated,
        "final_board_digest": board_digest,
        "prior_generated": handle.prior.generated,
        "prior_board_digest": handle.prior.board_digest,
        "witness_sha": handle.witness.sha256,
        "code_pins": handle.pins,
        "coverage": handle.coverage,
        "counts": handle.counts,
        "shape_sha": handle.shape_sha,
        "alias_sha": handle.alias_sha,
        "diffs": handle.differences,
    }


def _recorded_baseline(
    recorder: Recorder,
    baseline: Any,
    asm: Any,
    notes: Any,
    tasks: Any,
    callbacks: Any,
    pending: PendingShadow,
) -> tuple[Any, bool]:
    loan = recorder.loan(asm, callbacks, baseline)
    try:
        loan.__enter__()
    except Exception:
        pending.block(ShadowBlocked("root_schema"))
        return baseline(asm, notes, tasks), False
    try:
        result = baseline(asm, notes, tasks)
    except BaseException:
        try:
            loan.__exit__(*sys.exc_info())
        except Exception:
            pending.block(ShadowBlocked("root_schema"))
        raise
    try:
        loan.__exit__(None, None, None)
    except Exception:
        pending.block(ShadowBlocked("root_schema"))
        return result, False
    return result, True


class ShadowObserver:
    def __init__(self) -> None:
        self.pending: PendingShadow | None = None
        self._commit_result: CommitResult | None = None

    @property
    def commit_result(self) -> CommitResult | None:
        """The original result/capability of this observer's one seal attempt."""
        return self._commit_result

    def observe_boundary(
        self,
        baseline: Any,
        candidate: Any,
        asm: Any,
        notes: Any,
        tasks: Any,
        *,
        shared_roots: Any,
        callbacks: Any,
        prior: Any,
        witness: Any,
        profile: Any,
        request: ShadowRequest | None = None,
    ) -> Any:
        if request is None:
            return baseline(asm, notes, tasks)
        pending = PendingShadow(request)
        self.pending = pending
        prepared = None
        try:
            if type(request) is not ShadowRequest:
                raise ShadowBlocked("bounds", "$commit")
            request.consume()
            profile = _boundary_profile(
                baseline, candidate, asm, shared_roots, callbacks, profile
            )
            prepared = _prepare(
                asm, notes, tasks, shared_roots, prior, witness, profile, pending
            )
        except ShadowBlocked as failure:
            pending.block(failure)
        except Exception:
            pending.block(ShadowBlocked("root_schema"))
        return self._normal(
            baseline,
            candidate,
            asm,
            notes,
            tasks,
            callbacks,
            profile,
            pending,
            prepared,
        )

    def _normal(
        self,
        baseline: Any,
        candidate: Any,
        asm: Any,
        notes: Any,
        tasks: Any,
        callbacks: Any,
        profile: Any,
        pending: PendingShadow,
        prepared: Any,
    ) -> Any:
        recorder = None
        pending.phase = "baseline"
        try:
            if prepared is None:
                result = baseline(asm, notes, tasks)
            else:
                recorder = Recorder(
                    candidate=False,
                    opaque=set(prepared[2].opaque),
                    classes=profile.classes,
                )
                result, recorded = _recorded_baseline(
                    recorder, baseline, asm, notes, tasks, callbacks, pending
                )
                if not recorded:
                    recorder = None
            pending.baseline_ok = True
        except BaseException:
            pending.block(ShadowBlocked("baseline_exception"))
            raise
        if prepared is not None and recorder is not None:
            roots, clone, graph, bindings = prepared
            roots["return_notes"] = result
            try:
                _compare(
                    candidate,
                    roots,
                    clone,
                    graph,
                    bindings,
                    callbacks,
                    recorder,
                    profile,
                    pending,
                )
            except ShadowBlocked as failure:
                pending.block(failure)
            except Exception:
                pending.block(ShadowBlocked("candidate_exception"))
        return result

    def seal_after_publish(
        self, handle: PendingShadow, final_generated: str, board_digest: str
    ) -> CommitResult:
        if (
            handle is not self.pending
            or handle.sealed
            or not handle.baseline_ok
            or self._commit_result is not None
        ):
            return CommitResult(CommitState.NOT_COMMITTED)
        handle.sealed = True
        result = CommitResult(CommitState.NOT_COMMITTED)
        if handle.prior is not None and handle.witness is not None:
            try:
                payload = _publication_payload(handle, final_generated, board_digest)
                result = commit_receipt(handle.request.directory, payload)
            except (ShadowBlocked, ValueError, OSError):
                pass
        self._commit_result = result
        return result
