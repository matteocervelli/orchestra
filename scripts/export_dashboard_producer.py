#!/usr/bin/env python3
"""Build a reviewed-source patch bundle; never apply or activate it."""

from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src/orchestra/dashboard"

PACKAGE_FILES = (
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
    "ownership.py",
    "provenance.py",
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


def _project_publication(publish: ast.FunctionDef) -> None:
    expected = ast.parse(
        "items = [item for item in data.get('items', []) if isinstance(item, dict)]"
    ).body[0]
    matches = [
        i for i, node in enumerate(publish.body) if ast.dump(node) == ast.dump(expected)
    ]
    if len(matches) != 1:
        raise ValueError("missing terminal repository boundary")
    index = matches[0]
    publish.body[index : index + 1] = ast.parse(
        "raw_items = [item for item in data.get('items', []) "
        "if isinstance(item, dict)]\n"
        "raw_live = [item for item in raw_items "
        "if item.get('status') not in TERMINAL_STATUSES]\n"
        "items = [dict(item, repo=repository_key(item['repo'])) if 'repo' in item "
        "else dict(item) for item in raw_items]"
    ).body
    _raw_publication_audit(publish)


def _raw_publication_audit(publish: ast.FunctionDef) -> None:
    calls = [
        node
        for node in ast.walk(publish)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "quality_audit"
    ]
    if len(calls) != 1:
        raise ValueError("missing raw audit boundary")
    call = calls[0]
    expected_arg = ast.parse("{**data, 'items': live}", mode="eval").body
    if len(call.args) != 1 or ast.dump(call.args[0]) != ast.dump(expected_arg):
        raise ValueError("unexpected raw audit input")
    call.args[0] = ast.parse("{**data, 'items': raw_live}", mode="eval").body


def _ownership_finish(finish: ast.FunctionDef) -> None:
    expected = ast.parse(
        "it['repos'] = wi_repos.derive(it, card, note, ctx.tasks, ctx.spawns, rows)\n"
        "if not (it.get('pr') or it.get('issue')):\n"
        "    it['repo'] = it['repos'][0]\n"
        "repo = REPOS.get(it['repo'], it['repo'])"
    ).body
    dumps = [ast.dump(node) for node in finish.body]
    indices = [
        index
        for index in range(len(dumps) - 2)
        if dumps[index : index + 3] == [ast.dump(node) for node in expected]
    ]
    fallback = ast.dump(ast.parse("it['repo'] = it['repo'] or 'orchestra'").body[0])
    late = [index for index, node in enumerate(dumps) if node == fallback]
    indexed = ast.dump(ast.parse("it['repos'][0]", mode="eval").body)
    reads = sum(ast.dump(node) == indexed for node in ast.walk(finish))
    if (
        len(indices) != 1
        or len(late) != 1
        or reads != 1
        or any(dumps.count(ast.dump(node)) != 1 for node in expected)
        or late[0] <= indices[0] + 2
    ):
        raise ValueError("missing or ambiguous ownership boundary")
    guard = expected[1]
    if not isinstance(guard, ast.If):
        raise ValueError("invalid ownership boundary")
    guard.body = ast.parse("it['repo'] = it['repos'][0] if it['repos'] else ''").body
    finish.body[indices[0] + 1] = guard
    del finish.body[late[0]]


def _workitems(source: str, *, include_project_ownership: bool = False) -> str:
    finish = _function(source, "finish")
    _quality_text_finish(finish)
    if include_project_ownership:
        _ownership_finish(finish)
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
    _project_publication(publish)
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
            "from orchestra_dashboard.repository import repository_key\n"
            "from orchestra_dashboard.provenance import resolve_w"
            "ork_provenance\nfrom orchestra_dashboard.quality impo"
            "rt bind_detail, board_digest, publication_generated\n"
        ),
    )


def _quality_text_finish(finish: ast.FunctionDef) -> None:
    """Pass existing merged intent to canonical text; no asking policy here."""
    fills = [
        node
        for node in finish.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "fill_text"
    ]
    notes = [
        node
        for node in finish.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "ask_note"
            for target in node.targets
        )
    ]
    if not fills and not notes:
        return  # Supported minimal synthetic donor has no text/ask boundary.
    if len(fills) != 1 or len(notes) != 1:
        raise ValueError("ambiguous text/asking boundary")
    finish.body.remove(notes[0])
    index = finish.body.index(fills[0])
    finish.body[index : index + 1] = [
        notes[0],
        *ast.parse(
            "res['asking'] = fill_text(it, curated, res['asking'], ask_note, "
            "note.get('status') in ASKING_OLD, "
            "[ctx.tasks[s] for s in it.get('slugs', []) if s in ctx.tasks])"
        ).body,
    ]


def _shadow_main(source: str) -> str:
    main = _function(source, "main")
    names = ("shadow_request", "shadow_prior", "shadow_witness")
    existing = {arg.arg for arg in (*main.args.args, *main.args.kwonlyargs)}
    if existing.intersection(names):
        raise ValueError("shadow main already present")
    main.args.kwonlyargs.extend(ast.arg(arg=name) for name in names)
    main.args.kw_defaults.extend(ast.Constant(None) for _ in names)
    _main_handoff_calls(main)
    main.body[:0] = ast.parse(
        "shadow = None\n"
        "if '--check' not in sys.argv and type(shadow_request) is ShadowRequest:\n"
        "    shadow = ShadowObserver()"
    ).body
    main.body.extend(
        ast.parse(
            "if shadow_request is not None:\n"
            "    return (shadow.commit_result if shadow is not None and "
            "shadow.commit_result is not None "
            "else CommitResult(CommitState.NOT_COMMITTED))"
        ).body
    )
    main.returns = ast.parse("CommitResult | None", mode="eval").body
    return ast.unparse(ast.fix_missing_locations(main))


def _main_handoff_calls(main: ast.FunctionDef) -> None:
    expected_build = ast.dump(ast.parse("data = build()").body[0])
    expected_publish = ast.dump(ast.parse("publish(data)").body[0])
    builds = [node for node in main.body if ast.dump(node) == expected_build]
    publishes = [node for node in main.body if ast.dump(node) == expected_publish]
    if len(builds) != 1 or len(publishes) != 1:
        raise ValueError("missing normal main handoff")
    build, publish = builds[0], publishes[0]
    if not isinstance(build, ast.Assign) or not isinstance(publish, ast.Expr):
        raise ValueError("invalid main handoff")
    build.value = ast.parse(
        "build(shadow=shadow,shadow_request=shadow_request,shadow_prior=shadow_prior,"
        "shadow_witness=shadow_witness,shadow_profile=None) "
        "if shadow is not None else build()",
        mode="eval",
    ).body
    publish.value = ast.parse(
        "publish(data,shadow=shadow) if shadow is not None else publish(data)",
        mode="eval",
    ).body


def shadow_adapter(source: str) -> str:
    """Review-only dormant hook on an explicitly supplied already-core caller."""
    build, publish = _function(source, "build"), _function(source, "publish")
    added = (
        "shadow",
        "shadow_request",
        "shadow_prior",
        "shadow_witness",
        "shadow_profile",
    )
    existing = {arg.arg for arg in (*build.args.args, *build.args.kwonlyargs)}
    if existing.intersection(added):
        raise ValueError("shadow hook already present")
    build.args.kwonlyargs.extend(ast.arg(arg=name) for name in added)
    build.args.kw_defaults.extend(ast.Constant(None) for _ in added)
    matches = [
        (index, node)
        for index, node in enumerate(build.body)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "collapse"
        and len(node.targets) == 1
        and ast.unparse(node.targets[0]) == "ctx.notes"
    ]
    if len(matches) != 1:
        raise ValueError("missing shadow boundary")
    index, normal = matches[0]
    names = (
        "spawns",
        "tk",
        "ordinary_tasks",
        "runs",
        "ledger",
        "led",
        "by_slug",
        "decisions",
        "triage",
        "all_prs",
        "revs",
        "probes",
    )
    local_source = ", ".join(repr(name) + ": " + name for name in names)
    injected = ast.parse(
        "if shadow is not None and shadow_request is not None:\n"
        "    ctx.notes = shadow.observe_boundary(collapse, canonical_collapse, "
        "asm, ctx.notes, tk, "
        "shared_roots={'ctx':ctx,'locals':{" + local_source + "}}, "
        "callbacks={'compute':collapse.__globals__['compute'],"
        "'effective_note':collapse.__globals__['effective_note'],"
        "'issue_ref':collapse.__globals__['issue_ref']}, "
        "prior=shadow_prior,witness=shadow_witness,profile=shadow_profile,request=shadow_request)\n"
        "else:\n    pass\n"
    ).body[0]
    if not isinstance(injected, ast.If):
        raise ValueError("invalid shadow hook")
    injected.orelse = [normal]
    build.body[index] = injected
    if any(
        arg.arg == "shadow" for arg in (*publish.args.args, *publish.args.kwonlyargs)
    ):
        raise ValueError("shadow publisher already present")
    publish.args.kwonlyargs.append(ast.arg(arg="shadow"))
    publish.args.kw_defaults.append(ast.Constant(None))
    seal = ast.parse(
        "if shadow is not None and shadow.pending is not None:\n"
        "    shadow.seal_after_publish(shadow.pending,public['generated'],"
        "snapshot_digest)\n"
    ).body
    position = len(publish.body) - int(isinstance(publish.body[-1], ast.Return))
    publish.body[position:position] = seal
    changed = replace_symbols(
        source,
        {
            "build": ast.unparse(ast.fix_missing_locations(build)),
            "publish": ast.unparse(ast.fix_missing_locations(publish)),
            "main": _shadow_main(source),
        },
    )
    return _imports_after_future(
        changed,
        "from orchestra_dashboard.shadow import ShadowObserver, ShadowRequest\n"
        "from orchestra_dashboard.shadow_store import CommitResult, CommitState\n"
        "from orchestra_dashboard.curation import collapse as canonical_collapse\n",
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


# Reviewed AST includes the function name, signature, ordering and merge guards.
# Changes require explicit donor review; runtime/identity activation is separate.
MERGE_NOTES_AST_SHA256 = (
    "14addbab8955dfb1f63bb14d0f8a435ca84482766190685fe484c376bcc63b59"
)


class MissingDedupeDonorError(ValueError):
    """A candidate donor must be explicitly bound before generating output."""


class DedupeInventoryTransitionError(ValueError):
    """Old core inventories cannot authorize an extra protected runtime target."""


def dedupe_intent_adapter(source: str) -> str:
    """Pair metadata at the existing scalar winner boundary, changing no identity."""
    if sys.version_info[:2] != (3, 12):
        raise ValueError("dedupe intent adapter requires Python 3.12 for reviewed AST")
    tree = ast.parse(source)
    bound = [name for node in tree.body for name in bindings(node)]
    if bound.count("merge_notes") != 1 or "select_needs_intent" in bound:
        raise ValueError("ambiguous merge_notes intent binding")
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "merge_notes"
    ]
    if len(nodes) != 1:
        raise ValueError("missing merge_notes donor function")
    merge = nodes[0]
    digest = hashlib.sha256(
        ast.dump(merge, include_attributes=False).encode()
    ).hexdigest()
    if digest != MERGE_NOTES_AST_SHA256:
        raise ValueError("unreviewed merge_notes donor shape or signature")
    # Exact reviewed shape above makes these positions unambiguous.
    aliases = next(
        node
        for node in merge.body
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name)
        and node.target.id == "alias"
    )
    scalar = next(
        node
        for node in aliases.body
        if isinstance(node, ast.For) and isinstance(node.target, ast.Tuple)
    )
    guard = scalar.body[0]
    if not isinstance(guard, ast.If) or not isinstance(guard.test, ast.BoolOp):
        raise ValueError("invalid merge_notes scalar guard")
    comparison = guard.test.values[1]
    if not isinstance(comparison, ast.Compare):
        raise ValueError("invalid merge_notes scalar comparison")
    excluded = comparison.comparators[0]
    if not isinstance(excluded, ast.Tuple):
        raise ValueError("invalid merge_notes scalar exclusions")
    excluded.elts.append(ast.Constant("needs_intent"))
    index = aliases.body.index(scalar)
    aliases.body[index + 1 : index + 1] = ast.parse(
        "if not superseded and 'needs' in note:\n    select_needs_intent(out, note)"
    ).body
    changed = replace_symbols(
        source, {"merge_notes": ast.unparse(ast.fix_missing_locations(merge))}
    )
    return _imports_after_future(
        changed, "from orchestra_dashboard.curation import select_needs_intent\n"
    )


def adapters(
    donors: dict[str, str],
    *,
    include_identity_candidate: bool = False,
    include_project_ownership: bool = False,
) -> dict[str, str]:
    if (
        any(
            isinstance(node, ast.FunctionDef) and node.name == "asks"
            for node in ast.parse(donors["bin/workitems.py"]).body
        )
        and "bin/wi_fields.py" not in donors
    ):
        raise ValueError("missing human-intent classifier donor")
    if "bin/wi_dedupe.py" not in donors:
        raise MissingDedupeDonorError("missing dedupe intent donor: bin/wi_dedupe.py")
    result = {
        path: text
        for path, text in donors.items()
        if include_identity_candidate or path != "bin/wi_identity.py"
    }
    modules = (
        [("wi_text", "text")]
        + ([("wi_repos", "ownership")] if include_project_ownership else [])
        + ([("wi_identity", "identity")] if include_identity_candidate else [])
    )
    for filename, module in modules:
        names = module_exports(donors[f"bin/{filename}.py"])
        result[f"bin/{filename}.py"] = (
            ('"""Generated compatibility exports; edit canonical source only."""\n')
            + f"from orchestra_dashboard.{module} import ("
            + ", ".join(f"{name} as {name}" for name in names)
            + ")\n"
        )
    if "bin/wi_fields.py" in donors:
        result["bin/wi_fields.py"] = fields_adapter(donors["bin/wi_fields.py"])
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
    result["bin/wi_dedupe.py"] = dedupe_intent_adapter(donors["bin/wi_dedupe.py"])
    if include_identity_candidate:
        result["bin/wi_dedupe.py"] = replace_symbols(
            result["bin/wi_dedupe.py"],
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
    result["bin/workitems.py"] = _workitems(
        donors["bin/workitems.py"], include_project_ownership=include_project_ownership
    )
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


def fields_adapter(source: str) -> str:
    """One classifier authority; other field/answer/gate helpers stay in place."""
    return replace_symbols(
        source,
        {
            name: f"from orchestra_dashboard.text import {name} as {name}"
            for name in ("CALL_KINDS", "ACTION_RE", "ask_kind")
        },
    )


def _read_originals(donor: Path, expected: dict[str, str]) -> dict[str, str]:
    originals = {}
    package_paths = {"bin/orchestra_dashboard/" + name for name in PACKAGE_FILES}
    for relative, digest in expected.items():
        path = Path(relative)
        simple = len(path.parts) == 2 and path.suffix == ".py"
        if (
            not relative.startswith("bin/")
            or ".." in path.parts
            or not (simple or relative in package_paths)
        ):
            raise ValueError("invalid donor path")
        raw = (donor / relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(f"donor hash mismatch: {relative}")
        originals[relative] = raw.decode("utf-8")
    return originals


def _repository_package_before(donor: Path, originals: dict[str, str]) -> None:
    helper = "bin/orchestra_dashboard/repository.py"
    if (donor / helper).exists():
        raise ValueError("existing_output_or_helper")
    for name in PACKAGE_FILES:
        relative = "bin/orchestra_dashboard/" + name
        if (donor / relative).exists() and relative not in originals:
            raise ValueError("unbound_existing_package_source")
    common = "bin/orchestra_dashboard/common.py"
    if originals.get(common) != (PACKAGE / "common.py").read_text():
        raise ValueError("authority_dependency_drift")


def _repository_proposals(donor: Path, originals: dict[str, str]) -> dict[str, str]:
    import export_repository_compat as compat

    _repository_package_before(donor, originals)
    paths = [f"bin/{name}.py" for name in compat.TARGETS]
    if not all(path in originals for path in paths):
        raise ValueError("missing_compat_donors")
    before = {path: originals[path].encode() for path in paths}
    compat.validate_donors(before)
    return compat.propose(*(originals[path] for path in paths))


def _merge_proposals(generated: dict[str, str], proposed: dict[str, str]) -> None:
    if set(proposed) != {
        "bin/preview_recipes.py",
        "bin/action_dedupe.py",
        "bin/orchestra_dashboard/repository.py",
    }:
        raise ValueError("compat_target_inventory_drift")
    for path, text in proposed.items():
        if path in generated and generated[path] != text:
            raise ValueError("conflicting_source_proposals")
        generated[path] = text


def _package_sources() -> dict[str, str]:
    expected_modules = {name for name in PACKAGE_FILES if name.endswith(".py")}
    if {path.name for path in PACKAGE.glob("*.py")} != expected_modules:
        raise ValueError("canonical package inventory drift")
    return {
        "bin/orchestra_dashboard/" + name: (PACKAGE / name).read_text()
        for name in PACKAGE_FILES
    }


def _ownership_vector(donor: Path, originals: dict[str, str]) -> None:
    required = {
        "bin/wi_dedupe.py",
        "bin/wi_repos.py",
        "bin/workitems.py",
        "bin/wi_common.py",
        "bin/wi_text.py",
        "bin/wi_status.py",
        "bin/wi_sources.py",
        "bin/wi_notes.py",
        "bin/wi_quality.py",
    }
    if not required <= originals.keys():
        raise ValueError("incomplete ownership source vector")
    for name in PACKAGE_FILES:
        relative = "bin/orchestra_dashboard/" + name
        if (donor / relative).exists() and relative not in originals:
            raise ValueError("unbound ownership package source")


def _bundle_sources(
    donor: Path,
    originals: dict[str, str],
    *,
    include_identity_candidate: bool,
    include_repository_compat: bool,
    include_project_ownership: bool,
) -> dict[str, str]:
    compat_paths = {"bin/preview_recipes.py", "bin/action_dedupe.py"}
    proposed = (
        _repository_proposals(donor, originals) if include_repository_compat else None
    )
    producer = {
        path: text
        for path, text in originals.items()
        if len(Path(path).parts) == 2 and path not in compat_paths
    }
    generated = adapters(
        producer,
        include_identity_candidate=include_identity_candidate,
        include_project_ownership=include_project_ownership,
    )
    generated.update(_package_sources())
    if proposed is not None:
        _merge_proposals(generated, proposed)
    return generated


def _bundle_admission(
    donor: Path,
    output: Path,
    *,
    include_identity_candidate: bool,
    include_repository_compat: bool,
) -> None:
    if include_repository_compat and include_identity_candidate:
        raise ValueError("identity candidate requires a separate bundle")
    if output.exists() or output.resolve().is_relative_to(donor.resolve()):
        raise ValueError("output must be new and outside donor root")


def build_bundle(
    donor: Path,
    output: Path,
    expected: dict[str, str],
    *,
    include_identity_candidate: bool = False,
    include_repository_compat: bool = False,
    include_project_ownership: bool = False,
) -> dict[str, Any]:
    if type(include_project_ownership) is not bool:
        raise ValueError("project ownership selection must be bool")
    if include_project_ownership and include_identity_candidate:
        raise ValueError("ownership candidate excludes identity changes")
    _bundle_admission(
        donor,
        output,
        include_identity_candidate=include_identity_candidate,
        include_repository_compat=include_repository_compat,
    )
    if "bin/wi_dedupe.py" not in expected:
        if include_project_ownership:
            raise ValueError("incomplete ownership source vector: bin/wi_dedupe.py")
        raise MissingDedupeDonorError("missing dedupe intent donor: bin/wi_dedupe.py")
    if not (donor / "bin/wi_dedupe.py").is_file():
        raise MissingDedupeDonorError("missing dedupe intent donor: bin/wi_dedupe.py")
    originals = _read_originals(donor, expected)
    if include_project_ownership:
        _ownership_vector(donor, originals)
    generated = _bundle_sources(
        donor,
        originals,
        include_identity_candidate=include_identity_candidate,
        include_repository_compat=include_repository_compat,
        include_project_ownership=include_project_ownership,
    )
    patch = []
    rows = []
    for relative, text in sorted(generated.items()):
        if relative.endswith(".py"):
            compile(text, relative, "exec")
        before = originals.get(relative, "")
        patch.extend(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                text.splitlines(keepends=True),
                fromfile="a/" + relative if relative in originals else "/dev/null",
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
        "repository_compat": include_repository_compat,
        "project_ownership": include_project_ownership,
        "runtime_ready": False,
        "deferred_targets": []
        if include_identity_candidate
        else ["bin/wi_identity.py"],
        "dedupe_intent_candidate": {
            "path": "bin/wi_dedupe.py",
            "symbols": ["merge_notes"],
            "canonical_helper": "curation.select_needs_intent",
            "runtime_accepted": False,
        },
    }
    (output / "patch.diff").write_text("".join(patch))
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def _bundle_snapshot(root: Path) -> dict[str, bytes]:
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("identity_candidate"):
        raise ValueError("adapter delta requires core bundles")
    if manifest.get("project_ownership"):
        raise ValueError(
            "ownership requires a complete source vector, not an applied delta"
        )
    snapshot = {}
    for row in manifest["files"]:
        relative = row["path"]
        if (
            not relative.startswith("bin/")
            or ".." in Path(relative).parts
            or not (
                relative.endswith(".py")
                or relative == "bin/orchestra_dashboard/shadow_profile_pins.json"
            )
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
    if "bin/wi_dedupe.py" not in before and "bin/wi_dedupe.py" in after:
        raise DedupeInventoryTransitionError(
            "dedupe intent candidate inventory transition: bin/wi_dedupe.py requires "
            "a separate six-file composition review and fresh before vector; "
            "the existing five-file freeze cannot be extended by applied delta"
        )
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
    parser.add_argument("--include-repository-compat", action="store_true")
    parser.add_argument("--include-project-ownership", action="store_true")
    parser.add_argument("--expected-source", type=Path)
    parser.add_argument("--against-applied-bundle", type=Path)
    args = parser.parse_args()
    if args.include_project_ownership != (args.expected_source is not None):
        parser.error(
            "project ownership requires an explicit complete --expected-source vector"
        )
    if args.include_project_ownership and args.against_applied_bundle is not None:
        parser.error("project ownership cannot use the historical applied-delta path")
    provenance = json.loads(
        (ROOT / "docs/provenance/dashboard-card-producer-20261027.json").read_text()
    )
    expected = {row["donor"]: row["sha256"] for row in provenance["donors"]}
    if args.include_repository_compat:
        expected.update(
            provenance["repository_composition"]["expected_existing_source"]
        )
    if args.expected_source is not None:
        expected = json.loads(args.expected_source.read_text())
        if not isinstance(expected, dict) or not all(
            isinstance(key, str)
            and isinstance(value, str)
            and len(value) == 64
            and all(char in "0123456789abcdef" for char in value)
            for key, value in expected.items()
        ):
            raise ValueError("invalid ownership source vector")
    report = build_bundle(
        args.donor_source,
        args.output,
        expected,
        include_identity_candidate=args.include_identity_candidate,
        include_repository_compat=args.include_repository_compat,
        include_project_ownership=args.include_project_ownership,
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
