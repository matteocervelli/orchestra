"""Synthetic selected donor functions; no operational imports or note files."""

import ast
import copy
import hashlib
from pathlib import Path
from typing import Any

import pytest
from test_dashboard_runtime_export import exporter

from orchestra.dashboard.curation import curate

FIXTURE = (
    Path(__file__).parents[1] / "fixtures/dashboard_alias_intent/merge_selected.py.txt"
)
INFO = {"kind": "information", "text": "X"}


def execute(source: str) -> dict[str, Any]:
    """Execute only selected pure functions with synthetic dependency inputs."""
    tree = ast.parse(source)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    # Real canonical selector is wired exactly as the emitted import specifies.
    from orchestra.dashboard import curation

    namespace: dict[str, Any] = {
        "copy": copy,
        "hashlib": hashlib,
        "clean_steps": lambda rows: rows or [],
        "is_nothing": lambda text: text.startswith("Niente"),
        "STATUSES": ["Todo", "Doing", "Done", "Dropped"],
        "select_needs_intent": getattr(curation, "select_needs_intent", None),
    }
    exec(
        compile(ast.Module(body=functions, type_ignores=[]), "<synthetic>", "exec"),
        namespace,
    )
    return namespace


@pytest.mark.parametrize(
    "first,second,target,expected",
    [
        ({"needs": "X", "needs_intent": INFO}, {"needs": "X"}, "a", None),
        ({"needs": "X", "needs_intent": INFO}, {"needs": "Y"}, "a", None),
        ({"needs": "X"}, {"needs_intent": INFO}, "a", None),
        ({"needs_intent": INFO}, {"needs": "X"}, "a", None),
        ({"needs": "Y"}, {"needs": "X", "needs_intent": INFO}, "a", INFO),
        (
            {"needs": "X", "edited_fields": ["needs"]},
            {"needs": "X", "needs_intent": INFO},
            "a",
            None,
        ),
        (
            {"needs": "X", "needs_intent": INFO},
            {"needs": "X", "edited_fields": ["needs"]},
            "bb",
            None,
        ),
        (
            {"needs": "X"},
            {"needs": "X", "needs_intent": INFO, "merged_into": "a"},
            "a",
            None,
        ),
        (
            {"needs": "X"},
            {"needs": "X", "needs_intent": INFO, "status": "Dropped"},
            "a",
            None,
        ),
        ({"needs": "X"}, {"needs": "Niente: vedi a", "needs_intent": INFO}, "a", None),
        ({"needs": "X", "needs_intent": INFO}, {"needs": ""}, "a", None),
        ({"needs": "X", "needs_intent": INFO}, {"needs": None}, "a", None),
        ({"needs_intent": INFO}, {}, "a", None),
        (
            {"needs": "Y"},
            {"needs": "X", "needs_intent": {"kind": "unknown", "text": "X"}},
            "a",
            None,
        ),
        (
            {"needs": "Y"},
            {
                "needs": "X",
                "needs_intent": {
                    "kind": "information",
                    "text": "X",
                    "extra": "ignored",
                },
            },
            "a",
            None,
        ),
        (
            {"needs": "X", "needs_intent": INFO},
            {"needs_intent": {"kind": "request", "text": "X"}},
            "a",
            INFO,
        ),
    ],
)
def test_emitted_effective_note_pairs_source_and_preserves_other_fields(
    first: dict[str, Any], second: dict[str, Any], target: str, expected: Any
) -> None:
    source = FIXTURE.read_text()
    adapted = exporter().dedupe_intent_adapter(source)
    legacy, candidate = execute(source), execute(adapted)
    notes = {"a": copy.deepcopy(first), "bb": copy.deepcopy(second)}
    for alias, note in notes.items():
        note.update(
            {
                "ask": [{"id": "same-question", "question": alias}],
                "steps": [{"id": "same-step", "text": alias}],
                "steps_checked": {"same-step": alias == "a"},
                "pin": True,
                "priority": "P1" if alias == "a" else "P0",
                "hide": alias == "bb",
                "ask_overrides": [alias],
            }
        )
    before = copy.deepcopy(notes)
    old = legacy["effective_note"](notes, list(notes), target, [])
    new = candidate["effective_note"](notes, list(notes), target, [])
    assert new.get("needs_intent") == expected
    assert {k: v for k, v in old.items() if k != "needs_intent"} == {
        k: v for k, v in new.items() if k != "needs_intent"
    }
    assert notes == before
    # Synthetic migration's in-memory assignment boundary must persist the pair.
    migrated = copy.deepcopy(notes)
    migrated[target] = candidate["effective_note"](migrated, list(notes), target, [])
    assert migrated[target].get("needs_intent") == expected
    for alias in notes:
        if alias != target:
            migrated[alias]["merged_into"] = target
    repeated = candidate["effective_note"](migrated, list(notes), target, [])
    assert repeated.get("needs_intent") == expected
    if isinstance(new.get("needs"), str):
        item: dict[str, Any] = {"pages": {}}
        curate(item, new, {})
        assert item.get("needs_intent") == expected


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.replace("def merge_notes(", "def other_name("),
        lambda s: s.replace(
            "target_card: dict | None=None", "target_card: dict | None={}"
        ),
        lambda s: s.replace("not superseded and", "superseded and"),
        lambda s: s.replace("(len(s), s)", "(s, len(s))"),
        lambda s: s + "\nmerge_notes = None\n",
        lambda s: s.replace("out[key] = copy.deepcopy(value)", "out[key] = value"),
        lambda s: s.replace(
            "out[key] = copy.deepcopy(value)",
            "out[key] = copy.deepcopy(value); print('side effect')",
        ),
        lambda s: s.replace("'ask_overrides',", "'new_scalar_key', 'ask_overrides',"),
    ],
)
def test_adapter_rejects_malformed_or_changed_donor(change: Any) -> None:
    source = FIXTURE.read_text()
    changed = change(source)
    assert changed != source
    with pytest.raises(ValueError, match="merge_notes"):
        exporter().dedupe_intent_adapter(changed)


def test_adapter_changes_only_merge_symbol_and_canonical_import() -> None:
    source = FIXTURE.read_text()
    adapted = exporter().dedupe_intent_adapter(source)
    original = {
        n.name: ast.dump(n)
        for n in ast.parse(source).body
        if isinstance(n, ast.FunctionDef)
    }
    emitted = {
        n.name: ast.dump(n)
        for n in ast.parse(adapted).body
        if isinstance(n, ast.FunctionDef)
    }
    assert original.keys() == emitted.keys()
    assert {key for key in original if original[key] != emitted[key]} == {"merge_notes"}
    imports = [
        ast.unparse(n) for n in ast.parse(adapted).body if isinstance(n, ast.ImportFrom)
    ]
    assert imports == ["from orchestra_dashboard.curation import select_needs_intent"]


@pytest.mark.parametrize("ownership", [False, True])
def test_missing_dedupe_donor_rejects_before_output(
    tmp_path: Path, ownership: bool
) -> None:
    from test_dashboard_runtime_export import synthetic_donors

    module = exporter()
    donor, output = tmp_path / "donor", tmp_path / "output"
    expected = synthetic_donors(donor)
    expected.pop("bin/wi_dedupe.py")
    error = ValueError if ownership else module.MissingDedupeDonorError
    message = (
        "incomplete ownership source vector"
        if ownership
        else "missing dedupe intent donor"
    )
    with pytest.raises(error, match=message):
        module.build_bundle(
            donor, output, expected, include_project_ownership=ownership
        )
    assert not output.exists()


def test_old_core_inventory_requires_separate_six_file_review(tmp_path: Path) -> None:
    import json

    from test_dashboard_runtime_export import synthetic_donors

    module = exporter()
    donor, applied, output = tmp_path / "donor", tmp_path / "old", tmp_path / "new"
    expected = synthetic_donors(donor)
    module.build_bundle(donor, applied, expected)
    module.build_bundle(donor, output, expected)
    manifest = json.loads((applied / "manifest.json").read_text())
    historical = json.loads(
        (FIXTURE.parent / "prechange_core_inventory.json").read_text()
    )
    manifest["files"] = [
        r for r in manifest["files"] if r["path"] in historical["paths"]
    ]
    assert {r["path"] for r in manifest["files"]} == set(historical["paths"])
    (applied / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(
        module.DedupeInventoryTransitionError, match=r"six-file.*review"
    ):
        module.build_applied_delta(applied, output)
    assert not (output / "delta.diff").exists()
    assert not (output / "delta-manifest.json").exists()


def test_provenance_describes_current_inactive_candidate() -> None:
    import json

    from test_dashboard_runtime_export import ROOT

    provenance = json.loads(
        (ROOT / "docs/provenance/dashboard-card-producer-20261027.json").read_text()
    )
    assert provenance["runtime_export"]["core_excludes"] == ["bin/wi_identity.py"]
    assert (
        provenance["runtime_export"]["dedupe_intent_candidate"]["runtime_accepted"]
        is False
    )
    path = "src/orchestra/dashboard/curation.py"
    assert (
        provenance["canonical_files"][path]
        == hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    )


def test_core_bundle_keeps_other_symbols_and_imports_and_imports_helper(
    tmp_path: Path,
) -> None:
    import subprocess
    import sys

    from test_dashboard_runtime_export import synthetic_donors

    donor, output = tmp_path / "donor", tmp_path / "output"
    expected = synthetic_donors(donor)
    before = (donor / "bin/wi_dedupe.py").read_text()
    exporter().build_bundle(donor, output, expected)
    emitted = (output / "bin/wi_dedupe.py").read_text()
    old = {
        n.name: ast.dump(n)
        for n in ast.parse(before).body
        if isinstance(n, ast.FunctionDef)
    }
    new = {
        n.name: ast.dump(n)
        for n in ast.parse(emitted).body
        if isinstance(n, ast.FunctionDef)
    }
    assert old.keys() == new.keys()
    assert {k for k in old if old[k] != new[k]} == {"merge_notes"}

    def imports(source: str) -> list[str]:
        return [
            ast.dump(n)
            for n in ast.parse(source).body
            if isinstance(n, (ast.Import, ast.ImportFrom))
        ]

    added = ast.dump(
        ast.parse("from orchestra_dashboard.curation import select_needs_intent").body[
            0
        ]
    )
    assert [n for n in imports(emitted) if n != added] == imports(before)
    assert imports(emitted).count(added) == 1
    assert "canonical_collapse" not in emitted
    assert "select_needs_intent(out, note)" in emitted
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import wi_dedupe, orchestra_dashboard.curation as c; "
            "assert wi_dedupe.select_needs_intent is c.select_needs_intent",
        ],
        cwd=output / "bin",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (donor / "bin/wi_dedupe.py").read_text() == before


@pytest.mark.parametrize("mutation", ["collision", "docstring"])
def test_invalid_donor_shape_rejects_before_bundle_output(
    tmp_path: Path, mutation: str
) -> None:
    from test_dashboard_runtime_export import synthetic_donors

    donor, output = tmp_path / "donor", tmp_path / "output"
    expected = synthetic_donors(donor)
    path = donor / "bin/wi_dedupe.py"
    source = path.read_text()
    changed = (
        source + "\nselect_needs_intent = None\n"
        if mutation == "collision"
        else source.replace("Specific child text wins", "Different docstring")
    )
    assert changed != source
    path.write_text(changed)
    expected["bin/wi_dedupe.py"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="merge_notes"):
        exporter().build_bundle(donor, output, expected)
    assert not output.exists()


def test_python_ast_version_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    module = exporter()
    with monkeypatch.context() as patch:
        patch.setattr(module.sys, "version_info", (3, 13, 0))
        with pytest.raises(ValueError, match=r"requires Python 3\.12"):
            module.dedupe_intent_adapter(FIXTURE.read_text())


def test_fixture_is_bound_to_reviewed_donor_and_ast() -> None:
    import json

    from test_dashboard_runtime_export import ROOT

    manifest = json.loads((FIXTURE.parent / "manifest.json").read_text())
    provenance = json.loads(
        (ROOT / "docs/provenance/dashboard-card-producer-20261027.json").read_text()
    )
    donor = next(
        row for row in provenance["donors"] if row["donor"] == manifest["donor"]
    )
    assert manifest["donor_sha256"] == donor["sha256"]
    assert (
        manifest["fixture_sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    )
    node = next(
        n
        for n in ast.parse(FIXTURE.read_text()).body
        if isinstance(n, ast.FunctionDef) and n.name == manifest["source_function"]
    )
    assert (
        manifest["source_function_ast_sha256"]
        == hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
    )
    assert manifest["source_function_ast_sha256"] == exporter().MERGE_NOTES_AST_SHA256
    assert manifest["runtime_accepted"] is False


def test_absent_dedupe_file_has_typed_error_without_output(tmp_path: Path) -> None:
    from test_dashboard_runtime_export import synthetic_donors

    module = exporter()
    donor, output = tmp_path / "donor", tmp_path / "output"
    expected = synthetic_donors(donor)
    # A nonexistent root models absent files without deleting a fixture.
    with pytest.raises(
        module.MissingDedupeDonorError, match="missing dedupe intent donor"
    ):
        module.build_bundle(tmp_path / "absent-donor", output, expected)
    assert not output.exists()
