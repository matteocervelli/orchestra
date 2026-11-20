#!/usr/bin/env python3
"""Prepare the R1 history delta from pinned static copies; never apply or run it."""

from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from export_dashboard_producer import _imports_after_future, replace_symbols

ROOT = Path(__file__).resolve().parents[1]
PINS = ROOT / "docs/provenance/dashboard-history-publisher-r1-20261104.json"
HELPER = "bin/orchestra_dashboard/history_index.py"
HISTORY_IMPORT = (
    "from orchestra_dashboard.history_index import "
    "history_terminal, prepare_history_index\n"
)


def _function(source: str, name: str) -> ast.FunctionDef:
    nodes = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if len(nodes) != 1:
        raise ValueError("history_donor_function")
    return nodes[0]


def function_hash(source: str, name: str) -> str:
    return hashlib.sha256(
        ast.dump(_function(source, name), include_attributes=False).encode()
    ).hexdigest()


def _replace(publish: ast.FunctionDef, before: str, after: str) -> None:
    expected = ast.dump(ast.parse(before).body[0])
    matches = [i for i, node in enumerate(publish.body) if ast.dump(node) == expected]
    if len(matches) != 1:
        raise ValueError("history_publication_boundary")
    index = matches[0]
    publish.body[index : index + 1] = ast.parse(after).body


def adapt_workitems(source: str) -> str:
    """Change only the pinned ordinary publish body and its canonical import."""
    if sys.version_info[:2] != (3, 12):
        raise ValueError("history_export_requires_python312")
    pins = json.loads(PINS.read_text())
    if function_hash(source, "publish") != pins["publish_ast_sha256"]:
        raise ValueError("history_publish_shape")
    if "orchestra_dashboard.history_index" in source:
        raise ValueError("history_already_adapted")
    publish = _function(source, "publish")
    _replace(
        publish,
        "live = [item for item in items "
        "if item.get('status') not in TERMINAL_STATUSES]",
        "live = [item for item in items if not history_terminal(item)]",
    )
    _replace(
        publish,
        "terminal = [item for item in items "
        "if item.get('status') in TERMINAL_STATUSES]",
        "terminal = [item for item in items if history_terminal(item)]",
    )
    _replace(publish, "detail_dir.mkdir(parents=True, exist_ok=True)", "")
    loops = [node for node in publish.body if isinstance(node, ast.For)]
    if len(loops) != 1:
        raise ValueError("history_detail_boundary")
    _replace(
        publish,
        ast.unparse(loops[0]),
        "details = [_detail_item(item, ledger, board=public, "
        "snapshot_digest=snapshot_digest) for item in items]\n"
        "history_index = prepare_history_index(public, terminal, details, ledger, "
        "_public_item)\n"
        "detail_dir.mkdir(parents=True, exist_ok=True)\n"
        "for detail in details:\n"
        "    _write_compact(detail, detail_dir / (detail['id'] + '.json'))",
    )
    _replace(
        publish,
        "_write_compact(public, out)",
        "_write_compact(history_index, "
        "out.with_name('work-items-history-index.json'))\n"
        "_write_compact(public, out)",
    )
    changed = replace_symbols(
        source, {"publish": ast.unparse(ast.fix_missing_locations(publish))}
    )
    return _imports_after_future(changed, HISTORY_IMPORT)


def _read(donor: Path, relative: str) -> bytes:
    path = donor
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("history_symlink_donor")
    if not path.is_file():
        raise ValueError("history_missing_donor")
    return path.read_bytes()


def _originals(donor: Path, pins: dict[str, Any]) -> dict[str, bytes]:
    expected = pins["runtime_targets"]
    if set(expected) != {"bin/workitems.py", "bin/orchestra_dashboard/quality.py"}:
        raise ValueError("history_before_vector")
    originals = {path: _read(donor, path) for path in expected}
    if any(
        hashlib.sha256(raw).hexdigest() != expected[path]
        for path, raw in originals.items()
    ):
        raise ValueError("history_donor_hash")
    helper = donor / HELPER
    if helper.exists() or helper.is_symlink():
        raise ValueError("history_existing_helper")
    quality = originals["bin/orchestra_dashboard/quality.py"].decode("utf-8")
    canonical = (ROOT / "src/orchestra/dashboard/quality.py").read_text()
    for name, digest in pins["quality_function_ast_sha256"].items():
        if (
            function_hash(quality, name) != digest
            or function_hash(canonical, name) != digest
        ):
            raise ValueError("history_quality_dependency")
    return originals


def build_bundle(donor: Path, output: Path) -> dict[str, Any]:
    """Export a new review artifact; the donor and its dependencies stay unchanged."""
    if sys.version_info[:2] != (3, 12):
        raise ValueError("history_export_requires_python312")
    donor = donor.resolve()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(donor):
        raise ValueError("history_output_must_be_new_and_outside_donor")
    pins = json.loads(PINS.read_text())
    originals = _originals(donor, pins)
    generated = {
        "bin/workitems.py": adapt_workitems(originals["bin/workitems.py"].decode()),
        HELPER: (ROOT / "src/orchestra/dashboard/history_index.py").read_text(),
    }
    rows, patch = [], []
    for path, text in generated.items():
        compile(text, path, "exec")
        before = originals.get(path)
        rows.append(
            {
                "path": path,
                "before_sha256": hashlib.sha256(before).hexdigest() if before else None,
                "after_sha256": hashlib.sha256(text.encode()).hexdigest(),
            }
        )
        patch.extend(
            difflib.unified_diff(
                before.decode().splitlines(keepends=True) if before else [],
                text.splitlines(keepends=True),
                fromfile="a/" + path if before else "/dev/null",
                tofile="b/" + path,
            )
        )
    report = {
        "schema": "orchestra-dashboard-history-patch/v1",
        "interface_sha256": pins["interface_sha256"],
        "before_vector": pins["runtime_targets"],
        "files": rows,
        "applied": False,
        "runtime_ready": False,
    }
    output.mkdir(parents=True)
    for relative, text in generated.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "patch.diff").write_text("".join(patch))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--donor", type=Path, required=True, help="isolated static SOURCE donor copy"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_bundle(args.donor, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
