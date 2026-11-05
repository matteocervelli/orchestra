from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
import types
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/repository_compat"


@pytest.fixture
def exporter(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "repository_export_test", ROOT / "scripts/export_repository_compat.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pins = tmp_path / "synthetic-reviewed-pins.json"
    pins.write_text(
        json.dumps(
            {
                "runtime_targets": [
                    {
                        "path": f"bin/{name}.py",
                        "before_sha256": hashlib.sha256(
                            (FIXTURES / f"{name}.py").read_bytes()
                        ).hexdigest(),
                    }
                    for name in ("preview_recipes", "action_dedupe")
                ]
            }
        )
    )
    monkeypatch.setattr(module, "PIN_MANIFEST", pins)
    return module


@pytest.fixture
def adapters(exporter, monkeypatch):
    from orchestra.dashboard import repository

    package = types.ModuleType("orchestra_dashboard")
    package.__path__ = []
    monkeypatch.setitem(sys.modules, "orchestra_dashboard", package)
    monkeypatch.setitem(sys.modules, "orchestra_dashboard.repository", repository)
    original = {
        name: (FIXTURES / f"{name}.py").read_text()
        for name in ("preview_recipes", "action_dedupe")
    }
    proposed = exporter.propose(original["preview_recipes"], original["action_dedupe"])
    namespaces = {}
    for name in original:
        module = types.ModuleType(name)
        namespace = module.__dict__
        monkeypatch.setitem(sys.modules, name, module)
        exec(compile(proposed[f"bin/{name}.py"], name, "exec"), namespace)
        namespaces[name] = namespace
    return original, proposed, namespaces


@pytest.mark.parametrize(
    "raw,canonical",
    [
        ("himalaia", "app-himalaia"),
        ("ratio", "app-ratio"),
        ("matteocervelli/app-ratio.", "app-ratio"),
        ("adlimenui", "adlimen-ui"),
        ("atrium.", "atrium"),
    ],
)
def test_real_proposed_normalizer_feeds_canonical_recipe_lookup(
    adapters, raw, canonical
):
    _, _, modules = adapters
    recipe = modules["preview_recipes"]
    item = {"id": "opaque-exact-ID", "repo": raw, "nested": {"ask": [1]}}
    before = deepcopy(item)
    normalized = recipe["normalize_item"](item)
    recipe["R"] = types.SimpleNamespace(
        REPOS=recipe["REPOS"],
        HOST="synthetic.test",
        link_path=lambda repo: "/",
        login_of=lambda repo: {},
    )
    recipe["S"] = types.SimpleNamespace(
        next_n=lambda others, repo: 1,
        alloc_ports=lambda others, serve, free: {"https": 9000},
        target_of=lambda it: (None, "synthetic-ref"),
    )
    recipe["serve_status"] = lambda deps: {}
    deps = types.SimpleNamespace(pid=123, port_free=lambda port: True)
    paths = types.SimpleNamespace(dir=lambda key: Path("synthetic") / key)
    result = recipe["new_entry"](
        {"previews": {}}, item["id"], normalized, deps, paths, "synthetic-time"
    )
    assert (result["item"], result["repo"]) == (item["id"], canonical)
    assert normalized["nested"] is item["nested"] and item == before
    assert set(recipe["REPOS"]) == {"app-himalaia", "app-ratio", "adlimen-ui", "atrium"}


@pytest.mark.parametrize("step", ["promote", "release"])
@pytest.mark.parametrize(
    "old,new",
    [
        ("ratio", "app-ratio"),
        ("app-ratio", "ratio"),
        ("matteocervelli/app-ratio.", "ratio"),
    ],
)
def test_real_proposed_dedupe_matches_old_records_without_mutation(
    adapters, tmp_path, step, old, new
):
    _, _, modules = adapters
    action = modules["action_dedupe"]
    actions = tmp_path / "actions"
    actions.mkdir()
    record = {
        "item": "old-ID-exact",
        "intent": step,
        "scope": "repo:" + old,
        "text": "original",
        "status": "unchanged",
    }
    path = actions / "001.json"
    payload = json.dumps(record)
    path.write_text(payload)
    old_info, new_info = {"repo": old}, {"repo": new}
    before = deepcopy((record, old_info, new_info))
    index = types.SimpleNamespace(
        get=lambda item: old_info if item == record["item"] else {}
    )
    scope = action["scope_of"](step, "new-ID-exact", new_info)
    assert scope == "repo:app-ratio"
    assert action["find_active"](actions, tmp_path, index, step, "repo:" + new) == (
        path.name,
        record,
    )
    assert path.read_text() == payload
    assert (record, old_info, new_info) == before
    assert action["scope_of"]("review", "new-ID-exact", new_info) == "item:new-ID-exact"
    assert (
        action["find_active"](actions, tmp_path, index, step, "repo:foreign/app-ratio")
        is None
    )


def test_special_release_snapshot_scopes_are_byte_identical(adapters):
    original, _, modules = adapters
    old = {}
    exec(compile(original["action_dedupe"], "old", "exec"), old)
    record = {
        "project": "ratio",
        "version": "1.2.3",
        "base": {"sha": "a"},
        "candidates": [{"number": 2, "sha": "b"}, {"number": 1, "sha": "c"}],
    }
    before = deepcopy(record)
    for intent in ("release_prepare", "deploy"):
        args = (intent, "opaque-ID", {"repo": "ratio"}, record)
        assert modules["action_dedupe"]["scope_of"](*args) == old["scope_of"](*args)
    assert record == before


def test_only_target_function_bytes_and_ast_change(adapters, exporter):
    original, proposed, _ = adapters
    targets = {
        "preview_recipes": {"normalize_item"},
        "action_dedupe": {"scope_of", "find_active"},
    }
    for name, functions in targets.items():
        after = proposed[f"bin/{name}.py"]
        assert exporter.outside_functions(
            original[name], functions
        ) == exporter.outside_functions(after, functions)

        def untouched(text, functions=functions):
            tree = ast.parse(text)
            tree.body = [
                n
                for n in tree.body
                if not isinstance(n, ast.FunctionDef) or n.name not in functions
            ]
            return ast.dump(tree, include_attributes=False)

        assert untouched(original[name]) == untouched(after)


def test_bundle_is_three_target_hash_bound_and_rejects_dependency_drift(
    exporter, tmp_path
):
    runtime = tmp_path / "synthetic"
    package = runtime / "bin/orchestra_dashboard"
    package.mkdir(parents=True)
    common = (ROOT / "src/orchestra/dashboard/common.py").read_bytes()
    (package / "common.py").write_bytes(common)
    for name in ("preview_recipes", "action_dedupe"):
        (runtime / "bin" / f"{name}.py").write_bytes(
            (FIXTURES / f"{name}.py").read_bytes()
        )
    before = {
        str(p.relative_to(runtime)): p.read_bytes() for p in runtime.rglob("*.py")
    }
    output = tmp_path / "proposal"
    report = exporter.build_bundle(runtime, output)
    assert report["applied"] is False
    assert report["dependency_sha256"] == hashlib.sha256(common).hexdigest()
    assert {row["path"] for row in report["files"]} == {
        "bin/orchestra_dashboard/repository.py",
        "bin/preview_recipes.py",
        "bin/action_dedupe.py",
    }
    for row in report["files"]:
        raw = before.get(row["path"])
        assert row["before_sha256"] == (
            hashlib.sha256(raw).hexdigest() if raw is not None else None
        )
        after = (output / "after" / row["path"]).read_bytes()
        assert row["after_sha256"] == hashlib.sha256(after).hexdigest()
    assert before == {
        str(p.relative_to(runtime)): p.read_bytes() for p in runtime.rglob("*.py")
    }
    (package / "common.py").write_text("# drift\n")
    with pytest.raises(ValueError, match=r"^authority_dependency_drift$"):
        exporter.build_bundle(runtime, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_ambiguous_donor_and_existing_helper_fail_closed(exporter, tmp_path):
    preview = (FIXTURES / "preview_recipes.py").read_text()
    action = (FIXTURES / "action_dedupe.py").read_text()
    with pytest.raises(ValueError):
        exporter.propose(preview.replace("def normalize_item", "def different"), action)
    with pytest.raises(ValueError):
        exporter.propose(
            preview, action.replace('info.get("repo")', 'info.get("different")')
        )
    runtime = tmp_path / "synthetic"
    package = runtime / "bin/orchestra_dashboard"
    package.mkdir(parents=True)
    helper = package / "repository.py"
    helper.write_text("# existing helper must never be overwritten\n")
    with pytest.raises(ValueError, match=r"^existing_output_or_helper$"):
        exporter.build_bundle(runtime, tmp_path / "rejected")
    assert helper.read_text() == "# existing helper must never be overwritten\n"
    assert not (tmp_path / "rejected").exists()


@pytest.mark.parametrize(
    "mutation", ["normalizer_body", "matching_body", "repo_steps", "recipe_owner"]
)
def test_donor_mutations_fail_before_creating_any_output(exporter, tmp_path, mutation):
    runtime = tmp_path / "synthetic"
    package = runtime / "bin/orchestra_dashboard"
    package.mkdir(parents=True)
    (package / "common.py").write_bytes(
        (ROOT / "src/orchestra/dashboard/common.py").read_bytes()
    )
    for name in ("preview_recipes", "action_dedupe"):
        text = (FIXTURES / f"{name}.py").read_text()
        old, new = {
            "normalizer_body": (
                'key = item.get("repo")',
                'key = item.get("alternate_repo")',
            ),
            "matching_body": (
                "if not step or not actions_dir.is_dir():",
                'if not step or scope == "repo:locked" or not actions_dir.is_dir():',
            ),
            "repo_steps": (
                'REPO_STEPS = ("promote", "release")',
                'REPO_STEPS = ("promote", "release", "review")',
            ),
            "recipe_owner": ('"matteocervelli/" + name', '"foreign/" + name'),
        }[mutation]
        target = (
            "preview_recipes"
            if mutation in ("normalizer_body", "recipe_owner")
            else "action_dedupe"
        )
        if name == target:
            assert old in text
            text = text.replace(old, new)
        (runtime / "bin" / f"{name}.py").write_text(text)
    output = tmp_path / "rejected"
    with pytest.raises(ValueError, match=r"^runtime_donor_drift$"):
        exporter.build_bundle(runtime, output)
    assert not output.exists()


@pytest.mark.parametrize(
    "record_intent,request_intent,scope",
    [
        ("release", "promote", "repo:ratio"),
        ("review", "review", "item:different-exact-ID"),
        ("review", "review", "repo:ratio"),
    ],
)
def test_dedupe_does_not_match_other_intents_or_item_scopes(
    adapters, tmp_path, record_intent, request_intent, scope
):
    _, _, modules = adapters
    actions = tmp_path / "actions"
    actions.mkdir()
    record = {"item": "original-exact-ID", "intent": record_intent}
    path = actions / "001.json"
    payload = json.dumps(record)
    path.write_text(payload)
    index = types.SimpleNamespace(get=lambda item: {"repo": "app-ratio"})
    assert (
        modules["action_dedupe"]["find_active"](
            actions, tmp_path, index, request_intent, scope
        )
        is None
    )
    if record_intent == "review":
        assert modules["action_dedupe"]["find_active"](
            actions, tmp_path, index, "review", "item:original-exact-ID"
        ) == (path.name, record)
    assert path.read_text() == payload
