import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


def exporter() -> Any:
    spec = importlib.util.spec_from_file_location(
        "dashboard_export_test", ROOT / "scripts/export_dashboard_producer.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_donors(root: Path) -> dict[str, str]:
    files = {
        "wi_common": (
            "import re\nO = 0\nREPOS = {}\nFULL = {}\n"
            "REF_RE = re.compile('')\ndef short_repo(na"
            "me): return name\ndef refs(text): return []\n"
        ),
        "wi_status": "STATUSES = []\nCLOSED = ()\n",
        "wi_text": "def fill_text(it, curated, asking): return None\n",
        "wi_fields": (
            "CALL_KINDS = ()\nACTION_RE = None\n"
            "def ask_kind(a, it, decision): return 'legacy'\n"
        ),
        "wi_repos": (
            "ALIASES = {}\nNAME = URL = REF = None\n"
            "def canonical(value): return value\ndef clean(values): return values\n"
            "def reference_repos(text): return []\ndef task_repos(text): return []\n"
            "def derive(it, card, note, tasks, spawns, ledger): return []\n"
        ),
        "wi_identity": "def groups(items, notes, tasks, pr_issues): return {}, {}\n",
        "wi_quality": (
            'def audit(data): return {"atrium": "https://example.'
            'test/board?item="}\ndef main(): return 0\n'
        ),
        "wi_notes": (
            "import fcntl\nfrom contextlib import contextmanager\n"
            "from typing import Iterator\nfrom pathlib import Path\n"
            "@contextmanager\ndef notes_lock(root: Path) -> Iterator[None]:\n"
            '    with (root / "lock").open("a") as lock:\n'
            "        fcntl.flock(lock, fcntl.LOCK_EX)\n        yield\n"
            "def active_sweeps(root: Path): return []\n"
        ),
        "wi_sources": (
            "from pathlib import Path\nfrom types import SimpleNamespace\n"
            'C = SimpleNamespace(O=Path("synthetic"))\n'
            "def tasks(): return {str(C.O): {}}\n"
        ),
        "wi_dedupe": (
            "import copy\nimport hashlib\nfrom wi_status import STATUSES\n"
            "def clean_steps(rows): return rows or []\n"
            "def is_nothing(text): return text.startswith('Niente')\n"
            + (
                ROOT / "tests/fixtures/dashboard_alias_intent/merge_selected.py.txt"
            ).read_text()
            + "\ndef collapse(asm, notes, tasks): return {}\n"
        ),
        "workitems": (
            "from pathlib import Path\nimport wi_repos\nfrom wi_common import REPOS\n"
            "TEXT_KEYS = ()\ndef match_pages(*args, **kwargs): return None\n"
            "def curate(i"
            't, note, card): return set(), ""\ndef finish(it, iid,'
            " ctx):\n    note = {}\n    card = {}\n    rows = []\n"
            "    it['repos'] = wi_repos.derive("
            "it, card, note, ctx.tasks, ctx.spawns, rows)\n"
            "    if not (it.get('pr') or it.get('issue')):\n"
            "        it['repo'] = it['repos'][0]\n"
            "    repo = REPOS.get(it['repo'], it['repo'])\n"
            "    match_pages(it, iid, repo, ctx.pages, "
            "number_repos=ctx.number_repos, html=ctx.html)\n"
            "    it['repo'] = it['repo'] or 'orchestra'\n    curated, prev"
            "iew = curate(it, note, card)\n    return curated, preview\n"
            "def _detail_item(item, "
            "ledger): return item\ndef read_json(path, default): r"
            "eturn default\ndef _ledger_for(item, ledger): return "
            "ledger\ndef publish(data, out=None):\n    out = out or"
            ' Path("synthetic.json")\n    public = {"generated": d'
            'ata["generated"], "items": data["items"]}\n    for it'
            'em in data["items"]:\n        _detail_item(item, [], '
            "board=public) if False else _detail_item(item, [])\n"
        ).replace(
            (
                "        _detail_item(item, [], board=public) if Fals"
                "e else _detail_item(item, [])"
            ),
            "        _detail_item(item, [])",
        ),
    }
    expected = {}
    for name, text in files.items():
        if name == "workitems":
            text = text.replace(
                '    public = {"generated": data["generated"], "items": data["items"]}',
                '    items = [item for item in data.get("items", []) '
                "if isinstance(item, dict)]\n"
                "    live = items\n"
                '    public = {"generated": data["generated"], "items": live}',
            )
            text = text.replace(
                "def publish(data, out=None):",
                "def quality_audit(data): return {}\nTERMINAL_STATUSES = ()\n"
                "def publish(data, out=None):",
            )
            text += (
                '    quality_audit({**data, "items": live})\n    return public, out\n'
            )
        relative = f"bin/{name}.py"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        expected[relative] = hashlib.sha256(text.encode()).hexdigest()
    return expected


def test_export_is_inert_byte_identical_and_adapters_import_canonical_objects(
    tmp_path: Path,
) -> None:
    donor = tmp_path / "donor"
    expected = synthetic_donors(donor)
    output = tmp_path / "bundle"
    report = exporter().build_bundle(donor, output, expected)
    assert report["applied"] is False
    for path in (ROOT / "src/orchestra/dashboard").glob("*.py"):
        assert (
            output / "bin/orchestra_dashboard" / path.name
        ).read_bytes() == path.read_bytes()
    for relative, digest in expected.items():
        assert hashlib.sha256((donor / relative).read_bytes()).hexdigest() == digest
    code = (
        "import wi_text, orchestra_dashboard.text; assert wi_"
        "text.fill_text is orchestra_dashboard.text.fill_text"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=output / "bin",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads((output / "manifest.json").read_text())
    assert all(row["after_sha256"] for row in manifest["files"])
    # Every changed consumer compiles; this does not execute source readers.
    for path in (output / "bin").glob("*.py"):
        compile(path.read_text(), str(path), "exec")


def test_donor_drift_fails_before_any_output(tmp_path: Path) -> None:
    donor = tmp_path / "donor"
    expected = synthetic_donors(donor)
    (donor / "bin/wi_text.py").write_text("# changed\n")
    output = tmp_path / "bundle"
    with pytest.raises(ValueError, match="hash mismatch"):
        exporter().build_bundle(donor, output, expected)
    assert not output.exists()


def test_exported_fields_preserve_symbols_and_use_one_classifier(tmp_path: Path):
    module = exporter()
    donor = tmp_path / "donor"
    expected = synthetic_donors(donor)
    selected = ROOT / "tests/fixtures/dashboard_ownership/wi_fields_selected.py.txt"
    source = "from __future__ import annotations\nimport re\n" + selected.read_text()
    (donor / "bin/wi_fields.py").write_text(source)
    expected["bin/wi_fields.py"] = hashlib.sha256(source.encode()).hexdigest()
    output = tmp_path / "bundle"
    module.build_bundle(donor, output, expected)
    emitted = (output / "bin/wi_fields.py").read_text()
    assert set(module.module_exports(source)) - {
        "CALL_KINDS",
        "ACTION_RE",
        "ask_kind",
    } <= set(module.module_exports(emitted))
    code = """import wi_fields
from orchestra_dashboard import text
assert wi_fields.ask_kind is text.ask_kind
assert wi_fields.CALL_KINDS is text.CALL_KINDS
assert wi_fields.ACTION_RE is text.ACTION_RE
item = dict(id='synthetic-item', aliases=['synthetic-alias'], slugs=[],
            ask=[dict(id='', question='Il mockup è respinto. Quale pagina?', rec='')],
            pr=None, labels=[], gates={}, ui=False, status='Backlog')
wi_fields.enrich_asks(item, {}, [])
assert item['ask'][0]['kind'] == 'decide'
assert item['ask'][0]['answered'] is False
assert wi_fields.MOCKUP_RE.search('mockup')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=output / "bin",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_classifier_binding_drift_fails_before_output(tmp_path: Path, mutation: str):
    donor = tmp_path / "donor"
    expected = synthetic_donors(donor)
    path = donor / "bin/wi_fields.py"
    source = path.read_text()
    if mutation == "missing":
        source = source.replace("def ask_kind", "def other_kind")
    else:
        source += "\ndef ask_kind(a, it, decision): return 'second'\n"
    path.write_text(source)
    expected["bin/wi_fields.py"] = hashlib.sha256(source.encode()).hexdigest()
    output = tmp_path / "bundle"
    with pytest.raises(ValueError, match="missing or duplicate donor binding"):
        exporter().build_bundle(donor, output, expected)
    assert not output.exists()


def test_real_ask_caller_requires_hash_bound_classifier_donor(tmp_path: Path):
    donor = tmp_path / "donor"
    expected = synthetic_donors(donor)
    path = donor / "bin/workitems.py"
    source = path.read_text() + "\ndef asks(*args): pass\n"
    path.write_text(source)
    expected["bin/workitems.py"] = hashlib.sha256(source.encode()).hexdigest()
    expected.pop("bin/wi_fields.py")
    output = tmp_path / "bundle"
    with pytest.raises(ValueError, match="missing human-intent classifier donor"):
        exporter().build_bundle(donor, output, expected)
    assert not output.exists()


def test_default_cli_invocations_require_explicit_input(tmp_path: Path) -> None:
    for name in ("dashboard_producer_title.py", "export_dashboard_producer.py"):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / name)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2
    assert list(tmp_path.iterdir()) == []


def test_identity_candidate_is_separate_and_never_runtime_ready(tmp_path: Path) -> None:
    donor = tmp_path / "donor"
    expected = synthetic_donors(donor)
    module = exporter()
    core = module.build_bundle(donor, tmp_path / "core", expected)
    assert not {"bin/wi_identity.py"} & {row["path"] for row in core["files"]}
    assert "bin/wi_dedupe.py" in {row["path"] for row in core["files"]}
    assert core["deferred_targets"] == ["bin/wi_identity.py"]
    assert core["dedupe_intent_candidate"] == {
        "path": "bin/wi_dedupe.py",
        "symbols": ["merge_notes"],
        "canonical_helper": "curation.select_needs_intent",
        "runtime_accepted": False,
    }
    before = {path: (donor / path).read_bytes() for path in expected}
    candidate = module.build_bundle(
        donor, tmp_path / "candidate", expected, include_identity_candidate=True
    )
    assert {path: (donor / path).read_bytes() for path in expected} == before
    assert (
        "select_needs_intent(out, note)"
        in (tmp_path / "candidate/bin/wi_dedupe.py").read_text()
    )
    assert candidate["identity_candidate"] and candidate["runtime_ready"] is False
    assert {"bin/wi_identity.py", "bin/wi_dedupe.py"} <= {
        row["path"] for row in candidate["files"]
    }


def ruff_issues(path: Path) -> list[dict[str, Any]]:
    executable = shutil.which("ruff")
    if executable is None:
        pytest.skip("Ruff is unavailable in this test environment")
    result = subprocess.run(
        [executable, "check", "--isolated", "--output-format=json", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    return json.loads(result.stdout)


def assert_only_known_legacy_ruff(issues: list[dict[str, Any]]) -> None:
    unexpected = [
        row
        for row in issues
        if not (
            row["code"] == "E741"
            and Path(row["filename"]).name == "wi_common.py"
            and row["message"] == "Ambiguous variable name: `O`"
        )
    ]
    assert unexpected == []


def test_export_adds_no_ruff_errors_and_preserves_partial_module_api(
    tmp_path: Path,
) -> None:
    donor = tmp_path / "donor"
    expected = synthetic_donors(donor)
    assert_only_known_legacy_ruff(ruff_issues(donor / "bin"))
    output = tmp_path / "bundle"
    exporter().build_bundle(donor, output, expected)
    assert_only_known_legacy_ruff(ruff_issues(output / "bin"))
    code = """import wi_common, wi_notes, wi_status, wi_text, wi_fields
import orchestra_dashboard.common as common
import orchestra_dashboard.notes as notes
import orchestra_dashboard.text as text
assert wi_common.refs is common.refs
assert wi_common.short_repo is common.short_repo
assert wi_common.O == 0
assert wi_notes.notes_lock is notes.notes_lock
assert wi_status.STATUSES is common.STATUSES
assert wi_text.fill_text is text.fill_text
assert wi_fields.ask_kind is text.ask_kind
assert wi_fields.CALL_KINDS is text.CALL_KINDS
assert wi_fields.ACTION_RE is text.ACTION_RE
assert all(
    not hasattr(module, "__all__")
    for module in (wi_common, wi_notes, wi_status)
)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=output / "bin",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_applied_delta_uses_after_hash_and_preserves_retained_function_ast(
    tmp_path: Path,
) -> None:
    import ast

    module = exporter()
    donor = tmp_path / "donor"
    expected = synthetic_donors(donor)
    applied = tmp_path / "applied"
    output = tmp_path / "new"
    module.build_bundle(donor, applied, expected)
    module.build_bundle(donor, output, expected)
    path = applied / "bin/wi_text.py"
    path.write_text(path.read_text().replace("fill_text as fill_text", "fill_text"))
    manifest = json.loads((applied / "manifest.json").read_text())
    old_after = hashlib.sha256(path.read_bytes()).hexdigest()
    for row in manifest["files"]:
        if row["path"] == "bin/wi_text.py":
            row["after_sha256"] = old_after
    (applied / "manifest.json").write_text(json.dumps(manifest))
    report = module.build_applied_delta(applied, output)
    assert report["files"] == [
        {
            "path": "bin/wi_text.py",
            "before_sha256": old_after,
            "after_sha256": hashlib.sha256(
                (output / "bin/wi_text.py").read_bytes()
            ).hexdigest(),
        }
    ]
    assert report["files"][0]["before_sha256"] != expected["bin/wi_text.py"]
    expected_package = (
        "__init__.py",
        "common.py",
        "collector.py",
        "collector_caller.py",
        "collector_checkpoint.py",
        "repository.py",
        "curation.py",
        "history.py",
        "identity.py",
        "notes.py",
        "provenance.py",
        "ownership.py",
        "quality.py",
        "sources.py",
        "text.py",
        "titles.py",
        "shadow.py",
        "shadow_graph.py",
        "shadow_prior.py",
        "shadow_probe.py",
        "shadow_profile.py",
        "shadow_schema.py",
        "shadow_store.py",
        "shadow_profile_pins.json",
    )
    assert report["unchanged_package_paths"] == sorted(
        "bin/orchestra_dashboard/" + name for name in expected_package
    )
    assert report["package_changes"] == []
    assert report["apply_artifact"] == "delta.diff" and report["applied"] is False
    checked = subprocess.run(
        ["git", "apply", "--check", str(output / "delta.diff")],
        cwd=applied,
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr
    replacements = {
        "wi_common.py": {"refs", "short_repo"},
        "wi_notes.py": {"notes_lock"},
        "wi_status.py": set(),
        "workitems.py": {"curate", "finish", "publish", "_detail_item"},
    }
    for filename, replaced in replacements.items():
        before = {
            node.name: ast.dump(node)
            for node in ast.parse((donor / "bin" / filename).read_text()).body
            if isinstance(node, ast.FunctionDef) and node.name not in replaced
        }
        after = {
            node.name: ast.dump(node)
            for node in ast.parse((output / "bin" / filename).read_text()).body
            if isinstance(node, ast.FunctionDef) and node.name not in replaced
        }
        assert before == after


@pytest.mark.parametrize("kind", ["base_mismatch", "package_drift"])
def test_applied_delta_rejects_mismatches_before_writing(
    tmp_path: Path, kind: str
) -> None:
    module = exporter()
    donor = tmp_path / "donor"
    expected = synthetic_donors(donor)
    applied = tmp_path / "applied"
    output = tmp_path / "new"
    module.build_bundle(donor, applied, expected)
    module.build_bundle(donor, output, expected)
    target = applied if kind == "base_mismatch" else output
    path = target / "bin/orchestra_dashboard/quality.py"
    path.write_text(path.read_text() + "\n# synthetic changed package\n")
    if kind == "package_drift":
        manifest = json.loads((target / "manifest.json").read_text())
        for row in manifest["files"]:
            if row["path"] == "bin/orchestra_dashboard/quality.py":
                row["after_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        (target / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match=r"after-hash mismatch|package drift"):
        module.build_applied_delta(applied, output)
    assert not (output / "delta.diff").exists()
    assert not (output / "delta-manifest.json").exists()


def test_shadow_adapter_is_dormant_and_seals_after_successful_final_publish() -> None:
    import ast

    module = exporter()
    source = """def build(now=None):
    spawns = tk = ordinary_tasks = runs = ledger = led = None
    by_slug = decisions = triage = all_prs = revs = probes = None
    asm = None
    ctx = Context()
    ctx.notes = collapse(asm, ctx.notes, tk)
    return {"normal": True}

def publish(data, out=None):
    public = data
    snapshot_digest = "a" * 64
    write(public)
"""
    from test_dashboard_repository_projection import RAW_MAIN

    after = module.shadow_adapter(source + "\n" + RAW_MAIN)
    tree = ast.parse(after)
    build = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "build"
    )
    assert all(
        isinstance(value, ast.Constant) and value.value is None
        for value in build.args.kw_defaults
    )
    assert (
        len(
            [
                node
                for node in ast.walk(build)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "observe_boundary"
            ]
        )
        == 1
    )
    # The real caller does not import issue_ref; use the baseline's named globals.
    from types import SimpleNamespace

    callbacks = {name: object() for name in ("compute", "effective_note", "issue_ref")}
    normal_namespace = dict(callbacks)
    exec("def collapse(asm, notes, tasks): return notes", normal_namespace)
    captured = {}

    class Boundary:
        def observe_boundary(self, *args, **kwargs):
            captured.update(kwargs["callbacks"])
            return args[3]

    namespace = {
        "collapse": normal_namespace["collapse"],
        "canonical_collapse": object(),
        "Context": lambda: SimpleNamespace(notes={}),
    }
    exec(compile(ast.Module([build], type_ignores=[]), "synthetic", "exec"), namespace)
    assert namespace["build"](shadow=Boundary(), shadow_request=object()) == {
        "normal": True
    }
    assert all(captured[key] is value for key, value in callbacks.items())
    # Execute only this invented publisher; never import/build the donor producer.
    publish = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "publish"
    )
    events = []
    namespace = {"write": lambda public: events.append("write")}
    exec(
        compile(ast.Module([publish], type_ignores=[]), "synthetic", "exec"), namespace
    )

    class Observer:
        pending = object()

        def seal_after_publish(self, handle, generation, digest):
            events.append(("seal", generation, digest))

    data = {"generated": "synthetic-final-generation"}
    namespace["publish"](data)
    assert events == ["write"]
    events.clear()
    namespace["publish"](data, shadow=Observer())
    assert events == ["write", ("seal", data["generated"], "a" * 64)]

    def fail(*args):
        raise RuntimeError("synthetic publisher failure")

    namespace["write"] = fail
    events.clear()
    with pytest.raises(RuntimeError):
        namespace["publish"](data, shadow=Observer())
    assert events == []


def test_export_pin_table_is_exact_and_default_caller_remains_dormant(
    tmp_path: Path,
) -> None:
    donor = tmp_path / "donor"
    expected = synthetic_donors(donor)
    output = tmp_path / "bundle"
    exporter().build_bundle(donor, output, expected)
    relative = "bin/orchestra_dashboard/shadow_profile_pins.json"
    assert (output / relative).read_bytes() == (
        ROOT / "src/orchestra/dashboard/shadow_profile_pins.json"
    ).read_bytes()
    manifest = json.loads((output / "manifest.json").read_text())
    assert any(row["path"] == relative for row in manifest["files"])
    assert "observe_boundary" not in (output / "bin/workitems.py").read_text()
    assert manifest["runtime_ready"] is False


def test_package_inventory_is_closed_and_extra_json_is_not_read(
    tmp_path: Path, monkeypatch
) -> None:
    module = exporter()
    package = tmp_path / "package"
    shutil.copytree(
        ROOT / "src/orchestra/dashboard",
        package,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    monkeypatch.setattr(module, "PACKAGE", package)
    (package / "unrelated.json").write_text('{"auth":"PRIVATE_SENTINEL"}')
    donor = tmp_path / "donor"
    expected = synthetic_donors(donor)
    output = tmp_path / "bundle"
    module.build_bundle(donor, output, expected)
    assert not (output / "bin/orchestra_dashboard/unrelated.json").exists()
    (package / "unapproved.py").write_text("raise RuntimeError('must not execute')\n")
    with pytest.raises(ValueError, match="inventory drift"):
        module.build_bundle(donor, tmp_path / "rejected", expected)
    assert not (tmp_path / "rejected").exists()


def composition_inputs(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import export_repository_compat as compat

    donor = tmp_path / "donor"
    expected = synthetic_donors(donor)
    fixture = ROOT / "tests/fixtures/repository_compat"
    pinned = []
    for name in ("preview_recipes", "action_dedupe"):
        relative = f"bin/{name}.py"
        raw = (fixture / f"{name}.py").read_bytes()
        (donor / relative).write_bytes(raw)
        expected[relative] = hashlib.sha256(raw).hexdigest()
        pinned.append({"path": relative, "before_sha256": expected[relative]})
    pin = tmp_path / "fixture-compat-pins.json"
    pin.write_text(json.dumps({"runtime_targets": pinned}))
    monkeypatch.setattr(compat, "PIN_MANIFEST", pin)
    common = "bin/orchestra_dashboard/common.py"
    (donor / common).parent.mkdir()
    (donor / common).write_bytes(
        (ROOT / "src/orchestra/dashboard/common.py").read_bytes()
    )
    expected[common] = hashlib.sha256((donor / common).read_bytes()).hexdigest()
    return exporter(), compat, donor, expected


def test_composed_inventory_is_exact_24():
    assert set(exporter().PACKAGE_FILES) == {
        "__init__.py",
        "common.py",
        "collector.py",
        "collector_caller.py",
        "collector_checkpoint.py",
        "curation.py",
        "history.py",
        "identity.py",
        "notes.py",
        "ownership.py",
        "provenance.py",
        "quality.py",
        "repository.py",
        "sources.py",
        "text.py",
        "titles.py",
        "shadow.py",
        "shadow_graph.py",
        "shadow_prior.py",
        "shadow_probe.py",
        "shadow_profile.py",
        "shadow_schema.py",
        "shadow_store.py",
        "shadow_profile_pins.json",
    }
    assert len(exporter().PACKAGE_FILES) == 24


def test_composed_bundle_has_one_helper_same_before_vector_and_inert_donor(
    tmp_path, monkeypatch
):
    module, compat, donor, expected = composition_inputs(tmp_path, monkeypatch)
    existing = "bin/orchestra_dashboard/text.py"
    (donor / existing).write_text("def is_nothing(value): return False\n")
    expected[existing] = hashlib.sha256((donor / existing).read_bytes()).hexdigest()
    before = {path: (donor / path).read_bytes() for path in expected}
    proposals = compat.propose(
        *(before[f"bin/{name}.py"].decode() for name in compat.TARGETS)
    )
    isolated = tmp_path / "compat-isolated"
    compat_report = compat.build_bundle(donor, isolated)
    output = tmp_path / "combined"
    report = module.build_bundle(
        donor, output, expected, include_repository_compat=True
    )
    assert report["repository_compat"] and report["applied"] is False
    rows = {r["path"]: r for r in report["files"]}
    assert len(rows) == len(report["files"])
    helper = "bin/orchestra_dashboard/repository.py"
    assert rows[helper]["before_sha256"] is None
    assert rows[existing]["before_sha256"] == expected[existing]
    for row in compat_report["files"]:
        assert rows[row["path"]] == row
        assert (isolated / "after" / row["path"]).read_bytes() == (
            output / row["path"]
        ).read_bytes()
    for path, text in proposals.items():
        assert (output / path).read_text() == text
        assert rows[path]["before_sha256"] == expected.get(path)
    for path, raw in before.items():
        assert (donor / path).read_bytes() == raw
    assert (
        rows["bin/orchestra_dashboard/common.py"]["before_sha256"]
        == expected["bin/orchestra_dashboard/common.py"]
    )
    assert (output / helper).read_bytes() == (
        ROOT / "src/orchestra/dashboard/repository.py"
    ).read_bytes()
    result = subprocess.run(
        ["git", "apply", "--check", str(output / "patch.diff")],
        cwd=donor,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "mutation",
    [
        "existing_helper",
        "common_drift",
        "compat_drift",
        "duplicate_binding",
        "helper_conflict",
        "unbound_package",
    ],
)
def test_composed_bundle_rejects_before_any_output(tmp_path, monkeypatch, mutation):
    module, compat, donor, expected = composition_inputs(tmp_path, monkeypatch)
    if mutation == "existing_helper":
        (donor / "bin/orchestra_dashboard/repository.py").write_text(
            "# already present"
        )
    elif mutation == "common_drift":
        (donor / "bin/orchestra_dashboard/common.py").write_text("# authority drift")
    elif mutation in {"compat_drift", "duplicate_binding"}:
        relative = "bin/preview_recipes.py"
        with (donor / relative).open("a") as stream:
            stream.write(
                "\ndef normalize_item(item): return item\n"
                if mutation == "duplicate_binding"
                else "\nREPOS = {}\n"
            )
        expected[relative] = hashlib.sha256((donor / relative).read_bytes()).hexdigest()
    elif mutation == "helper_conflict":
        original = compat.propose

        def conflict(*args):
            return original(*args) | {
                "bin/orchestra_dashboard/repository.py": "# conflicting after"
            }

        monkeypatch.setattr(compat, "propose", conflict)
    else:
        (donor / "bin/orchestra_dashboard/text.py").write_text(
            "# unbound existing Source"
        )
    before = {
        p.relative_to(donor): p.read_bytes() for p in donor.rglob("*") if p.is_file()
    }
    output = tmp_path / "combined"
    with pytest.raises(ValueError):
        module.build_bundle(donor, output, expected, include_repository_compat=True)
    assert not output.exists()
    assert before == {
        p.relative_to(donor): p.read_bytes() for p in donor.rglob("*") if p.is_file()
    }


def test_composed_cli_uses_the_same_explicit_before_vector(
    tmp_path, monkeypatch, capsys
):
    module, _, donor, expected = composition_inputs(tmp_path, monkeypatch)
    metadata = tmp_path / "source-root/docs/provenance"
    metadata.mkdir(parents=True)
    (metadata / "dashboard-card-producer-20261027.json").write_text(
        json.dumps(
            {
                "donors": [
                    {"donor": path, "sha256": sha}
                    for path, sha in expected.items()
                    if path
                    not in {
                        "bin/preview_recipes.py",
                        "bin/action_dedupe.py",
                        "bin/orchestra_dashboard/common.py",
                    }
                ],
                "repository_composition": {
                    "expected_existing_source": {
                        path: expected[path]
                        for path in (
                            "bin/preview_recipes.py",
                            "bin/action_dedupe.py",
                            "bin/orchestra_dashboard/common.py",
                        )
                    }
                },
            }
        )
    )
    monkeypatch.setattr(module, "ROOT", tmp_path / "source-root")
    output = tmp_path / "cli-bundle"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export_dashboard_producer",
            "--donor-source",
            str(donor),
            "--output",
            str(output),
            "--include-repository-compat",
        ],
    )
    assert module.main() == 0
    assert json.loads(capsys.readouterr().out)["applied"] is False
    assert (
        json.loads((output / "manifest.json").read_text())["repository_compat"] is True
    )


def test_identity_candidate_and_unified_core_are_separate(tmp_path, monkeypatch):
    module, _, donor, expected = composition_inputs(tmp_path, monkeypatch)
    output = tmp_path / "mixed"
    with pytest.raises(ValueError, match="separate"):
        module.build_bundle(
            donor,
            output,
            expected,
            include_repository_compat=True,
            include_identity_candidate=True,
        )
    assert not output.exists()


def handoff_main():
    import ast

    from test_dashboard_repository_projection import RAW_MAIN

    source = """
def build():
    ctx.notes = collapse(asm, ctx.notes, tk)
    return data

def publish(data, out=None):
    public = data
    snapshot_digest = "a" * 64
    write(public)
"""
    module = exporter()
    changed = module.shadow_adapter(source + "\n" + RAW_MAIN)
    main = module._function(changed, "main")
    return ast.Module([main], type_ignores=[])


@pytest.mark.parametrize(
    "mode", ["off", "false", "true", "check", "enabled", "publish_failure"]
)
def test_programmatic_main_handoff_preserves_normal_cycle_and_capability(
    tmp_path, mode
):
    from types import SimpleNamespace

    from dashboard_shadow_fixture import boundary
    from test_dashboard_shadow import prior_input

    from orchestra.dashboard.quality import audit, board_digest
    from orchestra.dashboard.shadow import ShadowObserver, ShadowRequest
    from orchestra.dashboard.shadow_prior import (
        PriorWitness,
        project_prior_publications,
    )
    from orchestra.dashboard.shadow_store import CommitResult, CommitState, read_receipt

    fixture = boundary()
    evidence, verified_witness, now = prior_input()
    prior = project_prior_publications(
        {
            "generated": evidence.generated,
            "items": [
                {
                    "id": "synthetic",
                    "repo": "atrium",
                    "slugs": list(fixture["tasks"]),
                    "pr": None,
                }
            ],
        },
        {"generated": evidence.generated, "items": []},
        artifacts=evidence.artifacts,
        board_digest=evidence.board_digest,
        coverage="live_and_terminal",
    )
    # The synthetic ROOT witness is deliberately separate from the pure projector.
    witness = PriorWitness(prior, verified_witness.sha256, verified_witness.verified_at)
    fixture["ctx"].now = now.timestamp()
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    request = ShadowRequest("6" * 32, directory, 7200)
    events, observers, created = [], [], []

    def new_observer():
        created.append(1)
        return ShadowObserver()

    def build(**kwargs):
        events.append("build")
        if kwargs:
            assert mode in {"enabled", "publish_failure"}
            assert kwargs["shadow_request"] is request
            assert (
                kwargs["shadow_prior"] is prior and kwargs["shadow_witness"] is witness
            )
            assert kwargs["shadow_profile"] is None
            shadow = kwargs["shadow"]
            observers.append(shadow)
            result = shadow.observe_boundary(
                fixture["baseline"],
                fixture["candidate"],
                fixture["asm"],
                fixture["notes"],
                fixture["tasks"],
                shared_roots={"ctx": fixture["ctx"], "locals": fixture["locals"]},
                callbacks=fixture["callbacks"],
                prior=prior,
                witness=witness,
                profile=None,
                request=request,
            )
            assert result["synthetic"]["steps_checked"]["check"] is True
            assert shadow.pending.equivalent, shadow.pending.differences
        else:
            fixture["baseline"](fixture["asm"], fixture["notes"], fixture["tasks"])
        return {
            "generated": "2026-10-27T13:00:00.000001Z",
            "items": [{"id": "synthetic", "ask": [], "auto": []}],
        }

    failure = RuntimeError("synthetic ordinary publish failure")

    def publish(data, **kwargs):
        events.append("publish")
        if mode == "publish_failure":
            raise failure
        if kwargs:
            assert kwargs["shadow"] is observers[0]
            shadow = kwargs["shadow"]
            shadow.seal_after_publish(
                shadow.pending, data["generated"], board_digest(data)
            )

    namespace = {
        "ShadowObserver": new_observer,
        "ShadowRequest": ShadowRequest,
        "CommitResult": CommitResult,
        "CommitState": CommitState,
        "build": build,
        "publish": publish,
        "quality_audit": audit,
        "sys": SimpleNamespace(
            argv=["workitems"] + (["--check"] if mode == "check" else [])
        ),
        "validate": lambda data: [],
        "duplicate_gaps": lambda data: [],
        "uncurated_open": lambda data: [],
        "step_gaps": lambda data: [],
        "NO_REC": "none",
    }
    exec(compile(handoff_main(), "synthetic-source-main.py", "exec"), namespace)
    args = (
        {}
        if mode == "off"
        else {
            "shadow_request": False
            if mode == "false"
            else True
            if mode == "true"
            else request,
            "shadow_prior": prior,
            "shadow_witness": witness,
        }
    )
    if mode == "publish_failure":
        with pytest.raises(RuntimeError) as caught:
            namespace["main"](**args)
        assert caught.value is failure and observers[0].commit_result is None
    elif mode == "check":
        with pytest.raises(SystemExit) as caught:
            namespace["main"](**args)
        assert caught.value.code == 0 and not request._consumed and observers == []
    else:
        result = namespace["main"](**args)
        if mode == "enabled":
            assert (
                result is observers[0].commit_result
                and result.state is CommitState.COMMITTED
            )
            assert read_receipt(directory, result.receipt)["verdict"] == "PASS"
        elif mode == "off":
            assert result is None and not request._consumed and observers == []
        else:
            assert (
                result.state is CommitState.NOT_COMMITTED
                and observers == []
                and not request._consumed
            )
    assert events == (["build"] if mode == "check" else ["build", "publish"])
    assert created == ([1] if mode in {"enabled", "publish_failure"} else [])
