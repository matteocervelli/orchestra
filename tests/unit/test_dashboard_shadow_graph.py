"""Closed synthetic shadow graphs; no live objects or readers."""

import pytest

from orchestra.dashboard.shadow_graph import Graph, ShadowBlocked
from orchestra.dashboard.shadow_schema import record


def test_clone_preserves_cross_root_mutable_alias_and_opaque_reference() -> None:
    report = "synthetic opaque report"
    shared = {"slug": "synthetic", "report": report}
    schema = record({"slug": "ID", "report": "OSTR"})
    source = {"left": shared, "right": shared}
    graph = Graph()
    clone = graph.clone(source, record({"left": schema, "right": schema}))
    assert clone is not source
    assert clone["left"] is clone["right"] and clone["left"] is not shared
    assert clone["left"]["report"] is report
    assert graph.equivalent(source, clone)
    clone["right"] = dict(clone["right"])
    assert not graph.equivalent(source, clone)


def test_unknown_and_forbidden_keys_block_without_value_access() -> None:
    class Canary(dict):
        def __getitem__(self, key):
            raise AssertionError("PRIVATE_CANARY")

    with pytest.raises(ShadowBlocked, match="root_schema"):
        Graph().clone(Canary(secret="ignored"), record({}))
    for key, code in (("headers", "forbidden"), ("undeclared", "root_schema")):
        with pytest.raises(ShadowBlocked, match=code):
            Graph().clone({key: object()}, record({}))


def test_record_required_optional_nullable_and_exact_types() -> None:
    schema = record({"slug": "ID", "cost": "N0?"}, {"running": "B"})
    assert Graph().clone({"slug": "synthetic", "cost": None}, schema)["cost"] is None
    for value in ({"slug": "synthetic"}, {"slug": "synthetic", "cost": True}):
        with pytest.raises(ShadowBlocked):
            Graph().clone(value, schema)


def test_cycle_is_blocked_not_truncated() -> None:
    data = []
    data.append(data)
    with pytest.raises(ShadowBlocked):
        Graph().clone(data, ("list", "S"))


def test_shared_map_cannot_bypass_second_schema_validation() -> None:
    shared = {"slug": "synthetic"}
    schema = record({"left": ("map", "S", "T"), "right": record({"cost": "N0"})})
    with pytest.raises(ShadowBlocked, match="root_schema"):
        Graph().clone({"left": shared, "right": shared}, schema)


def test_nested_alias_numbering_is_stable_after_clone() -> None:
    leaf = {"slug": "synthetic"}
    left = {"entries": [leaf, leaf]}
    schema = record({"entries": ("list", record({"slug": "ID"}))})
    graph = Graph()
    right = graph.clone(left, schema)
    assert graph.equivalent(left, right)
    right["entries"][1] = dict(right["entries"][1])
    assert not graph.equivalent(left, right)


def test_same_atom_cannot_cross_opaque_and_normal_roles() -> None:
    opaque = "private-only-value"
    source = {"report": opaque, "title": opaque}
    with pytest.raises(ShadowBlocked, match="opaque_op"):
        Graph().clone(source, record({"report": "OSTR", "title": "T"}))


def test_shared_map_values_are_validated_in_each_schema_role() -> None:
    shared = {"synthetic": "not-a-cost"}
    schema = record({"left": ("map", "ID", "T"), "right": ("map", "ID", "N0")})
    with pytest.raises(ShadowBlocked):
        Graph().clone({"left": shared, "right": shared}, schema)


@pytest.mark.parametrize("reverse", [False, True])
def test_enum_never_compares_an_opaque_atom_in_either_order(reverse: bool) -> None:
    opaque = "".join(["synthetic", "-enum"])
    fields = {"report": "OSTR", "role": ("enum", ("synthetic-enum",))}
    if reverse:
        fields = dict(reversed(tuple(fields.items())))
    with pytest.raises(ShadowBlocked, match="opaque_op"):
        Graph().clone(dict.fromkeys(fields, opaque), record(fields))
    assert Graph().clone(
        {"role": "synthetic-enum"}, record({"role": fields["role"]})
    ) == {"role": "synthetic-enum"}


def test_union_cannot_read_previously_opaque_atom_to_select_variant() -> None:
    opaque = "".join(["synthetic", "-union"])
    with pytest.raises(ShadowBlocked, match="opaque_op"):
        Graph().clone(
            {"report": opaque, "role": opaque},
            record(
                {
                    "report": "OSTR",
                    "role": ("union", (("enum", ("synthetic-union",)), "T")),
                }
            ),
        )


@pytest.mark.parametrize(
    "schema", ["T", ("enum", ("synthetic-preflight",)), ("union", ("T", "S"))]
)
def test_role_preflight_precedes_ordinary_atom_validation(monkeypatch, schema) -> None:
    import orchestra.dashboard.shadow_graph as module

    opaque = "".join(["synthetic", "-preflight"])
    original = module._atom
    seen = []

    def atom(value, kind):
        seen.append(value is opaque)
        return original(value, kind)

    monkeypatch.setattr(module, "_atom", atom)
    with pytest.raises(ShadowBlocked, match="opaque_op"):
        Graph().clone(
            {"role": opaque, "report": opaque},
            record({"role": schema, "report": "OSTR"}),
        )
    assert True not in seen


def test_preflight_has_global_budget_and_propagates_bounds_through_union(
    monkeypatch,
) -> None:
    import orchestra.dashboard.shadow_graph as module

    monkeypatch.setattr(module, "EDGE_LIMIT", 12, raising=False)
    data = ["synthetic"] * 20
    with pytest.raises(ShadowBlocked, match="bounds"):
        Graph().clone(data, ("union", (("list", "T"), ("list", "S"))))


def test_preflight_visits_shared_dag_role_once() -> None:
    leaf = {"slug": "synthetic"}
    spec = record({"slug": "ID"})
    for _ in range(12):
        leaf = [leaf, leaf]
        spec = ("list", spec)
    graph = Graph()
    graph.clone(leaf, spec)
    assert graph.preflight_edges < 100


@pytest.mark.parametrize(
    "field", ["transcript", "auth", "headers", "header", "env", "report"]
)
def test_unknown_or_forbidden_values_are_never_obtained_or_copied(field) -> None:
    class Poison:
        def __deepcopy__(self, memo):
            raise AssertionError("PRIVATE_SENTINEL")

        def __repr__(self):
            raise AssertionError("PRIVATE_SENTINEL")

        def __eq__(self, other):
            raise AssertionError("PRIVATE_SENTINEL")

    with pytest.raises(ShadowBlocked) as caught:
        Graph().clone({field: Poison()}, record({}))
    assert caught.value.path == "$roots[*]" and caught.value.count == 1
    assert "PRIVATE_SENTINEL" not in str(caught.value)


def test_nonstring_or_string_subclass_key_never_hashed_by_observer() -> None:
    class Key(str):
        armed = False

        def __hash__(self):
            if self.armed:
                raise AssertionError("PRIVATE_SENTINEL")
            return 1

    key = Key("synthetic")
    data = {key: object()}
    key.armed = True
    with pytest.raises(ShadowBlocked, match="root_schema"):
        Graph().clone(data, record({}))


def test_local_caller_list_shapes_and_cross_root_record_aliases() -> None:
    from dashboard_shadow_fixture import boundary

    from orchestra.dashboard import shadow_schema as schemas
    from orchestra.dashboard.shadow_profile import approved_profile

    data = boundary()
    # The source caller holds lists; Ctx holds their indexed views.
    row = {"slug": "synthetic", "outcome": "synthetic", "gates": None, "note": None}
    decision = {"id": "synthetic-decision", "title": "synthetic"}
    data["locals"]["ledger"] = [row]
    data["locals"]["led"]["synthetic"] = row
    data["locals"]["by_slug"]["synthetic"] = [row]
    data["locals"]["decisions"] = [decision]
    data["ctx"].decisions[decision["id"]] = decision
    profile = approved_profile(
        data["baseline"], data["candidate"], data["asm"], data["ctx"], data["callbacks"]
    )
    graph = Graph(profile.classes, profile.globals_schema)
    root = {
        "asm": data["asm"],
        "ctx": data["ctx"],
        "locals": data["locals"],
        "original_notes": data["notes"],
        "return_notes": None,
        "tasks": data["tasks"],
        "globals": profile.globals,
    }
    copied = graph.clone(root, schemas.record(schemas.ROOT_FIELDS))
    assert copied["locals"]["ledger"][0] is copied["asm"].led["synthetic"]
    assert copied["locals"]["ledger"][0] is copied["ctx"].ledger["synthetic"][0]
    assert (
        copied["locals"]["decisions"][0]
        is copied["ctx"].decisions["synthetic-decision"]
    )


def test_memo_key_selection_does_not_read_an_opaque_atom(monkeypatch) -> None:
    import orchestra.dashboard.shadow_graph as module

    opaque = "".join(["synthetic", "-repo"])
    real = module._atom
    seen = []

    def atom(value, kind):
        seen.append(value is opaque)
        return real(value, kind)

    monkeypatch.setattr(module, "_atom", atom)
    with pytest.raises(ShadowBlocked, match="opaque_op"):
        Graph().clone(
            {"memo": {("meta", opaque): {}}, "report": opaque},
            record({"memo": "Memo", "report": "OSTR"}),
        )
    assert True not in seen


@pytest.mark.parametrize(
    "field,limit", [("children", 200), ("ask", 100), ("steps", 200)]
)
def test_per_owner_collection_bounds_precede_leaf_processing(field, limit) -> None:
    value = {field: ["synthetic"] * (limit + 1)}
    with pytest.raises(ShadowBlocked, match="bounds"):
        Graph().clone(value, record({field: ("list", "T")}))


@pytest.mark.parametrize(
    "host,path", [("github.com", "pull"), ("git.adlimen.dev", "pulls")]
)
def test_review_nb1_actual_qualified_reference_domains_are_admitted(host, path) -> None:
    from orchestra.dashboard.provenance import qualified_pr
    from orchestra.dashboard.shadow_schema import QPR

    ref = qualified_pr(
        {"number": 207, "url": f"https://{host}/matteocervelli/nexus/{path}/207"},
        "nexus",
    )
    assert ref is not None and ref["host"] == host
    assert Graph().clone(ref, QPR) == ref
    with pytest.raises(ShadowBlocked):
        Graph().clone({**ref, "host": "unknown.invalid"}, QPR)
