#!/usr/bin/env python3
"""Prepare a narrow hash-bound SOURCE description patch; never apply or import it."""

from __future__ import annotations

import argparse
import ast
import copy
import difflib
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from export_dashboard_producer import _imports_after_future

ROOT = Path(__file__).resolve().parents[1]
PINS = ROOT / "docs/provenance/dashboard-semantic-content-20261104.json"
HELPER = "bin/orchestra_dashboard/descriptions.py"


def _node(source: str, name: str) -> ast.FunctionDef | ast.ClassDef:
    nodes = [
        n
        for n in ast.parse(source).body
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name
    ]
    if len(nodes) != 1:
        raise ValueError("semantic_missing_symbol")
    return nodes[0]


def _hash_node(node: ast.AST) -> str:
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def _check(source: str, names: dict[str, str]) -> None:
    if any(_hash_node(_node(source, name)) != digest for name, digest in names.items()):
        raise ValueError("semantic_symbol_shape")


def _offset(source: str, line: int, column: int) -> int:
    lines = source.split("\n")
    lines = [line + "\n" for line in lines[:-1]] + lines[-1:]
    # AST columns count UTF-8 bytes, not Unicode characters.
    return sum(len(s) for s in lines[: line - 1]) + len(
        lines[line - 1].encode()[:column].decode()
    )


def _splice(source: str, node: ast.AST, replacement: str) -> str:
    if node.end_lineno is None or node.end_col_offset is None:
        raise ValueError("semantic_missing_span")
    start = _offset(source, node.lineno, node.col_offset)
    end = _offset(source, node.end_lineno, node.end_col_offset)
    return source[:start] + replacement + source[end:]


def _call(node: ast.AST, name: str) -> ast.Call:
    calls = [
        n
        for n in ast.walk(node)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == name
    ]
    if len(calls) != 1:
        raise ValueError("semantic_caller_boundary")
    return calls[0]


def _acquisition(build: ast.FunctionDef | ast.ClassDef) -> tuple[ast.Assign, ast.List]:
    matches = [
        n
        for n in build.body
        if isinstance(n, ast.Assign)
        and len(n.targets) == 1
        and ast.unparse(n.targets[0]) == "all_prs"
    ]
    if len(matches) != 1:
        raise ValueError("semantic_acquisition_boundary")
    assignment = matches[0]
    comprehensions = [n for n in ast.walk(assignment) if isinstance(n, ast.DictComp)]
    if len(comprehensions) != 1 or len(comprehensions[0].generators) != 1:
        raise ValueError("semantic_acquisition_boundary")
    generator = comprehensions[0].generators[0]
    acquired = generator.iter
    if not isinstance(acquired, ast.List):
        raise ValueError("semantic_acquisition_boundary")
    generator.iter = ast.Name(id="acquired_prs", ctx=ast.Load())
    return assignment, acquired


def _without_symbols(
    source: str, names: set[str], *, descriptions_import: bool = False
) -> str:
    lines = source.split("\n")
    spans = []
    for node in ast.parse(source).body:
        selected = (
            isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names
        )
        imported = (
            descriptions_import
            and isinstance(node, ast.ImportFrom)
            and node.module == "descriptions"
        )
        if selected or imported:
            first = min(
                [node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])]
            )
            spans.append((first - 1, node.end_lineno))
    for start, end in reversed(spans):
        lines[start:end] = []
    return "\n".join(lines)


def _verify_workitems(before: str, after: str, expected: ast.Module) -> None:
    if ast.dump(ast.parse(after)) != ast.dump(ast.fix_missing_locations(expected)):
        raise ValueError("semantic_caller_output_ast")
    names = {"Ctx", "build", "finish"}
    if _without_symbols(before, names) != _without_symbols(after, names):
        raise ValueError("semantic_caller_output_bytes")


def adapt_workitems(source: str) -> str:
    """Retain raw acquired descriptions while preserving assembly deduplication."""
    pins = json.loads(PINS.read_text())
    _check(source, pins["caller_ast_sha256"])
    original = source
    expected = ast.parse(source)
    nodes = {
        n.name: n
        for n in expected.body
        if isinstance(n, (ast.ClassDef, ast.FunctionDef))
    }
    ctx, build, finish = (nodes[name] for name in ("Ctx", "build", "finish"))
    call, context = _call(finish, "fill_text"), _call(build, "Ctx")
    if call.keywords or context.args:
        raise ValueError("semantic_caller_boundary")
    call.keywords.append(
        ast.keyword(
            arg="source_prs", value=ast.parse("ctx.source_prs", mode="eval").body
        )
    )
    source = _splice(source, call, ast.unparse(call))
    context.keywords.append(
        ast.keyword(arg="source_prs", value=ast.Name(id="acquired_prs", ctx=ast.Load()))
    )
    position = _offset(source, context.end_lineno, 0)
    source = (
        source[:position] + "        source_prs=acquired_prs,\n" + source[position:]
    )
    assignment, acquired = _acquisition(build)
    retained = ast.Assign(
        targets=[ast.Name(id="acquired_prs", ctx=ast.Store())],
        value=copy.deepcopy(acquired),
    )
    replacement = (
        ast.unparse(ast.fix_missing_locations(retained))
        + "\n    "
        + ast.unparse(assignment)
    )
    source = _splice(source, assignment, replacement)
    build.body.insert(build.body.index(assignment), retained)
    position = _offset(source, ctx.end_lineno + 1, 0)
    field_source = "source_prs: list[dict] = field(default_factory=list)"
    source = source[:position] + "    " + field_source + "\n" + source[position:]
    ctx.body.append(ast.parse(field_source).body[0])
    _verify_workitems(original, source, expected)
    return source


def adapt_status(source: str) -> str:
    """Validate the reviewed dependency without changing lifecycle/settle source."""
    pins = json.loads(PINS.read_text())
    _check(source, pins["status_ast_sha256"])
    return source


def adapt_quality(source: str) -> str:
    pins = json.loads(PINS.read_text())
    _check(source, pins["dependency_ast_sha256"]["quality.py"])
    node = _node(source, "findings")
    returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
    if len(returns) != 1 or ast.unparse(returns[0]) != "return rows":
        raise ValueError("semantic_quality_boundary")
    bound = [
        n
        for n in node.body[: node.body.index(returns[0])]
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "severity" for t in n.targets)
    ]
    if len(bound) != 1:
        raise ValueError("semantic_quality_severity_binding")
    position = _offset(source, returns[0].lineno, 0)
    addition = (
        "    rows.extend(\n"
        "        {'code': code, 'severity': severity, 'message': message}\n"
        "        for code, message in description_findings(item)\n"
        "    )\n"
    )
    changed = _imports_after_future(
        source[:position] + addition + source[position:],
        "from .descriptions import description_findings\n",
    )
    expected = copy.deepcopy(node)
    expected.body.insert(
        expected.body.index(
            next(n for n in expected.body if isinstance(n, ast.Return))
        ),
        ast.parse(addition.lstrip()).body[0],
    )
    if _hash_node(_node(changed, "findings")) != _hash_node(expected):
        raise ValueError("semantic_quality_output_ast")
    if _without_symbols(source, {"findings"}) != _without_symbols(
        changed, {"findings"}, descriptions_import=True
    ):
        raise ValueError("semantic_quality_output_bytes")
    return changed


def _read(donor: Path, relative: str) -> bytes:
    path = donor
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("semantic_symlink_donor")
    if not path.is_file():
        raise ValueError("semantic_missing_donor")
    return path.read_bytes()


def _originals(donor: Path, pins: dict[str, Any], variant: str) -> dict[str, bytes]:
    expected = pins["before_vectors"].get(variant)
    if not isinstance(expected, dict) or set(expected) != set(
        pins["before_vectors"]["current"]
    ) | (
        {"bin/orchestra_dashboard/history_index.py"}
        if variant == "planned_r1"
        else set()
    ):
        raise ValueError("semantic_before_vector")
    if any(
        expected.get(row["source"]) != row["source_sha256"]
        for row in pins["acquisition_evidence"]
    ):
        raise ValueError("semantic_acquisition_vector")
    originals = {relative: _read(donor, relative) for relative in expected}
    if any(
        hashlib.sha256(raw).hexdigest() != expected[path]
        for path, raw in originals.items()
    ):
        raise ValueError("semantic_donor_hash")
    if (donor / HELPER).exists() or (donor / HELPER).is_symlink():
        raise ValueError("semantic_existing_helper")
    for filename, names in pins["dependency_ast_sha256"].items():
        _check(originals["bin/orchestra_dashboard/" + filename].decode(), names)
    for filename, names in pins["canonical_dependency_ast_sha256"].items():
        _check((ROOT / "src/orchestra/dashboard" / filename).read_text(), names)
    # Refactored canonical qualification and the reviewed monolithic runtime
    # implementation have separately pinned bodies and identical call contracts.
    current = _node(
        originals["bin/orchestra_dashboard/provenance.py"].decode(), "qualified_pr"
    )
    canonical = _node(
        (ROOT / "src/orchestra/dashboard/provenance.py").read_text(), "qualified_pr"
    )
    if (
        not isinstance(current, ast.FunctionDef)
        or not isinstance(canonical, ast.FunctionDef)
        or ast.dump(current.args) != ast.dump(canonical.args)
    ):
        raise ValueError("semantic_qualification_contract")
    return originals


def _check_acquisition(pins: dict[str, Any]) -> None:
    fixture = ROOT / "tests/fixtures/dashboard_semantic/acquisition.py.txt"
    raw = fixture.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pins["acquisition_fixture_sha256"]:
        raise ValueError("semantic_acquisition_fixture")
    _check(raw.decode(), pins["acquisition_ast_sha256"])


def build_bundle(donor: Path, output: Path, variant: str = "current") -> dict[str, Any]:
    """Validate a reviewed copied donor before emitting an inert new bundle."""
    if sys.version_info[:2] != (3, 12):
        raise ValueError("semantic_export_requires_python312")
    donor = donor.resolve()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(donor):
        raise ValueError("semantic_output_must_be_new_and_outside_donor")
    pins = json.loads(PINS.read_text())
    _check_acquisition(pins)
    originals = _originals(donor, pins, variant)
    adapt_status(originals["bin/wi_status.py"].decode())
    generated = {
        "bin/workitems.py": adapt_workitems(originals["bin/workitems.py"].decode()),
        "bin/orchestra_dashboard/quality.py": adapt_quality(
            originals["bin/orchestra_dashboard/quality.py"].decode()
        ),
        "bin/orchestra_dashboard/text.py": (
            ROOT / "src/orchestra/dashboard/text.py"
        ).read_text(),
        HELPER: (ROOT / "src/orchestra/dashboard/descriptions.py").read_text(),
    }
    rows, patch = [], []
    for path, source in generated.items():
        compile(source, path, "exec")
        before = originals.get(path)
        rows.append(
            {
                "path": path,
                "before_sha256": hashlib.sha256(before).hexdigest() if before else None,
                "after_sha256": hashlib.sha256(source.encode()).hexdigest(),
            }
        )
        patch.extend(
            difflib.unified_diff(
                before.decode().splitlines(keepends=True) if before else [],
                source.splitlines(keepends=True),
                fromfile="a/" + path if before else "/dev/null",
                tofile="b/" + path,
            )
        )
    report = {
        "schema": "orchestra-dashboard-semantic-patch/v1",
        "variant": variant,
        "before_vector": pins["before_vectors"][variant],
        "files": rows,
        "applied": False,
        "runtime_ready": False,
    }
    output.mkdir(parents=True)
    for relative, source in generated.items():
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "patch.diff").write_text("".join(patch))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--variant", choices=("current", "planned_r1"), default="current"
    )
    args = parser.parse_args()
    print(json.dumps(build_bundle(args.donor, args.output, args.variant), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
