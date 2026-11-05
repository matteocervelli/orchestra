"""Finite recorder loans; candidate probes execute only admitted warm paths."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from . import shadow_schema as S
from .shadow_graph import Graph, ShadowBlocked

METHODS = (
    "pr_meta",
    "main_contains",
    "tag_contains",
    "is_ancestor",
    "atrium_version",
    "deploy_shas",
)
_ARGS = {
    "pr_meta": ("S",),
    "main_contains": ("S", "SHA40"),
    "tag_contains": ("S", "SHA40", ("enum", ("v*", "ui/v*"))),
    "is_ancestor": ("S", "SHA40", "S", "B"),
    "atrium_version": (),
    "deploy_shas": ("S",),
    "pr_issue": (S.REF,),
    "effective_note": (S.mapping("ID", S.NOTE), S.seq("ID"), "ID", S.seq(S.CHILD)),
}
_RESULTS = {
    "pr_meta": S.mapping("I+", S.PR_META),
    "main_contains": "B?",
    "tag_contains": "B?",
    "is_ancestor": "B?",
    "atrium_version": ("union", ("SHA40", ("enum", ("",)))),
    "deploy_shas": ("nullable", S.seq("SHA40")),
    "pr_issue": "I+?",
    "effective_note": S.NOTE,
}
EVENT = S.union(
    *(
        S.record(
            {
                "kind": ("enum", (name,)),
                "args": ("tuple", args),
                "result": _RESULTS[name],
            }
        )
        for name, args in _ARGS.items()
    )
)


def _arguments(
    name: str, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> tuple[Any, ...]:
    if name != "is_ancestor":
        if kwargs:
            raise ShadowBlocked("callback_roster", "$frame.requests")
        return args
    if (
        not set(kwargs) <= {"persist"}
        or len(args) not in (3, 4)
        or (len(args) == 4 and kwargs)
    ):
        raise ShadowBlocked("callback_roster", "$frame.requests")
    return args if len(args) == 4 else (*args, kwargs.get("persist", True))


def warm(
    probe: Any,
    name: str,
    args: tuple[Any, ...],
    repo_keys: dict[str, Any],
    forgejo: dict[str, str],
) -> bool:
    Graph().clone(args, ("tuple", _ARGS[name]))
    if name == "pr_meta":
        return ("meta", args[0]) in probe._memo
    if name == "atrium_version":
        return "atrium" in probe._memo
    if name == "deploy_shas":
        return args[0] in forgejo and ("fj", args[0]) in probe._memo
    short, commit = args[:2]
    if short not in repo_keys:
        return False
    if name == "main_contains":
        return probe._anc.get(f"{short}:{commit}:main") is True
    if name == "tag_contains":
        return probe._anc.get(f"{short}:{commit}:tag:{args[2]}") is True
    key = f"{short}:{commit}:{args[2]}"
    return key in probe._anc if args[3] else ("anc", key) in probe._memo


class Recorder:
    def __init__(
        self, *, candidate: bool, opaque: set[int], classes: dict[str, type]
    ) -> None:
        self.candidate = candidate
        self.opaque = opaque
        self.classes = classes
        self.events: list[dict[str, Any]] = []
        self.calls = 0
        self.probes = 0
        self.failure: ShadowBlocked | None = None
        self.pr_roster: list[Any] = []
        self.borrowed: list[tuple[dict[str, Any], str, Any, bool]] = []

    def _invalid(self, failure: ShadowBlocked) -> None:
        self.failure = self.failure or failure
        if self.candidate:
            raise failure

    def _admit(
        self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any], probe: Any
    ) -> tuple[Any, ...] | None:
        try:
            values = _arguments(name, args, kwargs)
            if any(id(value) in self.opaque for value in values):
                raise ShadowBlocked("opaque_op", "$frame.requests")
            Graph(self.classes, known_opaque=self.opaque).clone(
                values, ("tuple", _ARGS[name])
            )
            if name in METHODS:
                namespace = getattr(type(probe), name).__globals__
                if not warm(
                    probe,
                    name,
                    values,
                    namespace.get("REPO_GIT", {}),
                    namespace.get("FORGEJO_REPO", {}),
                ):
                    raise ShadowBlocked("cold_probe", "$frame.requests")
            return values
        except ShadowBlocked as failure:
            self._invalid(failure)
            return None
        except Exception:
            self._invalid(ShadowBlocked("callback_roster", "$frame.requests"))
            return None

    def _wrapped(self, name: str, real: Any, probe: Any) -> Any:
        def call(*args: Any, **kwargs: Any) -> Any:
            self.calls += 1
            self.probes += int(name in METHODS)
            if name in {"compute", "issue_ref"}:
                self._invalid(ShadowBlocked("callback_roster", "$frame.requests"))
                return real(*args, **kwargs)
            values = self._admit(name, args, kwargs, probe)
            event = {"kind": name, "args": values, "result": None}
            if values is not None:
                self.events.append(event)
                if name == "pr_issue":
                    self.pr_roster.append(values[0])
            result = real(*args, **kwargs)
            if values is not None:
                try:
                    Graph(self.classes, known_opaque=self.opaque).clone(
                        result, _RESULTS[name]
                    )
                    event["result"] = result
                except ShadowBlocked as failure:
                    self._invalid(failure)
                except Exception:
                    self._invalid(ShadowBlocked("callback_roster", "$frame.requests"))
            return result

        return call

    def _borrow(self, namespace: dict[str, Any], name: str, replacement: Any) -> None:
        present = name in namespace
        self.borrowed.append((namespace, name, namespace.get(name), present))
        namespace[name] = replacement

    @contextmanager
    def loan(self, asm: Any, callbacks: dict[str, Any], baseline: Any = None) -> Any:
        probe = asm.probes
        try:
            for name in METHODS:
                self._borrow(
                    object.__getattribute__(probe, "__dict__"),
                    name,
                    self._wrapped(name, getattr(probe, name), probe),
                )
            self._borrow(
                object.__getattribute__(asm, "__dict__"),
                "pr_issue",
                self._wrapped("pr_issue", asm.pr_issue, probe),
            )
            wrapped = {
                name: self._wrapped(name, fn, probe) for name, fn in callbacks.items()
            }
            if baseline is not None:
                for name, function in wrapped.items():
                    self._borrow(baseline.__globals__, name, function)
            yield wrapped
        finally:
            for namespace, name, previous, present in reversed(self.borrowed):
                if present:
                    namespace[name] = previous
                else:
                    namespace.pop(name, None)
            self.borrowed.clear()
