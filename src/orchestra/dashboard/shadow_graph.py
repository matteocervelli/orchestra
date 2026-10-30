"""Closed graph cloning and bidirectional alias comparison for the fixed boundary."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import PosixPath
from typing import Any

from . import shadow_schema as S


class ShadowBlocked(ValueError):
    """A static diagnostic, never including a value or arbitrary input key."""

    def __init__(self, code: str, path: str = "$roots", count: int = 1) -> None:
        self.code, self.path, self.count = code, path, count
        super().__init__(code)


EDGE_LIMIT = 1000000
NODE_LIMIT = 200000

_PATTERNS = {
    "ID": r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}",
    "StepID": r"[A-Za-z0-9_-]{1,40}",
    "SHA40": r"[0-9a-f]{40}",
    "H64": r"[0-9a-f]{64}",
    "TS": r"(?:|\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00))",
}
_LIMITS = {"S": 200, "S64": 64, "T": 16384, "U": 2048, "T500": 500, "T1000": 1000}


def _integer(value: Any, kind: str) -> bool:
    bounds = {
        "I": (None, None),
        "I+": (1, None),
        "I0": (0, None),
        "Order": (-9999, 9999),
    }
    low, high = bounds[kind]
    return (
        type(value) is int
        and (low is None or value >= low)
        and (high is None or value <= high)
    )


def _atom(value: Any, kind: str) -> bool:
    if kind.endswith("?"):
        return value is None or _atom(value, kind[:-1])
    if kind in _LIMITS:
        return type(value) is str and len(value.encode("utf-8")) <= _LIMITS[kind]
    if kind in _PATTERNS:
        return type(value) is str and re.fullmatch(_PATTERNS[kind], value) is not None
    if kind in {"I", "I+", "I0", "Order"}:
        return _integer(value, kind)
    return _other_atom(value, kind)


def _other_atom(value: Any, kind: str) -> bool:
    if kind == "B":
        return type(value) is bool
    if kind in {"N", "N0"}:
        return (
            type(value) in (int, float)
            and math.isfinite(value)
            and (kind == "N" or value >= 0)
        )
    if kind == "Priority":
        return type(value) is str and value in ("P0", "P1", "P2", "P3")
    if kind == "CounterKey":
        return type(value) is str and value in (
            "gh",
            "git",
            "docker",
            "fj",
            "ssh",
            "tailscale",
        )
    return False


def _memo_schema(key: Any) -> S.Schema:
    if type(key) is str and key == "atrium":
        return ("union", ("SHA40", ("enum", ("",))))
    if type(key) is not tuple or len(key) != 2:
        raise ShadowBlocked("root_schema", "$frame.memo")
    tag, name = key
    if type(tag) is not str or not _atom(name, "S"):
        raise ShadowBlocked("root_schema", "$frame.memo")
    schemas = {
        "meta": S.mapping("I+", S.PR_META),
        "anc": "B?",
        "fj": ("nullable", S.seq("SHA40")),
    }
    if tag not in schemas:
        raise ShadowBlocked("root_schema", "$frame.memo")
    return schemas[tag]


class Graph:
    """One memo for all declared roots, with no generic object introspection."""

    def __init__(
        self,
        classes: dict[str, type] | None = None,
        globals_schema: Any = None,
        known_opaque: set[int] | None = None,
    ) -> None:
        self.external_opaque = known_opaque or set()
        self.classes = classes or {}
        self.globals_schema = globals_schema
        self.schema: Any = None
        self.memo: dict[int, Any] = {}
        self.first_path: dict[int, str] = {}
        self.active: set[int] = set()
        self.nodes = self.edges = 0
        self.preflight_edges = 0
        self.preflight_seen: set[tuple[int, int]] = set()
        self.preflight_specs: list[Any] = []
        self.opaque: set[int] = set()
        self.ordinary: set[int] = set()
        self.validated: set[tuple[int, int]] = set()
        self.tokens: list[Any] = []
        self.shape: list[Any] = []
        self.aliases: list[Any] = []

    def clone(self, value: Any, schema: Any = None) -> Any:
        self.schema = schema if schema is not None else self.schema
        self.memo, self.active, self.opaque = {}, set(), set(self.external_opaque)
        self.ordinary, self.validated = set(), set()
        self.first_path = {}
        self.tokens, self.shape, self.aliases = [], [], []
        self.nodes = self.edges = 0
        self.preflight_edges = 0
        self.preflight_seen = set()
        self.preflight_specs = []
        self._opaque_preflight(value, self.schema, "$roots", set(), 0)
        return self._visit(value, self.schema, "$roots", 0)

    def _opaque_preflight(
        self, value: Any, schema: Any, path: str, active: set[int], depth: int
    ) -> None:
        """Collect opaque roles before any ordinary leaf validation or comparison."""
        self.preflight_edges += 1
        if depth > 32 or self.preflight_edges > EDGE_LIMIT:
            raise ShadowBlocked("bounds", path)
        key = (id(value), id(schema))
        if key in self.preflight_seen:
            return
        if len(self.preflight_seen) >= NODE_LIMIT:
            raise ShadowBlocked("bounds", path)
        self.preflight_seen.add(key)
        self.preflight_specs.append(schema)
        if type(schema) is str:
            self._opaque_named(value, schema, path, active, depth)
            return
        kind = schema[0]
        if kind == "nullable":
            if value is not None:
                self._opaque_preflight(value, schema[1], path, active, depth)
            return
        if kind == "enum":
            return
        if kind == "union":
            self._opaque_union(value, schema[1], path, active, depth)
            return
        self._opaque_container(value, schema, path, active, depth)

    def _opaque_named(
        self, value: Any, name: str, path: str, active: set[int], depth: int
    ) -> None:
        if name in {"OSTR", "OPATH"}:
            self.opaque.add(id(value))
        elif name == "Globals":
            self._opaque_preflight(value, self.globals_schema, path, active, depth)
        elif name in self.classes:
            if type(value) is not self.classes[name]:
                raise ShadowBlocked("root_schema", path)
            fields = {
                "Assembly": S.ASSEMBLY,
                "Ctx": S.CTX,
                "Probe": S.PROBE_FIELDS,
                "AnswerRec": {"decision": "S", "questions": ("frozenset", "T")},
            }[name]
            self._opaque_preflight(
                object.__getattribute__(value, "__dict__"),
                S.record(fields),
                path,
                active,
                depth + 1,
            )
        # Memo never declares opaque values; its closed schema is checked later.
        return

    def _opaque_union(
        self, value: Any, variants: Any, path: str, active: set[int], depth: int
    ) -> None:
        for spec in variants:
            try:
                self._opaque_preflight(value, spec, path, active, depth)
            except ShadowBlocked as failure:
                if failure.code in {"forbidden", "bounds"}:
                    raise
                continue

    def _opaque_container(
        self, value: Any, schema: Any, path: str, active: set[int], depth: int
    ) -> None:
        kind = schema[0]
        expected = {
            "record": dict,
            "map": dict,
            "list": list,
            "tuple": tuple,
            "set": set,
            "frozenset": frozenset,
            "counter": Counter,
        }.get(kind)
        if type(value) is not expected:
            raise ShadowBlocked("root_schema", path)
        if kind == "tuple" and len(value) != len(schema[1]):
            raise ShadowBlocked("root_schema", path)
        if id(value) in active:
            raise ShadowBlocked("root_schema", path)
        limit = {"children": 200, "ask": 100, "steps": 200, "items": 5000}.get(
            path.rsplit(".", 1)[-1], 20000
        )
        if len(value) > limit:
            raise ShadowBlocked("bounds", path)
        active.add(id(value))
        try:
            self._opaque_entries(value, schema, path, active, depth)
        finally:
            active.remove(id(value))

    def _opaque_entries(
        self, value: Any, schema: Any, path: str, active: set[int], depth: int
    ) -> None:
        kind = schema[0]
        if kind == "record":
            fields = self._record_fields(value, schema, path)
            for key in value:
                self._opaque_preflight(
                    value[key], fields[key], path + "." + key, active, depth + 1
                )
        elif kind in {"map", "counter"}:
            self._opaque_mapping(value, schema, path, active, depth)
        else:
            for i, entry in enumerate(value):
                spec = (
                    schema[1][i]
                    if kind == "tuple" and i < len(schema[1])
                    else schema[1]
                )
                self._opaque_preflight(entry, spec, path + "[*]", active, depth + 1)

    def _opaque_mapping(
        self, value: Any, schema: Any, path: str, active: set[int], depth: int
    ) -> None:
        key_spec = schema[1]
        value_spec = "I0" if schema[0] == "counter" else schema[2]
        for key in value:
            self._opaque_preflight(key, key_spec, path + "[*]", active, depth + 1)
            self._opaque_preflight(
                value[key], value_spec, path + "[*]", active, depth + 1
            )

    def equivalent(self, left: Any, right: Any) -> bool:
        self.clone(left)
        expected = list(self.tokens)
        self.clone(right)
        return expected == self.tokens

    def fingerprints(self) -> tuple[str, str]:
        def digest(value: Any) -> str:
            return hashlib.sha256(
                json.dumps(value, separators=(",", ":")).encode()
            ).hexdigest()

        return digest(self.shape), digest(self.aliases)

    def _visit(self, value: Any, schema: Any, path: str, depth: int) -> Any:
        self.edges += 1
        if depth > 32 or self.edges > EDGE_LIMIT:
            raise ShadowBlocked("bounds", path)
        if type(schema) is str:
            return self._named(value, schema, path, depth)
        kind = schema[0]
        if kind in {"nullable", "union", "enum"}:
            return self._variant(value, schema, path, depth)
        return self._container(value, schema, path, depth)

    def _named(self, value: Any, name: str, path: str, depth: int) -> Any:
        if name in {"OSTR", "OPATH"}:
            return self._opaque_atom(value, name, path)
        if name == "Globals":
            return self._visit(value, self.globals_schema, path, depth)
        if name == "Memo":
            return self._container(value, ("memo",), path, depth)
        if name in self.classes:
            return self._object(value, name, path, depth)
        if id(value) in self.opaque:
            raise ShadowBlocked("opaque_op", path)
        if type(value) is str:
            self.ordinary.add(id(value))
        if not _atom(value, name):
            raise ShadowBlocked("root_schema", path)
        self.tokens.append(("atom", type(value).__name__, value))
        self.shape.append(("atom", name))
        return value

    def _opaque_atom(self, value: Any, name: str, path: str) -> Any:
        expected = str if name == "OSTR" else PosixPath
        if type(value) is not expected:
            raise ShadowBlocked("root_schema", path)
        if id(value) in self.ordinary:
            raise ShadowBlocked("opaque_op", path)
        self.opaque.add(id(value))
        self.tokens.append(("opaque", name, id(value)))
        self.shape.append(("opaque", name))
        return value

    def _variant(self, value: Any, schema: Any, path: str, depth: int) -> Any:
        kind, body = schema
        if kind == "nullable":
            if value is None:
                self.tokens.append(("null",))
                self.shape.append(("null",))
                return None
            return self._visit(value, body, path, depth)
        if id(value) in self.opaque:
            raise ShadowBlocked("opaque_op", path)
        if kind == "enum":
            if type(value) is not str or value not in body:
                raise ShadowBlocked("root_schema", path)
            self.ordinary.add(id(value))
            self.tokens.append(("enum", value))
            self.shape.append(("enum",))
            return value
        for candidate in body:
            probe = Graph(self.classes, self.globals_schema, self.opaque)
            try:
                probe.clone(value, candidate)
            except ShadowBlocked:
                continue
            return self._visit(value, candidate, path, depth)
        raise ShadowBlocked("root_schema", path)

    def _begin(self, value: Any, path: str, kind: str) -> tuple[bool, Any]:
        ident = id(value)
        if ident in self.active:
            raise ShadowBlocked("root_schema", path)
        if ident in self.memo:
            self.tokens.append(("ref", self.memo[ident][0]))
            self.aliases.append(("ref", self.memo[ident][0]))
            return True, self.memo[ident][1]
        self.nodes += 1
        if self.nodes > NODE_LIMIT:
            raise ShadowBlocked("bounds", path)
        self.active.add(ident)
        self.first_path[ident] = path
        self.tokens.append((kind, self.nodes))
        self.shape.append((kind,))
        self.aliases.append(("node", self.nodes))
        return False, None

    def _object(self, value: Any, name: str, path: str, depth: int) -> Any:
        cls = self.classes[name]
        if type(value) is not cls:
            raise ShadowBlocked("root_schema", path)
        fields = {
            "Assembly": S.ASSEMBLY,
            "Ctx": S.CTX,
            "Probe": S.PROBE_FIELDS,
            "AnswerRec": {"decision": "S", "questions": ("frozenset", "T")},
        }[name]
        # Pinned exact classes have an ordinary instance dictionary, no descriptors.
        data = object.__getattribute__(value, "__dict__")
        self._record_fields(data, S.record(fields), path)
        exists, found = self._begin(value, path, name)
        if exists:
            return found
        out = object.__new__(cls)
        self.memo[id(value)] = (self.nodes, out)
        for key, field_schema in fields.items():
            object.__setattr__(
                out,
                key,
                self._visit(data[key], field_schema, path + "." + key, depth + 1),
            )
        self.active.remove(id(value))
        self.tokens.append(("end",))
        return out

    def _record_fields(self, value: Any, schema: Any, path: str) -> dict[str, Any]:
        if type(value) is not dict:
            raise ShadowBlocked("root_schema", path)
        required, optional = schema[1:]
        fields = {**required, **optional}
        for key in value:
            if type(key) is not str:
                raise ShadowBlocked("root_schema", path + "[*]")
            if key in S.FORBIDDEN:
                raise ShadowBlocked("forbidden", path + "[*]")
            if key not in fields:
                raise ShadowBlocked("root_schema", path + "[*]")
        if not required.keys() <= value.keys():
            raise ShadowBlocked("root_schema", path)
        return fields

    def _container(self, value: Any, schema: Any, path: str, depth: int) -> Any:
        kind = schema[0]
        expected = {
            "record": dict,
            "map": dict,
            "memo": dict,
            "list": list,
            "tuple": tuple,
            "set": set,
            "frozenset": frozenset,
            "counter": Counter,
        }[kind]
        if type(value) is not expected:
            raise ShadowBlocked("root_schema", path)
        fields = self._record_fields(value, schema, path) if kind == "record" else {}
        limit = {"children": 200, "ask": 100, "steps": 200, "items": 5000}.get(
            path.rsplit(".", 1)[-1], 20000
        )
        if len(value) > limit:
            raise ShadowBlocked("bounds", path)
        if id(value) in self.memo and (id(value), id(schema)) not in self.validated:
            Graph(self.classes, self.globals_schema, self.opaque).clone(value, schema)
        self.validated.add((id(value), id(schema)))
        exists, found = self._begin(value, path, kind)
        if exists:
            return found
        node_number = self.nodes
        out = self._entries(value, schema, fields, path, depth)
        self.active.remove(id(value))
        self.memo[id(value)] = (node_number, out)
        self.tokens.append(("end",))
        return out

    def _entries(
        self, value: Any, schema: Any, fields: Any, path: str, depth: int
    ) -> Any:
        kind = schema[0]
        if kind in {"record", "map", "memo", "counter"}:
            return self._dictionary(value, schema, fields, path, depth)
        if kind == "tuple" and len(value) != len(schema[1]):
            raise ShadowBlocked("root_schema", path)
        out = []
        for i, entry in enumerate(value):
            spec = schema[1][i] if kind == "tuple" else schema[1]
            out.append(self._visit(entry, spec, path + "[*]", depth + 1))
        return {"list": list, "tuple": tuple, "set": set, "frozenset": frozenset}[kind](
            out
        )

    def _dictionary(
        self, value: Any, schema: Any, fields: Any, path: str, depth: int
    ) -> Any:
        kind, out = schema[0], {}
        for key in value:
            child_path = path + ("." + key if kind == "record" else "[*]")
            if kind == "record":
                spec, new_key = fields[key], key
                self.tokens.append(("field", key))
                self.shape.append(("field", key))
            else:
                spec, key_spec = self._map_specs(schema, key)
                new_key = self._visit(key, key_spec, path + "[*]", depth + 1)
            out[new_key] = self._visit(value[key], spec, child_path, depth + 1)
            if (
                kind == "memo"
                and type(key) is tuple
                and key[0] == "meta"
                and any(row["number"] != number for number, row in out[new_key].items())
            ):
                raise ShadowBlocked("root_schema", "$frame.memo")
        return Counter(out) if kind == "counter" else out

    def _map_specs(self, schema: Any, key: Any) -> tuple[Any, Any]:
        if schema[0] == "memo":
            if id(key) in self.opaque or (
                type(key) is tuple
                and len(key) == 2
                and any(id(part) in self.opaque for part in key)
            ):
                raise ShadowBlocked("opaque_op", "$frame.memo")
            spec = _memo_schema(key)
            return spec, "S" if type(key) is str else ("tuple", ("S", "S"))
        if schema[0] == "counter":
            return "I0", schema[1]
        return schema[2], schema[1]
