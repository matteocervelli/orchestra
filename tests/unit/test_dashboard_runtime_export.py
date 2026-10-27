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
            "def unique(rows): return rows\ndef collapse(asm, note"
            "s, tasks): return {}\n"
        ),
        "workitems": (
            "from pathlib import Path\nTEXT_KEYS = ()\ndef curate(i"
            't, note, card): return set(), ""\ndef finish(it, iid,'
            " ctx):\n    note = {}\n    card = {}\n    curated, prev"
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
            text += "    return public, out\n"
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
    assert not {"bin/wi_identity.py", "bin/wi_dedupe.py"} & {
        row["path"] for row in core["files"]
    }
    candidate = module.build_bundle(
        donor, tmp_path / "candidate", expected, include_identity_candidate=True
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
    code = """import wi_common, wi_notes, wi_status, wi_text
import orchestra_dashboard.common as common
import orchestra_dashboard.notes as notes
import orchestra_dashboard.text as text
assert wi_common.refs is common.refs
assert wi_common.short_repo is common.short_repo
assert wi_common.O == 0
assert wi_notes.notes_lock is notes.notes_lock
assert wi_status.STATUSES is common.STATUSES
assert wi_text.fill_text is text.fill_text
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
    assert len(report["unchanged_package_paths"]) == 10
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
