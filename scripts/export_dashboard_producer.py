#!/usr/bin/env python3
"""Build a reviewed-source patch bundle; never apply or activate it."""

from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src/orchestra/dashboard"


def bindings(node: ast.stmt) -> list[str]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.Assign):
        return [target.id for target in node.targets if isinstance(target, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return [name.asname or name.name for name in node.names]
    return []


def replace_symbols(text: str, replacements: dict[str, str]) -> str:
    lines = text.splitlines(keepends=True)
    spans = []
    counts = {name: 0 for name in replacements}
    for node in ast.parse(text).body:
        selected = set(bindings(node)) & replacements.keys()
        if selected:
            if len(selected) != 1 or node.end_lineno is None:
                raise ValueError("ambiguous donor binding")
            name = next(iter(selected))
            counts[name] += 1
            first = min(
                [node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])]
            )
            spans.append((first - 1, node.end_lineno, replacements[name] + "\n"))
    if any(count != 1 for count in counts.values()):
        raise ValueError("missing or duplicate donor binding")
    for start, end, replacement in reversed(spans):
        lines[start:end] = [replacement]
    result = "".join(lines)
    top = [name for node in ast.parse(result).body for name in bindings(node)]
    if any(top.count(name) != 1 for name in replacements):
        raise ValueError("duplicate exported binding")
    return result


def module_exports(source: str) -> list[str]:
    return [
        name
        for node in ast.parse(source).body
        if not isinstance(node, (ast.Import, ast.ImportFrom))
        for name in bindings(node)
    ]


def _function(source: str, name: str) -> ast.FunctionDef:
    nodes = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if len(nodes) != 1:
        raise ValueError("ambiguous caller function")
    return nodes[0]


def _workitems(source: str) -> str:
    finish = _function(source, "finish")
    inserted = False
    for index, node in enumerate(finish.body):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "curate"
        ):
            finish.body[index:index] = ast.parse(
                'it["work_provenance"] = resolve_work_provenance(note'
                ', [ctx.tasks[s] for s in it.get("slugs", []) if s in'
                " ctx.tasks], card)"
            ).body
            inserted = True
            break
    if not inserted:
        raise ValueError("missing provenance insertion boundary")
    publish = _function(source, "publish")
    inserted = False
    detail_calls = 0
    for index, node in enumerate(publish.body):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "out" for t in node.targets
        ):
            publish.body[index + 1 : index + 1] = ast.parse(
                'data = {**data, "generated": publication_generated(r'
                'ead_json(out, {}).get("generated"))}'
            ).body
            inserted = True
            break
    for node in ast.walk(publish):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_detail_item"
        ):
            node.keywords.append(
                ast.keyword(arg="board", value=ast.Name(id="public", ctx=ast.Load()))
            )
            node.keywords.append(
                ast.keyword(
                    arg="snapshot_digest",
                    value=ast.Name(id="snapshot_digest", ctx=ast.Load()),
                )
            )
            detail_calls += 1
    for index, node in enumerate(publish.body):
        if (
            isinstance(node, ast.For)
            and isinstance(node.target, ast.Name)
            and node.target.id == "item"
        ):
            publish.body[index:index] = ast.parse(
                "snapshot_digest = board_digest(public)"
            ).body
            break
    else:
        raise ValueError("missing detail publication loop")
    if not inserted or detail_calls != 1:
        raise ValueError("missing publication boundary")
    changed = replace_symbols(
        source,
        {
            "TEXT_KEYS": (
                "from orchestra_dashboard.curation import TEXT_KEYS as TEXT_KEYS"
            ),
            "curate": "from orchestra_dashboard.curation import curate as curate",
            "finish": ast.unparse(ast.fix_missing_locations(finish)),
            "publish": ast.unparse(ast.fix_missing_locations(publish)),
            "_detail_item": (
                "def _detail_item(item, ledger, *, board, snapshot_di"
                'gest):\n    return bind_detail({**item, "ledger": _le'
                "dger_for(item, ledger)}, board, snapshot_digest=snap"
                "shot_digest)"
            ),
        },
    )
    return _imports_after_future(
        changed,
        (
            "from orchestra_dashboard.provenance import resolve_w"
            "ork_provenance\nfrom orchestra_dashboard.quality impo"
            "rt bind_detail, board_digest, publication_generated\n"
        ),
    )


def _imports_after_future(source: str, imports: str) -> str:
    lines = source.splitlines(keepends=True)
    future = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.ImportFrom) and node.module == "__future__"
    ]
    tree = ast.parse(source)
    doc = (
        tree.body[0]
        if tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
        else None
    )
    position = future[-1].end_lineno if future else doc.end_lineno if doc else 0
    lines.insert(position or 0, imports)
    return "".join(lines)


def _clean_adapter_imports(source: str, unused_candidates: set[str]) -> str:
    """Move canonical imports and remove only extracted, now-unused dependencies."""
    used = {
        node.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    lines = source.splitlines(keepends=True)
    hoisted = []
    edits = []
    for node in ast.parse(source).body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "orchestra_dashboard"
        ):
            hoisted.append(ast.unparse(node) + "\n")
            edits.append((node.lineno - 1, node.end_lineno, ""))
        else:
            kept = [
                alias
                for alias in node.names
                if (alias.asname or alias.name) not in unused_candidates
                or (alias.asname or alias.name) in used
            ]
            if len(kept) != len(node.names):
                node.names = kept
                edits.append(
                    (
                        node.lineno - 1,
                        node.end_lineno,
                        ast.unparse(node) + "\n" if kept else "",
                    )
                )
    for start, end, replacement in reversed(edits):
        lines[start:end] = [replacement]
    return _imports_after_future("".join(lines), "".join(hoisted))


def adapters(
    donors: dict[str, str], *, include_identity_candidate: bool = False
) -> dict[str, str]:
    result = {
        path: text
        for path, text in donors.items()
        if include_identity_candidate
        or path not in {"bin/wi_identity.py", "bin/wi_dedupe.py"}
    }
    modules = [("wi_text", "text")] + (
        [("wi_identity", "identity")] if include_identity_candidate else []
    )
    for filename, module in modules:
        names = module_exports(donors[f"bin/{filename}.py"])
        result[f"bin/{filename}.py"] = (
            ('"""Generated compatibility exports; edit canonical source only."""\n')
            + f"from orchestra_dashboard.{module} import ("
            + ", ".join(f"{name} as {name}" for name in names)
            + ")\n"
        )
    source = donors["bin/wi_quality.py"]
    urls = [
        node.value
        for node in ast.walk(_function(source, "audit"))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("https://")
        and node.value.endswith("?item=")
    ]
    if len(urls) != 1:
        raise ValueError("missing quality URL context")
    url = repr(urls[0])
    names = [name for name in module_exports(source) if name not in ("main", "audit")]
    exported = ", ".join(f"{name} as {name}" for name in names)
    result["bin/wi_quality.py"] = (
        "from pathlib import Path\n"
        f"from orchestra_dashboard.quality import ({exported})\n"
        "from orchestra_dashboard.quality import audit as _audit, main as _main\n"
        f"\ndef audit(data):\n    return _audit(data, board_url={url})\n"
        "\ndef main():\n    return _main(default_path="
        'Path(__file__).resolve().parents[1] / "pages/data/work-items.json", '
        f"board_url={url})\n"
        '\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
    )
    if not names:
        result["bin/wi_quality.py"] = result["bin/wi_quality.py"].replace(
            "from orchestra_dashboard.quality import ()\n", ""
        )
    result["bin/wi_sources.py"] = replace_symbols(
        donors["bin/wi_sources.py"],
        {
            "tasks": (
                "def tasks():\n    from orchestra_dashboard.sources im"
                "port tasks as canonical_tasks\n    return canonical_t"
                "asks(C.O)"
            )
        },
    )
    result["bin/wi_notes.py"] = replace_symbols(
        donors["bin/wi_notes.py"],
        {
            "notes_lock": (
                "from orchestra_dashboard.notes import notes_lock as notes_lock"
            )
        },
    )
    symbols = {
        "wi_common": ["REPOS", "FULL", "REF_RE", "short_repo", "refs"],
        "wi_status": ["STATUSES", "CLOSED"],
    }
    for filename, names in symbols.items():
        result[f"bin/{filename}.py"] = replace_symbols(
            donors[f"bin/{filename}.py"],
            {
                name: f"from orchestra_dashboard.common import {name} as {name}"
                for name in names
            },
        )
    if include_identity_candidate:
        result["bin/wi_dedupe.py"] = replace_symbols(
            donors["bin/wi_dedupe.py"],
            {
                "unique": "from orchestra_dashboard.curation import unique as unique",
                "collapse": (
                    "def collapse(asm, notes, tasks):\n    from orchestra_"
                    "dashboard.curation import collapse as canonical_coll"
                    "apse\n    return canonical_collapse(asm, notes, tasks"
                    ", compute=compute, effective_note=effective_note, is"
                    "sue_ref=issue_ref)"
                ),
            },
        )
    result["bin/workitems.py"] = _workitems(donors["bin/workitems.py"])
    result["bin/dashboard-producer-title.py"] = (
        "from orchestra_dashboard.notes import main\n\nif __nam"
        'e__ == "__main__":\n    raise SystemExit(main())\n'
    )
    unused = {
        "bin/wi_common.py": {"re"},
        "bin/wi_notes.py": {"fcntl", "contextmanager", "Iterator"},
    }
    return {
        path: _clean_adapter_imports(text, unused.get(path, set()))
        for path, text in result.items()
    }


def build_bundle(
    donor: Path,
    output: Path,
    expected: dict[str, str],
    *,
    include_identity_candidate: bool = False,
) -> dict[str, Any]:
    if output.exists() or output.resolve().is_relative_to(donor.resolve()):
        raise ValueError("output must be new and outside donor root")
    originals = {}
    for relative, digest in expected.items():
        if (
            not relative.startswith("bin/")
            or len(Path(relative).parts) != 2
            or not relative.endswith(".py")
        ):
            raise ValueError("invalid donor path")
        data = (donor / relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"donor hash mismatch: {relative}")
        originals[relative] = data.decode("utf-8")
    generated = adapters(
        originals, include_identity_candidate=include_identity_candidate
    )
    for path in PACKAGE.glob("*.py"):
        generated["bin/orchestra_dashboard/" + path.name] = path.read_text()
    patch = []
    rows = []
    for relative, text in sorted(generated.items()):
        compile(text, relative, "exec")
        before = originals.get(relative, "")
        patch.extend(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                text.splitlines(keepends=True),
                fromfile="a/" + relative,
                tofile="b/" + relative,
            )
        )
        rows.append(
            {
                "path": relative,
                "before_sha256": hashlib.sha256(before.encode()).hexdigest()
                if relative in originals
                else None,
                "after_sha256": hashlib.sha256(text.encode()).hexdigest(),
            }
        )
    output.mkdir(parents=True)
    for relative, text in generated.items():
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    report = {
        "schema": "orchestra-dashboard-patch/v1",
        "files": rows,
        "applied": False,
        "identity_candidate": include_identity_candidate,
        "runtime_ready": False,
        "deferred_targets": []
        if include_identity_candidate
        else ["bin/wi_identity.py", "bin/wi_dedupe.py"],
    }
    (output / "patch.diff").write_text("".join(patch))
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def _bundle_snapshot(root: Path) -> dict[str, bytes]:
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("identity_candidate"):
        raise ValueError("adapter delta requires core bundles")
    snapshot = {}
    for row in manifest["files"]:
        relative = row["path"]
        if (
            not relative.startswith("bin/")
            or ".." in Path(relative).parts
            or not relative.endswith(".py")
        ):
            raise ValueError("invalid bundle path")
        data = (root / relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != row["after_sha256"]:
            raise ValueError(f"bundle after-hash mismatch: {relative}")
        if relative in snapshot:
            raise ValueError("duplicate bundle path")
        snapshot[relative] = data
    return snapshot


def build_applied_delta(applied: Path, output: Path) -> dict[str, Any]:
    """Emit only the delta from a verified already-applied core AFTER snapshot."""
    if (output / "delta.diff").exists() or (output / "delta-manifest.json").exists():
        raise ValueError("delta output already exists")
    before, after = _bundle_snapshot(applied), _bundle_snapshot(output)
    if before.keys() != after.keys():
        raise ValueError("core target inventory changed")
    changed = sorted(path for path in before if before[path] != after[path])
    package_changes = [
        path for path in changed if path.startswith("bin/orchestra_dashboard/")
    ]
    if set(package_changes) - {"bin/orchestra_dashboard/sources.py"}:
        raise ValueError("canonical package drift outside authorized reader")
    patch, rows = [], []
    for relative in changed:
        patch.extend(
            difflib.unified_diff(
                before[relative].decode().splitlines(keepends=True),
                after[relative].decode().splitlines(keepends=True),
                fromfile="a/" + relative,
                tofile="b/" + relative,
            )
        )
        rows.append(
            {
                "path": relative,
                "before_sha256": hashlib.sha256(before[relative]).hexdigest(),
                "after_sha256": hashlib.sha256(after[relative]).hexdigest(),
            }
        )
    report = {
        "schema": "orchestra-dashboard-applied-delta/v1",
        "base_patch_sha256": hashlib.sha256(
            (applied / "patch.diff").read_bytes()
        ).hexdigest(),
        "base_manifest_sha256": hashlib.sha256(
            (applied / "manifest.json").read_bytes()
        ).hexdigest(),
        "files": rows,
        "unchanged_package_paths": sorted(
            path
            for path in before
            if path.startswith("bin/orchestra_dashboard/")
            and path not in package_changes
        ),
        "package_changes": package_changes,
        "apply_artifact": "delta.diff",
        "applied": False,
        "runtime_ready": False,
    }
    (output / "delta.diff").write_text("".join(patch))
    (output / "delta-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-identity-candidate", action="store_true")
    parser.add_argument("--against-applied-bundle", type=Path)
    args = parser.parse_args()
    provenance = json.loads(
        (ROOT / "docs/provenance/dashboard-card-producer-20261027.json").read_text()
    )
    expected = {row["donor"]: row["sha256"] for row in provenance["donors"]}
    report = build_bundle(
        args.donor_source,
        args.output,
        expected,
        include_identity_candidate=args.include_identity_candidate,
    )
    if args.against_applied_bundle:
        build_applied_delta(args.against_applied_bundle, args.output)
    print(
        json.dumps(
            {
                "files": len(report["files"]),
                "applied": False,
                "apply_artifact": "delta.diff" if args.against_applied_bundle else None,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
