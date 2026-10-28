"""Finite SOURCE code/global admission. No module readers or provider operations."""

from __future__ import annotations

import builtins
import copy
import dis
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import CodeType, FunctionType, GetSetDescriptorType, MethodType, ModuleType
from typing import Any
from urllib.parse import urlsplit

from . import provenance as SourceProvenance
from . import shadow_schema as S
from .history import HistoricalBindingConflict as SourceConflict
from .shadow_graph import Graph, ShadowBlocked

# Generated once from declared approved SOURCE AST; no caller-supplied registry.
_PIN_SHA = "cc4e1369fc61d8fa52621e4e1f10847a0799cb795fd8bc3914502b36e49f6faa"
_APPROVED = object()
_PINS: dict[str, Any] = {}
_GLOBAL_EXPECTED: dict[str, Any] = {}
_DEFAULTS: dict[str, Any] = {}
_DEPENDENCIES: dict[str, Any] = {}
_LOCAL_IMPORTS: dict[str, Any] = {}


def _load_pins() -> None:
    try:
        with Path(__file__).with_name("shadow_profile_pins.json").open("rb") as stream:
            data = stream.read(131073)
        if len(data) > 131072 or hashlib.sha256(data).hexdigest() != _PIN_SHA:
            raise ValueError("pins")
        parsed = json.loads(data)
        if (
            set(parsed)
            != {
                "schema",
                "python",
                "functions",
                "globals",
                "defaults",
                "dependencies",
                "local_imports",
            }
            or parsed["schema"] != "m3s-approved-source-pins/1"
            or parsed["python"] != "3.12"
        ):
            raise ValueError("pins")
        _PINS.update(parsed["functions"])
        _GLOBAL_EXPECTED.update(parsed["globals"])
        _DEFAULTS.update(parsed["defaults"])
        _DEPENDENCIES.update(parsed["dependencies"])
        _LOCAL_IMPORTS.update(parsed["local_imports"])
    except (OSError, ValueError, TypeError):
        raise ShadowBlocked("callable_drift", "$code[*]") from None


_REPO_KEYS = (
    "ratio",
    "himalaia",
    "atrium",
    "nexus",
    "adlimenui",
    "adlimen-infra",
    "adlimen-cicd",
    "limen-assistant",
    "orchestra",
    "dotfiles",
)
_STDLIB = {
    "re": re,
    "copy": copy,
    "hashlib": hashlib,
    "json": json,
    "urlsplit": urlsplit,
    "datetime": datetime,
    "timezone": timezone,
    "Mapping": Mapping,
    "Sequence": Sequence,
}
_BUILTINS = {
    name: getattr(builtins, name)
    for name in (
        "__import__",
        "RecursionError",
        "ValueError",
        "all",
        "any",
        "bool",
        "dict",
        "int",
        "isinstance",
        "iter",
        "len",
        "list",
        "map",
        "max",
        "min",
        "next",
        "ord",
        "set",
        "sorted",
        "str",
        "super",
        "tuple",
        "type",
    )
}
_SOURCE_CLASSES = {"canonical.history.HistoricalBindingConflict": SourceConflict}

_STDLIB_MEMBERS = tuple(
    (
        module,
        name,
        getattr(module, name),
        getattr(getattr(module, name), "__code__", None),
    )
    for module, names in (
        (copy, ("deepcopy",)),
        (re, ("compile", "search", "finditer", "findall", "match", "fullmatch", "sub")),
        (json, ("dumps", "loads")),
        (hashlib, ("sha256",)),
    )
    for name in names
)
_COPY_RUNTIME: Any = copy
_COPY_DISPATCH = tuple(
    (key, value, getattr(value, "__code__", None))
    for key, value in _COPY_RUNTIME._deepcopy_dispatch.items()
)


def _stdlib_members() -> None:
    for module, name, expected, code in _STDLIB_MEMBERS:
        current = getattr(module, name)
        if current is not expected or getattr(current, "__code__", None) is not code:
            raise ShadowBlocked("callable_drift", "$code[*]")
    dispatch = _COPY_RUNTIME._deepcopy_dispatch
    if type(dispatch) is not dict or len(dispatch) != len(_COPY_DISPATCH):
        raise ShadowBlocked("callable_drift", "$code[*]")
    for actual_key, (key, expected, code) in zip(dispatch, _COPY_DISPATCH, strict=True):
        if actual_key is not key:
            raise ShadowBlocked("callable_drift", "$code[*]")
        current = dispatch[key]
        if current is not expected or getattr(current, "__code__", None) is not code:
            raise ShadowBlocked("callable_drift", "$code[*]")


_G1 = frozenset(
    [
        "REPOS",
        "FULL",
        "STATUSES",
        "CLOSED",
        "_CANONICAL_REPOSITORIES",
        "PROTECTED",
        "SAFE_KEY",
        "SUFFIX",
        "URL",
        "KEYWORD",
        "REF_RE",
        "STEP_LIMITS",
        "STEP_RE",
        "DEPLOY_RULE",
        "TAG_PATTERN",
        "ALREADY_DONE",
        "NOT_NEEDED",
        "SUPERSEDED",
        "IN_EFFECT_KINDS",
    ]
)


def _constant(value: Any) -> Any:
    if type(value) is CodeType:
        return _code(value)
    if type(value) is tuple:
        return ["tuple", [_constant(entry) for entry in value]]
    if value is None or type(value) in (str, int, float, bool, bytes):
        return [type(value).__name__, value.hex() if type(value) is bytes else value]
    if type(value) is frozenset:
        return ["frozenset", sorted(_constant(entry) for entry in value)]
    raise ShadowBlocked("callable_drift", "$code[*]")


def _code(code: CodeType) -> Any:
    return [
        code.co_name,
        code.co_qualname,
        code.co_argcount,
        code.co_posonlyargcount,
        code.co_kwonlyargcount,
        code.co_flags,
        code.co_code.hex(),
        code.co_exceptiontable.hex(),
        code.co_names,
        code.co_varnames,
        code.co_freevars,
        code.co_cellvars,
        [_constant(entry) for entry in code.co_consts],
    ]


def code_digest(code: CodeType) -> str:
    return hashlib.sha256(
        json.dumps(_code(code), separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def _label(function: FunctionType) -> str:
    module = function.__module__
    if type(module) is not str or type(function.__qualname__) is not str:
        raise ShadowBlocked("callable_drift", "$code[*]")
    for prefix in ("orchestra.dashboard.", "orchestra_dashboard."):
        if module.startswith(prefix):
            module = "canonical." + module.removeprefix(prefix)
    return module + "." + function.__qualname__


def _static(value: Any) -> Any:
    if type(value) is re.Pattern:
        return ["regex", value.pattern, value.flags]
    if type(value) in (str, int, bool) or value is None:
        return value
    if type(value) is dict:
        return ["dict", [[_static(k), _static(v)] for k, v in value.items()]]
    if type(value) in (list, tuple):
        return [type(value).__name__, [_static(v) for v in value]]
    if type(value) in (set, frozenset):
        return [type(value).__name__, sorted(_static(v) for v in value)]
    raise ShadowBlocked("global_drift", "$roots.globals")


@dataclass(frozen=True)
class ResolvedDependency:
    function: FunctionType
    name: str
    kind: str
    target: str
    namespace: dict[str, Any]
    value: Any

    def recheck(self) -> None:
        expected = _dependency_spec(self.function, self.name)
        if expected != {"kind": self.kind, "target": self.target}:
            raise ShadowBlocked("callable_drift", "$code[*]")
        namespace, value = _resolved_slot(self.function, self.name, self.kind)
        code = "global_drift" if self.kind == "global" else "callable_drift"
        if namespace is not self.namespace or value is not self.value:
            raise ShadowBlocked(code, "$code[*]")
        _dependency_target(self.kind, self.target, value)


@dataclass(frozen=True)
class ImportedDependency:
    function: FunctionType
    declaration: dict[str, Any]
    value: FunctionType
    package: str
    spec: ModuleSpec

    def recheck(self) -> None:
        value, package, spec = _import_slot(self.function, self.declaration)
        if value is not self.value or package != self.package or spec is not self.spec:
            raise ShadowBlocked("callable_drift", "$code[*]")


@dataclass
class ApprovedProfile:
    classes: dict[str, type]
    functions: list[FunctionType] = field(default_factory=list)
    caller_roles: list[tuple[FunctionType, str]] = field(default_factory=list)
    lookups: list[ResolvedDependency] = field(default_factory=list)
    imports: list[ImportedDependency] = field(default_factory=list)
    pins: list[dict[str, str]] = field(default_factory=list)
    globals: dict[str, Any] = field(default_factory=dict)
    bindings: list[tuple[dict[str, Any], str, Any]] = field(default_factory=list)
    static: list[tuple[Any, Any]] = field(default_factory=list)
    methods: list[tuple[type, str, Any]] = field(default_factory=list)
    approval: object = field(default=None, init=False, repr=False)
    profile_id: str = "m3s-full-boundary/1"
    boundary: tuple[Any, Any, tuple[tuple[str, Any], ...]] | None = None

    def bind(self, baseline: Any, candidate: Any, callbacks: Any) -> None:
        if self.boundary is None or type(callbacks) is not dict:
            raise ShadowBlocked("callable_drift", "$code[*]")
        old_baseline, old_candidate, old_callbacks = self.boundary
        if baseline is not old_baseline or candidate is not old_candidate:
            raise ShadowBlocked("callable_drift", "$code[*]")
        if len(callbacks) != len(old_callbacks) or any(
            callbacks.get(key) is not value for key, value in old_callbacks
        ):
            raise ShadowBlocked("callable_drift", "$code[*]")

    def recheck(self) -> None:
        _stdlib_members()
        if self.approval is not _APPROVED:
            raise ShadowBlocked("callable_drift", "$code[*]")
        self._recheck_classes()
        for cls, name, value in self.methods:
            if cls.__dict__.get(name) is not value:
                raise ShadowBlocked("callable_drift", "$code[*]")
        self._recheck_lookups()
        for namespace, name, value in self.bindings:
            if namespace.get(name) is not value:
                raise ShadowBlocked("global_drift", "$roots.globals")
        for value, expected in self.static:
            if _static(value) != expected:
                raise ShadowBlocked("global_drift", "$roots.globals")
        _borrowed_globals(self)

    def _recheck_lookups(self) -> None:
        for function, role in self.caller_roles:
            if _label(function) != role:
                raise ShadowBlocked("callable_drift", "$code[*]")
            _function_pin(function)
        for lookup in self.lookups:
            lookup.recheck()
        for imported in self.imports:
            imported.recheck()

    def _recheck_classes(self) -> None:
        for name, cls in self.classes.items():
            if name == "AnswerRec":
                _record_class(
                    cls,
                    name,
                    "wi_fields",
                    {"decision": "S", "questions": ("frozenset", "T")},
                )
            elif name == "Ctx":
                _record_class(cls, name, "workitems", S.CTX)
            else:
                _class(
                    cls,
                    {"Assembly": "wi_assembly", "Probe": "wi_probes"}[name],
                    {"Assembly": S.ASSEMBLY, "Probe": S.PROBE_FIELDS}[name],
                )

    @property
    def globals_schema(self) -> Any:
        # Slots are compiler-assigned ordinals, never application keys or payload.
        return S.record(
            {key: _global_schema(value) for key, value in self.globals.items()}
        )


def _closure(function: FunctionType) -> None:
    if function.__closure__:
        if (
            function.__code__.co_freevars != ("__class__",)
            or len(function.__closure__) != 1
        ):
            raise ShadowBlocked("closure", "$code[*]")
        cls = function.__closure__[0].cell_contents
        if (
            type(cls) is not type
            or cls.__name__ != "HistoricalBindingConflict"
            or cls.__bases__ != (ValueError,)
            or cls.__dict__.get("__init__") is not function
        ):
            raise ShadowBlocked("closure", "$code[*]")


def _function_pin(function: Any) -> tuple[str, str]:
    if type(function) is MethodType:
        function = function.__func__
    if type(function) is not FunctionType:
        raise ShadowBlocked("callable_drift", "$code[*]")
    _closure(function)
    label = _label(function)
    expected = _PINS.get(label)
    if expected is None or code_digest(function.__code__) != expected[1]:
        raise ShadowBlocked("callable_drift", "$code[*]")
    defaults = [
        _constant(function.__defaults__),
        {
            key: _constant(value)
            for key, value in (function.__kwdefaults__ or {}).items()
        },
    ]
    if defaults != _DEFAULTS.get(label):
        raise ShadowBlocked("callable_drift", "$code[*]")
    return expected[0], expected[1]


def _global_schema(value: Any) -> Any:
    if type(value) is set:
        return ("set", S.REF)
    if type(value) is dict and set(value) == set(_REPO_KEYS):
        return S.record(
            dict.fromkeys(
                _REPO_KEYS, ("tuple", ("OSTR", ("enum", ("origin", "github"))))
            )
        )
    if type(value) is dict and set(value) == {"atrium", "nexus"}:
        return S.record(
            {
                "atrium": ("enum", ("matteocervelli/atrium",)),
                "nexus": ("enum", ("matteocervelli/nexus",)),
            }
        )
    # G1 is checked against its initializer separately, retained by reference readonly.
    return "Static"


def _repo_global(value: Any) -> None:
    if type(value) is not dict or tuple(value) != _REPO_KEYS:
        raise ShadowBlocked("global_drift", "$roots.globals")
    for key in _REPO_KEYS:
        row = value[key]
        remote = "github" if key == "adlimenui" else "origin"
        if (
            type(row) is not tuple
            or len(row) != 2
            or type(row[0]) is not str
            or type(row[1]) is not str
            or row[1] != remote
        ):
            raise ShadowBlocked("global_drift", "$roots.globals")


def _borrowed_globals(profile: ApprovedProfile) -> None:
    for _namespace, name, value in profile.bindings:
        if name == "REPO_GIT":
            _repo_global(value)
        elif name == "FORGEJO_REPO":
            if type(value) is not dict or value != {
                "atrium": "matteocervelli/atrium",
                "nexus": "matteocervelli/nexus",
            }:
                raise ShadowBlocked("global_drift", "$roots.globals")
        elif name == "_DETACHED":
            Graph().clone(value, ("set", S.REF))


def _capture_global(
    profile: ApprovedProfile, namespace: dict[str, Any], name: str, value: Any
) -> None:
    profile.bindings.append((namespace, name, value))
    if name in _G1:
        expected = _GLOBAL_EXPECTED.get(name)
        actual = _static(value)
        if actual != expected:
            raise ShadowBlocked("global_drift", "$roots.globals")
        profile.static.append((value, actual))
        return
    if name in {"_DETACHED", "REPO_GIT", "FORGEJO_REPO"}:
        if not any(existing is value for existing in profile.globals.values()):
            profile.globals["g" + str(len(profile.globals))] = value
        return
    raise ShadowBlocked("closure", "$code[*]")


def _dependency_spec(function: FunctionType, name: str) -> dict[str, str]:
    row = _DEPENDENCIES.get(_label(function), {}).get(name)
    if row is None or row["kind"] == "unavailable":
        raise ShadowBlocked("closure", "$code[*]")
    return {"kind": row["kind"], "target": row["target"]}


def _resolved_slot(
    function: FunctionType, name: str, kind: str
) -> tuple[dict[str, Any], Any]:
    namespace = function.__globals__
    if kind == "builtin":
        if name in namespace:
            raise ShadowBlocked("callable_drift", "$code[*]")
        runtime_function: Any = function
        namespace = runtime_function.__builtins__
        if type(namespace) is not dict:
            raise ShadowBlocked("callable_drift", "$code[*]")
    return namespace, namespace.get(name)


def _dependency_target(kind: str, target: str, value: Any) -> None:
    if kind == "function":
        if type(value) is not FunctionType or _label(value) != target:
            raise ShadowBlocked("callable_drift", "$code[*]")
    elif kind != "global":
        expected = {
            "builtin": _BUILTINS,
            "stdlib": _STDLIB,
            "class": _SOURCE_CLASSES,
        }.get(kind)
        if expected is None or target not in expected or value is not expected[target]:
            raise ShadowBlocked("callable_drift", "$code[*]")


def _dependency(
    profile: ApprovedProfile, function: FunctionType, name: str, seen: set[int]
) -> None:
    expected = _dependency_spec(function, name)
    kind, target = expected["kind"], expected["target"]
    namespace, value = _resolved_slot(function, name, kind)
    _dependency_target(kind, target, value)
    profile.lookups.append(
        ResolvedDependency(function, name, kind, target, namespace, value)
    )
    if kind == "function":
        _walk(profile, value, seen)
    elif kind == "class":
        initializer = value.__dict__.get("__init__")
        profile.methods.append((value, "__init__", initializer))
        _walk(profile, initializer, seen)
    elif kind == "global":
        _capture_global(profile, namespace, name, value)


def _global_names(code: CodeType, *, nested: bool) -> set[str]:
    names = {
        instruction.argval
        for instruction in dis.get_instructions(code)
        if instruction.opname == "LOAD_GLOBAL"
    }
    if nested:
        for value in code.co_consts:
            if type(value) is CodeType:
                names.update(_global_names(value, nested=True))
    return names


def _import_context(function: FunctionType) -> tuple[str, ModuleSpec]:
    namespace = function.__globals__
    package, spec = namespace.get("__package__"), namespace.get("__spec__")
    expected_package = function.__module__.rsplit(".", 1)[0]
    if (
        type(package) is not str
        or package != expected_package
        or type(spec) is not ModuleSpec
        or type(spec.name) is not str
        or spec.name != function.__module__
        or spec.parent != expected_package
    ):
        raise ShadowBlocked("callable_drift", "$code[*]")
    return package, spec


def _import_slot(
    function: FunctionType, declaration: dict[str, Any]
) -> tuple[FunctionType, str, ModuleSpec]:
    # Literal relative imports use the already-loaded, pure SOURCE module only.
    package, spec = _import_context(function)
    module = SourceProvenance
    expected_name = package + ".provenance"
    if (
        declaration["module"] != "canonical.provenance"
        or declaration["level"] != 1
        or type(module) is not ModuleType
        or sys.modules.get(expected_name) is not module
        or type(module.__dict__.get("__name__")) is not str
        or module.__dict__["__name__"] != expected_name
    ):
        raise ShadowBlocked("callable_drift", "$code[*]")
    value = module.__dict__.get(declaration["name"])
    _dependency_target(declaration["kind"], declaration["target"], value)
    if type(value) is not FunctionType:
        raise ShadowBlocked("callable_drift", "$code[*]")
    return value, package, spec


def _local_dependencies(
    profile: ApprovedProfile, function: FunctionType, seen: set[int]
) -> None:
    declarations = _LOCAL_IMPORTS.get(_label(function), ())
    if not declarations:
        return
    _dependency(profile, function, "__import__", seen)
    for declaration in declarations:
        value, package, spec = _import_slot(function, declaration)
        profile.imports.append(
            ImportedDependency(function, declaration, value, package, spec)
        )
        _walk(profile, value, seen)


def _walk(profile: ApprovedProfile, function: Any, seen: set[int]) -> None:
    expected = _function_pin(function)
    if type(function) is MethodType:
        function = function.__func__
    if id(function) in seen:
        return
    seen.add(id(function))
    profile.functions.append(function)
    profile.caller_roles.append((function, _label(function)))
    role = "canonical" if _label(function).startswith("canonical.") else "legacy"
    profile.pins.append(
        {"role": role, "file_sha": expected[0], "loaded_code_sha": expected[1]}
    )
    for name in sorted(
        _global_names(
            function.__code__, nested=not _label(function).startswith("wi_probes.")
        )
    ):
        _dependency(profile, function, name, seen)
    _local_dependencies(profile, function, seen)


def _class(cls: type, module: str, fields: dict[str, Any]) -> None:
    if type(cls) is not type:
        raise ShadowBlocked("callable_drift", "$code[*]")
    if type(cls.__module__) is not str or cls.__module__ != module:
        raise ShadowBlocked("callable_drift", "$code[*]")
    if len(cls.__bases__) != 1 or cls.__bases__[0] is not object:
        raise ShadowBlocked("callable_drift", "$code[*]")
    _class_shape(cls, fields)


def _class_shape(cls: type, fields: dict[str, Any]) -> None:
    namespace = cls.__dict__
    descriptor = namespace.get("__dict__")
    if (
        type(descriptor) is not GetSetDescriptorType
        or descriptor.__objclass__ is not cls
    ):
        raise ShadowBlocked("callable_drift", "$code[*]")
    if (
        cls.__dict__.get("__getattribute__", object.__getattribute__)
        is not object.__getattribute__
        or "__getattr__" in namespace
        or "__slots__" in namespace
    ):
        raise ShadowBlocked("callable_drift", "$code[*]")
    if type(namespace.get("__dict__")) is not GetSetDescriptorType or any(
        key in namespace for key in fields
    ):
        raise ShadowBlocked("callable_drift", "$code[*]")


def _record_class(cls: type, name: str, module: str, fields: dict[str, Any]) -> None:
    _class(cls, module, fields)
    initializer = cls.__dict__.get("__init__")
    expected = _PINS.get(module + "." + name + ".__init__")
    if type(initializer) is not FunctionType or expected is None:
        raise ShadowBlocked("callable_drift", "$code[*]")
    if (
        code_digest(initializer.__code__) != expected[1]
        or initializer.__globals__.get(name) is not cls
    ):
        raise ShadowBlocked("callable_drift", "$code[*]")


def _classes_for(asm: Any, ctx: Any) -> dict[str, type]:
    _class(type(asm), "wi_assembly", S.ASSEMBLY)
    _class(type(ctx), "workitems", S.CTX)
    probe = object.__getattribute__(asm, "__dict__").get("probes")
    classes = {"Assembly": type(asm), "Ctx": type(ctx), "Probe": type(probe)}
    for key, module in (
        ("Assembly", "wi_assembly"),
        ("Ctx", "workitems"),
        ("Probe", "wi_probes"),
    ):
        _class(
            classes[key],
            module,
            {"Assembly": S.ASSEMBLY, "Ctx": S.CTX, "Probe": S.PROBE_FIELDS}[key],
        )
    _record_class(classes["Ctx"], "Ctx", "workitems", S.CTX)
    answered = object.__getattribute__(ctx, "__dict__").get("answered")
    if type(answered) is not list:
        raise ShadowBlocked("root_schema", "$roots.ctx.answered")
    if answered:
        answer_type = type(answered[0])
        _record_class(
            answer_type,
            "AnswerRec",
            "wi_fields",
            {"decision": "S", "questions": ("frozenset", "T")},
        )
        classes["AnswerRec"] = answer_type
    return classes


def _entrypoints(baseline: Any, candidate: Any, callbacks: Any) -> None:
    if (
        type(callbacks) is not dict
        or any(type(key) is not str for key in callbacks)
        or set(callbacks)
        != {
            "compute",
            "effective_note",
            "issue_ref",
        }
    ):
        raise ShadowBlocked("callable_drift", "$code[*]")
    if type(baseline) is not FunctionType or type(candidate) is not FunctionType:
        raise ShadowBlocked("callable_drift", "$code[*]")
    if (
        _label(baseline) != "wi_dedupe.collapse"
        or _label(candidate) != "canonical.curation.collapse"
    ):
        raise ShadowBlocked("callable_drift", "$code[*]")


def _callback_roles(baseline: FunctionType, callbacks: dict[str, Any]) -> None:
    for name, function in callbacks.items():
        expected = {
            "compute": "wi_status.compute",
            "effective_note": "wi_dedupe.effective_note",
            "issue_ref": "wi_assembly.issue_ref",
        }[name]
        if (
            type(function) is not FunctionType
            or _label(function) != expected
            or baseline.__globals__.get(name) is not function
        ):
            raise ShadowBlocked("callable_drift", "$code[*]")


def approved_profile(
    baseline: Any, candidate: Any, asm: Any, ctx: Any, callbacks: dict[str, Any]
) -> ApprovedProfile:
    _stdlib_members()
    _entrypoints(baseline, candidate, callbacks)
    _load_pins()
    _callback_roles(baseline, callbacks)
    classes = _classes_for(asm, ctx)
    profile = ApprovedProfile(classes)
    seen: set[int] = set()
    for function in (baseline, candidate, *callbacks.values(), asm.pr_issue):
        _walk(profile, function, seen)
    for name in (
        "_once",
        "pr_meta",
        "main_contains",
        "tag_contains",
        "is_ancestor",
        "atrium_version",
        "deploy_shas",
    ):
        method = classes["Probe"].__dict__.get(name)
        profile.methods.append((classes["Probe"], name, method))
        _walk(profile, method, seen)
    profile.methods.append(
        (classes["Assembly"], "pr_issue", classes["Assembly"].__dict__["pr_issue"])
    )
    profile.approval = _APPROVED
    profile.boundary = (baseline, candidate, tuple(callbacks.items()))
    profile.recheck()
    return profile
