#!/usr/bin/env python3
"""Prepare a bounded repository compatibility delta; never apply or run it."""

from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
from typing import Any

from export_dashboard_producer import replace_symbols

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src/orchestra/dashboard"
PIN_MANIFEST = (
    ROOT / "docs/provenance/dashboard-repository-runtime-compat-20261027.json"
)
TARGETS = {
    "preview_recipes": {"normalize_item"},
    "action_dedupe": {"scope_of", "find_active"},
}


def function(source: str, name: str) -> ast.FunctionDef:
    found = [
        n
        for n in ast.parse(source).body
        if isinstance(n, ast.FunctionDef) and n.name == name
    ]
    if len(found) != 1:
        raise ValueError("ambiguous_donor_function")
    return found[0]


def outside_functions(source: str, names: set[str]) -> str:
    return replace_symbols(source, {name: f"def {name}(): pass" for name in names})


def scope_function(source: str) -> str:
    node = function(source, "scope_of")
    matches = [
        i
        for i, statement in enumerate(node.body)
        if isinstance(statement, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "repo" for t in statement.targets)
    ]
    expected = ast.parse('repo = info.get("repo") or ""').body[0]
    if len(matches) != 1 or ast.dump(node.body[matches[0]]) != ast.dump(expected):
        raise ValueError("unexpected_repo_assignment")
    node.body[matches[0] + 1 : matches[0] + 1] = ast.parse(
        "if isinstance(repo, str):\n    repo = repository_key(repo)"
    ).body
    node.body[:0] = ast.parse(
        "from orchestra_dashboard.repository import repository_key"
    ).body
    return ast.unparse(node)


def matching_function(source: str) -> str:
    node = function(source, "find_active")
    index = int(
        bool(
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        )
    )
    node.body[index:index] = ast.parse(
        "from orchestra_dashboard.repository import normalize_action_scope\n"
        "scope = normalize_action_scope(step, scope)"
    ).body
    return ast.unparse(node)


def propose(preview: str, actions: str) -> dict[str, str]:
    normalizer = (
        "def normalize_item(item: dict | None) -> dict | None:\n"
        '    """Resolve only configured recipes using the shared repository key."""\n'
        "    from orchestra_dashboard.repository import preview_item\n"
        "    return preview_item(item, REPOS)"
    )
    replacements = {
        "preview_recipes": {"normalize_item": normalizer},
        "action_dedupe": {
            "scope_of": scope_function(actions),
            "find_active": matching_function(actions),
        },
    }
    result = {}
    for name, before in (("preview_recipes", preview), ("action_dedupe", actions)):
        after = replace_symbols(before, replacements[name])
        if outside_functions(before, TARGETS[name]) != outside_functions(
            after, TARGETS[name]
        ):
            raise ValueError("unrelated_donor_bytes_changed")
        result[f"bin/{name}.py"] = after
    result["bin/orchestra_dashboard/repository.py"] = (
        PACKAGE / "repository.py"
    ).read_text()
    return result


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate_donors(before: dict[str, bytes]) -> None:
    targets = json.loads(PIN_MANIFEST.read_text())["runtime_targets"]
    expected = {
        row["path"]: row["before_sha256"]
        for row in targets
        if row.get("before_sha256") is not None
    }
    if set(expected) != set(before) or any(
        digest(raw) != expected[path] for path, raw in before.items()
    ):
        raise ValueError("runtime_donor_drift")


def delta_file(
    path: str, original: bytes | None, text: str
) -> tuple[dict[str, Any], str]:
    record = {
        "path": path,
        "before_sha256": digest(original) if original is not None else None,
        "after_sha256": digest(text.encode()),
    }
    patch = "".join(
        difflib.unified_diff(
            original.decode().splitlines(True) if original is not None else [],
            text.splitlines(True),
            fromfile="a/" + path if original is not None else "/dev/null",
            tofile="b/" + path,
        )
    )
    return record, patch


def build_bundle(runtime: Path, output: Path) -> dict[str, Any]:
    helper = "bin/orchestra_dashboard/repository.py"
    dependency = "bin/orchestra_dashboard/common.py"
    if output.exists() or (runtime / helper).exists():
        raise ValueError("existing_output_or_helper")
    common = (PACKAGE / "common.py").read_bytes()
    if (runtime / dependency).read_bytes() != common:
        raise ValueError("authority_dependency_drift")
    before = {
        f"bin/{name}.py": (runtime / "bin" / f"{name}.py").read_bytes()
        for name in TARGETS
    }
    validate_donors(before)
    proposed = propose(*(before[f"bin/{name}.py"].decode() for name in TARGETS))
    report: dict[str, Any] = {
        "schema": "orchestra-repository-compat-delta/v1",
        "applied": False,
        "dependency": dependency,
        "dependency_sha256": digest(common),
        "pin_manifest_sha256": digest(PIN_MANIFEST.read_bytes()),
        "files": [],
        "source_sha256": {
            str(p.relative_to(ROOT)): digest(p.read_bytes())
            for p in (
                PACKAGE / "repository.py",
                Path(__file__),
                ROOT / "scripts/export_dashboard_producer.py",
            )
        },
    }
    patch = []
    for path, text in proposed.items():
        record, diff = delta_file(path, before.get(path), text)
        report["files"].append(record)
        patch.append(diff)
    output.mkdir(parents=True)
    for path, text in proposed.items():
        target = output / "after" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    (output / "delta.patch").write_text("".join(patch))
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build_bundle(args.donor, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
