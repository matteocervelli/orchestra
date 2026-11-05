"""Exercise the pinned ordinary publisher with synthetic data, never build()."""

import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from orchestra.dashboard.history_index import history_terminal, prepare_history_index
from orchestra.dashboard.quality import (
    audit,
    bind_detail,
    board_digest,
    publication_generated,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/dashboard_history/workitems_selected.py.txt"


def exporter():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        spec = importlib.util.spec_from_file_location(
            "history_export_test", ROOT / "scripts/export_dashboard_history.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def publisher(writer=None):
    source = exporter().adapt_workitems(FIXTURE.read_text())
    tree = ast.parse(source)
    # Only the explicit selected static publisher and its pure helpers execute.
    tree.body = [
        node
        for node in tree.body
        if not isinstance(node, ast.ImportFrom)
        or node.module == "__future__"
        or node.module == "pathlib"
    ]
    namespace = {
        "read_json": lambda path, default: default,
        "publication_generated": publication_generated,
        "board_digest": board_digest,
        "bind_detail": bind_detail,
        "history_terminal": history_terminal,
        "prepare_history_index": prepare_history_index,
        "quality_audit": lambda data: {"generated": data["generated"], "items": []},
    }
    exec(compile(tree, "selected-static-publisher", "exec"), namespace)
    if writer is not None:
        namespace["_write_compact"] = writer
    return namespace["publish"], namespace


def data():
    return {
        "generated": "old",
        "statuses": ["Doing", "Deployed", "Dropped"],
        "ledger": [{"slug": "child", "note": f"result {i}"} for i in range(12)],
        "items": [
            {"id": "active", "status": "Doing", "your_call": False},
            {
                "id": "closed",
                "status": "dEpLoYeD",
                "your_call": False,
                "title": "Concluso",
                "priority_src": "",
                "agent": {},
                "call_kind": None,
                "ask": [],
                "steps": [],
                "hidden": False,
                "slugs": ["child"],
                "history": list(range(45)),
            },
        ],
    }


def test_ordinary_publisher_order_digest_raw_and_rich_details(tmp_path):
    writes = []

    def writer(value, path):
        writes.append((path.name, value))

    publish, _ = publisher(writer)
    publish(data(), tmp_path / "board" / "work-items.json")
    assert [name for name, _ in writes] == [
        "active.json",
        "closed.json",
        "work-items-archive.json",
        "work-items-quality.json",
        "work-items-history-index.json",
        "work-items.json",
    ]
    values = dict(writes)
    board = values["work-items.json"]
    index = values["work-items-history-index.json"]
    assert [row["id"] for row in board["items"]] == ["active"]
    assert [row["id"] for row in index["items"]] == ["closed"]
    assert len(index["items"][0]["history"]) == 5
    assert len(values["closed.json"]["history"]) == 45
    assert len(values["closed.json"]["ledger"]) == 12
    assert len(values["work-items-archive.json"]["items"][0]["history"]) == 45
    assert index["items"][0]["your_call"] is False
    assert index["items"][0]["priority_src"] == ""
    assert index["items"][0]["agent"] == {}
    assert index["items"][0]["call_kind"] is None
    assert index["items"][0]["hidden"] is False
    assert index["generated"] == board["generated"]
    assert index["board_sha256"] == board_digest(board)
    for row in (values["active.json"], values["closed.json"]):
        assert row["_producer_snapshot"]["generated"] == index["generated"]
        assert row["_producer_snapshot"]["board_sha256"] == index["board_sha256"]


@pytest.mark.parametrize(
    "mutation",
    [
        "unsafe",
        "duplicate_active",
        "duplicate_terminal",
        "overlap",
        "missing_call",
        "null_call",
        "oversize_detail",
        "oversize_index",
        "statuses",
        "generation",
        "nan",
    ],
)
def test_rejection_preserves_prior_files_and_does_not_create_directories(
    tmp_path, mutation
):
    publish, namespace = publisher()
    value = data()
    if mutation == "unsafe":
        value["items"][1]["id"] = "../escape"
    elif mutation == "duplicate_active":
        value["items"].append(dict(value["items"][0]))
    elif mutation == "duplicate_terminal":
        value["items"].append(dict(value["items"][1]))
    elif mutation == "overlap":
        value["items"][1]["id"] = "active"
    elif mutation == "missing_call":
        value["items"][1].pop("your_call")
    elif mutation == "null_call":
        value["items"][1]["your_call"] = None
    elif mutation == "oversize_detail":
        value["items"][1]["evidence"] = "x" * (10 * 1024 * 1024)
    elif mutation == "oversize_index":
        value["items"] = [
            {
                "id": f"closed-{i}",
                "status": "Dropped",
                "your_call": False,
                "title": "x" * (6 * 1024 * 1024),
            }
            for i in range(2)
        ]
    elif mutation == "statuses":
        value["statuses"] = [False]
    elif mutation == "generation":
        namespace["publication_generated"] = lambda previous: "bad"
    elif mutation == "nan":
        value["items"][1]["cost"] = float("nan")
    out = tmp_path / "existing" / "work-items.json"
    out.parent.mkdir()
    out.write_bytes(b"prior bytes")
    with pytest.raises(ValueError):
        publish(value, out)
    assert list(out.parent.iterdir()) == [out]
    assert out.read_bytes() == b"prior bytes"
    with pytest.raises(ValueError):
        publish(value, tmp_path / "absent" / "work-items.json")
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize("position", [0, 1], ids=["active", "terminal"])
@pytest.mark.parametrize("variant", ["list", "integer", "null", "missing"])
def test_real_quality_audit_invalid_status_rejected_before_any_write(
    tmp_path, position, variant
):
    publish, namespace = publisher()
    namespace["quality_audit"] = audit
    value = data()
    if variant == "missing":
        value["items"][position].pop("status")
    else:
        value["items"][position]["status"] = {
            "list": ["Deployed"],
            "integer": 5,
            "null": None,
        }[variant]
    out = tmp_path / "existing" / "work-items.json"
    prior = {
        "work-items.json": b"prior board",
        "work-items-archive.json": b"prior archive",
        "work-items-quality.json": b"prior quality",
        "work-items-history-index.json": b"prior index",
        "work-items-detail/active.json": b"prior active detail",
        "work-items-detail/closed.json": b"prior terminal detail",
    }
    for name, raw in prior.items():
        path = out.parent / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    with pytest.raises(ValueError, match="status"):
        publish(value, out)
    assert {
        str(path.relative_to(out.parent)): path.read_bytes()
        for path in out.parent.rglob("*")
        if path.is_file()
    } == prior
    with pytest.raises(ValueError, match="status"):
        publish(value, tmp_path / "absent" / "work-items.json")
    assert not (tmp_path / "absent").exists()


def test_actual_atomic_writer_keeps_existing_detail_and_outputs_consistent_json(
    tmp_path,
):
    publish, _ = publisher()
    old = tmp_path / "work-items-detail" / "older.json"
    old.parent.mkdir()
    old.write_text("preserve")
    publish(data(), tmp_path / "work-items.json")
    assert old.read_text() == "preserve"
    assert not list(tmp_path.rglob("*.tmp"))
    board = json.loads((tmp_path / "work-items.json").read_bytes())
    index = json.loads((tmp_path / "work-items-history-index.json").read_bytes())
    assert index["board_sha256"] == board_digest(board)


@pytest.mark.parametrize(
    "failed_artifact", ["work-items-quality.json", "work-items-history-index.json"]
)
def test_write_failure_never_reaches_active_board(tmp_path, failed_artifact):
    publish, namespace = publisher()
    original_writer = namespace["_write_compact"]
    reached = []

    def failing_writer(value, path):
        reached.append(path.name)
        if path.name == failed_artifact:
            raise OSError("synthetic failure")
        original_writer(value, path)

    namespace["_write_compact"] = failing_writer
    out = tmp_path / "work-items.json"
    out.write_bytes(b"previous board")
    with pytest.raises(OSError, match="synthetic failure"):
        publish(data(), out)
    assert out.name not in reached
    assert out.read_bytes() == b"previous board"
    assert (tmp_path / "work-items-detail/closed.json").exists()
    assert (tmp_path / "work-items-archive.json").exists()


def test_static_fixture_provenance_and_supported_export_interpreter(monkeypatch):
    module = exporter()
    pins = json.loads((FIXTURE.parent / "manifest.json").read_text())
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == pins["fixture_sha256"]
    monkeypatch.setattr(module.sys, "version_info", (3, 15))
    with pytest.raises(ValueError, match="python312"):
        module.adapt_workitems(FIXTURE.read_text())
    with pytest.raises(ValueError, match="python312"):
        module.build_bundle(Path("unused-donor"), Path("unused-output"))


def test_adapter_changes_only_publish_and_one_import():
    module = exporter()
    before = FIXTURE.read_text()
    after = module.adapt_workitems(before)
    placeholder = {"publish": "def publish(): pass"}
    from export_dashboard_producer import replace_symbols

    assert replace_symbols(
        after.replace(module.HISTORY_IMPORT, ""), placeholder
    ) == replace_symbols(before, placeholder)
    with pytest.raises(ValueError):
        module.adapt_workitems(after)
    with pytest.raises(ValueError):
        module.adapt_workitems(
            before.replace(
                "snapshot_digest = board_digest(public)", "snapshot_digest = 'wrong'"
            )
        )


def synthetic_donor(tmp_path, monkeypatch):
    module = exporter()
    donor = tmp_path / "donor"
    caller = donor / "bin/workitems.py"
    caller.parent.mkdir(parents=True)
    caller.write_text(FIXTURE.read_text())
    quality = donor / "bin/orchestra_dashboard/quality.py"
    quality.parent.mkdir()
    quality.write_bytes((ROOT / "src/orchestra/dashboard/quality.py").read_bytes())
    pins = json.loads(module.PINS.read_text())
    pins["runtime_targets"] = {
        str(path.relative_to(donor)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (caller, quality)
    }
    pins["publish_ast_sha256"] = module.function_hash(caller.read_text(), "publish")
    synthetic_pins = tmp_path / "synthetic-pins.json"
    synthetic_pins.write_text(json.dumps(pins))
    monkeypatch.setattr(module, "PINS", synthetic_pins)
    return module, donor, pins


def test_bundle_is_inert_minimal_hash_bound_and_canonical(tmp_path, monkeypatch):
    module, donor, pins = synthetic_donor(tmp_path, monkeypatch)
    before = {path: (donor / path).read_bytes() for path in pins["runtime_targets"]}
    output = tmp_path / "bundle"
    report = module.build_bundle(donor, output)
    assert report["applied"] is False and report["runtime_ready"] is False
    assert {row["path"] for row in report["files"]} == {
        "bin/workitems.py",
        "bin/orchestra_dashboard/history_index.py",
    }
    assert (output / "bin/orchestra_dashboard/history_index.py").read_bytes() == (
        ROOT / "src/orchestra/dashboard/history_index.py"
    ).read_bytes()
    assert (output / "bin/workitems.py").read_text() == module.adapt_workitems(
        FIXTURE.read_text()
    )
    for row in report["files"]:
        assert row["before_sha256"] == (
            hashlib.sha256(before[row["path"]]).hexdigest()
            if row["path"] in before
            else None
        )
        assert (
            row["after_sha256"]
            == hashlib.sha256((output / row["path"]).read_bytes()).hexdigest()
        )
    assert json.loads((output / "manifest.json").read_text()) == report
    patch_check = subprocess.run(
        ["git", "apply", "--check", str(output / "patch.diff")],
        cwd=donor,
        capture_output=True,
        text=True,
        check=False,
    )
    assert patch_check.returncode == 0, patch_check.stderr
    assert all((donor / path).read_bytes() == raw for path, raw in before.items())
    assert (output / "patch.diff").is_file()
    assert report["interface_sha256"] == pins["interface_sha256"]


@pytest.mark.parametrize(
    "mutation", ["caller", "quality", "helper", "output", "inside", "symlink"]
)
def test_export_drift_fails_before_bundle_output(tmp_path, monkeypatch, mutation):
    module, donor, _ = synthetic_donor(tmp_path, monkeypatch)
    output = tmp_path / "bundle"
    if mutation == "caller":
        (donor / "bin/workitems.py").write_text("unreviewed")
    elif mutation == "quality":
        (donor / "bin/orchestra_dashboard/quality.py").write_text("unreviewed")
    elif mutation == "helper":
        (donor / "bin/orchestra_dashboard/history_index.py").write_text("existing")
    elif mutation == "output":
        output.mkdir()
    elif mutation == "inside":
        output = donor / "bundle"
    elif mutation == "symlink":
        original = donor / "bin/workitems.py"
        copy = tmp_path / "caller-copy"
        original.rename(copy)
        original.symlink_to(copy)
    with pytest.raises(ValueError):
        module.build_bundle(donor, output)
    assert not output.exists() or mutation == "output"
