"""Execute only selected static ordinary caller with synthetic dependencies."""

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/dashboard_semantic"


def exporter():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        spec = importlib.util.spec_from_file_location(
            "semantic_export_test", ROOT / "scripts/export_dashboard_semantic.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def test_adapter_changes_only_declared_ast_and_not_publish():
    module = exporter()
    before = (FIXTURE / "selected.py.txt").read_text()
    after = module.adapt_workitems(before)
    original = {n.name: n for n in ast.parse(before).body if hasattr(n, "name")}
    changed = {n.name: n for n in ast.parse(after).body if hasattr(n, "name")}
    for name in original:
        if name not in {"Ctx", "build", "finish"}:
            assert ast.dump(original[name]) == ast.dump(changed[name])
    ctx = changed["Ctx"]
    assert (
        ast.unparse(ctx.body[-1])
        == "source_prs: list[dict] = field(default_factory=list)"
    )
    call = next(
        n
        for n in ast.walk(changed["build"])
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "Ctx"
    )
    assert ast.unparse(call.keywords[-1].value) == "acquired_prs"
    call = next(
        n
        for n in ast.walk(changed["finish"])
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "fill_text"
    )
    assert ast.unparse(call.keywords[-1].value) == "ctx.source_prs"


def test_status_dependency_stays_byte_identical_and_unknown_shape_rejected():
    source = (FIXTURE / "status.py.txt").read_text()
    assert exporter().adapt_status(source) == source
    with pytest.raises(ValueError):
        exporter().adapt_status(
            source.replace('lo.startswith("partial")', 'lo.startswith("unknown")')
        )


def caller_namespace(patched=True):
    from dataclasses import dataclass, field
    from types import SimpleNamespace

    from orchestra.dashboard import text
    from orchestra.dashboard.common import REPOS, STATUSES
    from orchestra.dashboard.curation import curate
    from orchestra.dashboard.provenance import resolve_work_provenance

    namespace = dict(vars(text))
    namespace.update(
        {
            "dataclass": dataclass,
            "field": field,
            "REPOS": REPOS,
            "STATUSES": STATUSES,
            "curate": curate,
            "resolve_work_provenance": resolve_work_provenance,
            "clip": lambda value, cap: str(value)[:cap],
            "iso": str,
            "refs": lambda *args, **kwargs: [],
            "match_pages": lambda *args, **kwargs: None,
            "merged_asks": lambda item, note, card: note,
            "steps_of": lambda note, card: [],
            "ui_of": lambda item, note: False,
            "gates_of": lambda *args: {},
            "attach_refs": lambda *args: None,
            "links_of": lambda item: [],
            "agent_of": lambda children: "",
            "reviewer_of": lambda item: "",
            "history_of": lambda *args: [],
            "priority_of": lambda *args: ("normal", "default"),
            "order_of": lambda note: None,
            "wi_repos": SimpleNamespace(derive=lambda item, *args: [item["repo"]]),
            "owned": lambda item, answers: [],
            "ask_answered": lambda *args: False,
            "card_ids": lambda item: {item["id"]},
        }
    )
    status = (FIXTURE / "status.py.txt").read_text()
    if patched:
        status = exporter().adapt_status(status)
    tree = ast.parse(status)
    tree.body = [
        n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))
    ]
    exec(compile(tree, "selected-static-status", "exec"), namespace)
    source = (FIXTURE / "selected.py.txt").read_text()
    if patched:
        source = exporter().adapt_workitems(source)
    tree = ast.parse(source)
    tree.body = [
        n
        for n in tree.body
        if (not isinstance(n, ast.ImportFrom) or n.module == "__future__")
        and getattr(n, "name", "") != "build"
    ]
    exec(compile(tree, "selected-static-caller", "exec"), namespace)
    return namespace


def run_finish(
    namespace,
    *,
    note=None,
    outcomes=None,
    pr=None,
    source_prs=None,
    decisions=None,
    labels=None,
    triage=None,
):
    from types import SimpleNamespace

    row = {
        "id": "opaque",
        "repo": "nexus",
        "title": (pr or {}).get("title", "Task"),
        "pr": pr,
        "issue": None,
        "branch": "",
        "kind": "feature",
        "slugs": ["child"],
        "children": [
            {
                "start": "2026-01-01",
                "end": "2026-01-02",
                "exit": "0",
                "running": False,
                "slug": "child",
                "tool": "cli",
                "model": "test",
                "duration": 1,
                "cost": 0,
            }
        ],
        "pages": {"pre": [], "post": [], "display": [], "mockup": []},
        "outcomes": outcomes or [{"outcome": "partial: follow-up required"}],
        "decisions": decisions or [],
        "labels": labels or [],
        "triage": triage or {},
        "review": None,
    }
    probes = SimpleNamespace(pr_meta=lambda repo: {})
    ctx = namespace["Ctx"]([], {}, {"opaque": note or {}}, probes, 0, {}, {}, [], set())
    if source_prs is not None:
        ctx.source_prs = source_prs
    namespace["finish"](row, "opaque", ctx)
    return row


def test_ordinary_compute_finish_partial_no_longer_invents_human_question():
    namespace = caller_namespace()
    computed = []
    compute = namespace["compute"]

    def observe(*args):
        result = compute(*args)
        computed.append(dict(result))
        return result

    namespace["compute"] = observe
    after = run_finish(namespace)
    assert computed[0]["asking"] is True
    assert after["status"] == computed[0]["status"] == "Backlog"
    assert after["your_call"] is False and after["ask"] == []
    assert after["needs"] == "Niente per ora: è in coda, la prende un agente."


@pytest.mark.parametrize(
    "authority",
    [
        {"note": {"needs": "Confermi il perimetro?"}},
        {
            "note": {
                "ask": [
                    {"id": "exact-owner", "question": "Orchestra: posso procedere?"}
                ]
            }
        },
        {"note": {"status": "Serve te"}},
        {"decisions": [{"id": "choice", "title": "Quale perimetro?"}]},
        {"triage": {"verdict": "done?"}, "outcomes": [{"outcome": ""}]},
        {
            "pr": {
                "number": 207,
                "url": "https://github.com/matteocervelli/nexus/pull/207",
                "state": "open",
            },
            "labels": ["needs-human"],
        },
    ],
)
def test_partial_patch_preserves_authored_and_independent_human_signals(authority):
    row = run_finish(caller_namespace(), **authority)
    assert row["your_call"] is True and row["ask"]


def test_ordinary_finish_recovers_already_acquired_primary_body_after_curate():
    from copy import deepcopy

    pr = {
        "number": 207,
        "url": "https://github.com/matteocervelli/nexus/pull/207",
        "title": "fix(runtime): preserve fields",
        "state": "open",
    }
    source = {
        **pr,
        "repository": {"name": "nexus", "nameWithOwner": "matteocervelli/nexus"},
        "body": "## Problem\nFields are discarded.\n"
        "## Summary\nPreserve `execution_id`.",
    }
    before = deepcopy(source)
    row = run_finish(caller_namespace(), pr=pr, source_prs=[source])
    assert row["problem"].endswith("Fields are discarded.")
    assert row["solution"].endswith("Preserve `execution_id`.")
    assert source == before
    row = run_finish(
        caller_namespace(),
        pr=pr,
        source_prs=[source],
        note={"edited_fields": ["solution"], "solution": "Authoritative exact note"},
    )
    assert row["solution"] == "Authoritative exact note"
    assert set(row["description_provenance"]) == {"problem"}


@pytest.mark.parametrize(
    "pr,repo",
    [
        (
            {"number": 207, "url": "https://github.com/matteocervelli/nexus/pull/207"},
            "nexus",
        ),
        (
            {
                "number": 207,
                "url": "https://git.adlimen.dev/matteocervelli/nexus/pulls/207/",
            },
            "matteocervelli/nexus",
        ),
        ({"number": 207, "url": "https://github.com/other/nexus/pull/207"}, "nexus"),
        (
            {"number": 207, "url": "https://github.com/matteocervelli/atrium/pull/207"},
            "nexus",
        ),
        (
            {"number": 208, "url": "https://github.com/matteocervelli/nexus/pull/207"},
            "nexus",
        ),
        (
            {"number": True, "url": "https://github.com/matteocervelli/nexus/pull/1"},
            "nexus",
        ),
        (
            {"number": 207, "url": "http://github.com/matteocervelli/nexus/pull/207"},
            "nexus",
        ),
        (
            {"number": 207, "url": "https://github.com/matteocervelli/nexus/pulls/207"},
            "nexus",
        ),
        (
            {
                "number": 207,
                "url": "https://github.com/matteocervelli/nexus/pull/207?x=1",
            },
            "nexus",
        ),
        (
            {
                "number": 207,
                "url": "https://github.com/matteocervelli/nexus/pull/207",
                "repo": "other/nexus",
            },
            "nexus",
        ),
        (
            {
                "number": 207,
                "url": "https://github.com/matteocervelli/nexus/pull/207",
                "host": "other",
            },
            "nexus",
        ),
    ],
)
def test_reviewed_runtime_qualification_matches_canonical_contract(pr, repo):
    import re
    from urllib.parse import urlsplit

    from orchestra.dashboard.common import repository_authority
    from orchestra.dashboard.provenance import qualified_pr

    source = (FIXTURE / "selected.py.txt").read_text()
    node = next(
        n for n in ast.parse(source).body if getattr(n, "name", None) == "qualified_pr"
    )
    namespace = {
        "re": re,
        "urlsplit": urlsplit,
        "repository_authority": repository_authority,
    }
    exec(
        compile(
            ast.Module([node], type_ignores=[]),
            "pinned-runtime-qualification",
            "exec",
            flags=__import__("__future__").annotations.compiler_flag,
        ),
        namespace,
    )
    assert namespace["qualified_pr"](pr, repo) == qualified_pr(pr, repo)


def synthetic_donor(tmp_path, monkeypatch, variant="current"):
    import hashlib
    import json

    from orchestra.dashboard import provenance

    module = exporter()
    donor = tmp_path / "donor"
    source = (FIXTURE / "selected.py.txt").read_text()
    qual = ast.get_source_segment(
        source,
        next(
            n
            for n in ast.parse(source).body
            if getattr(n, "name", "") == "qualified_pr"
        ),
    )
    files = {
        "bin/workitems.py": source,
        "bin/wi_status.py": (FIXTURE / "status.py.txt").read_text(),
        "bin/orchestra_dashboard/provenance.py": "from __future__ import annotations\n"
        + qual,
        "bin/orchestra_dashboard/quality.py": "def findings(item):\n"
        "    rows=[]\n    severity='warning'\n    return rows\n",
    }
    acquisition = (FIXTURE / "acquisition.py.txt").read_text()
    for row in json.loads(module.PINS.read_text())["acquisition_evidence"]:
        node = next(
            node
            for node in ast.parse(acquisition).body
            if getattr(node, "name", "") == row["symbol"]
        )
        files[row["source"]] = ast.get_source_segment(acquisition, node) + "\n"
    if variant == "planned_r1":
        files["bin/orchestra_dashboard/history_index.py"] = (
            "# pinned synthetic R1 helper\n"
        )
    for path, content in files.items():
        target = donor / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    pins = json.loads(module.PINS.read_text())
    for row in pins["acquisition_evidence"]:
        row["source_sha256"] = hashlib.sha256(files[row["source"]].encode()).hexdigest()
    pins["before_vectors"] = {
        variant: {
            path: hashlib.sha256(content.encode()).hexdigest()
            for path, content in files.items()
        }
    }
    pins["before_vectors"].setdefault(
        "current",
        {
            path: digest
            for path, digest in pins["before_vectors"][variant].items()
            if not path.endswith("history_index.py")
        },
    )
    pins["dependency_ast_sha256"] = {
        "provenance.py": {
            "qualified_pr": module._hash_node(
                module._node(
                    files["bin/orchestra_dashboard/provenance.py"], "qualified_pr"
                )
            )
        },
        "quality.py": {
            "findings": module._hash_node(
                module._node(files["bin/orchestra_dashboard/quality.py"], "findings")
            )
        },
    }
    pin_path = tmp_path / "pins.json"
    pin_path.write_text(json.dumps(pins))
    monkeypatch.setattr(module, "PINS", pin_path)
    assert provenance.qualified_pr is not None
    return module, donor


@pytest.mark.parametrize("variant", ["current", "planned_r1"])
def test_bundle_is_inert_preserves_caller_bytes_and_canonical_helpers(
    tmp_path, monkeypatch, variant
):
    module, donor = synthetic_donor(tmp_path, monkeypatch, variant)
    before = {
        p.relative_to(donor).as_posix(): p.read_bytes() for p in donor.rglob("*.py")
    }
    output = tmp_path / "bundle"
    report = module.build_bundle(donor, output, variant)
    assert report["applied"] is report["runtime_ready"] is False
    assert before == {
        p.relative_to(donor).as_posix(): p.read_bytes() for p in donor.rglob("*.py")
    }
    assert len(report["files"]) == 4
    for name in ("text.py", "descriptions.py"):
        assert (output / "bin/orchestra_dashboard" / name).read_bytes() == (
            ROOT / "src/orchestra/dashboard" / name
        ).read_bytes()
    assert (
        "from .descriptions import description_findings"
        in (output / "bin/orchestra_dashboard/quality.py").read_text()
    )


@pytest.mark.parametrize("mutation", ["hash", "helper", "symlink", "unknown_variant"])
def test_bundle_rejects_before_output(tmp_path, monkeypatch, mutation):
    module, donor = synthetic_donor(tmp_path, monkeypatch)
    if mutation == "hash":
        (donor / "bin/wi_status.py").write_text("# drift\n")
    elif mutation == "helper":
        (donor / module.HELPER).write_text("# unexpected helper\n")
    elif mutation == "symlink":
        (donor / module.HELPER).symlink_to("not-present")
    output = tmp_path / "bundle"
    with pytest.raises(ValueError):
        module.build_bundle(
            donor, output, "unknown" if mutation == "unknown_variant" else "current"
        )
    assert not output.exists()


@pytest.mark.parametrize(
    "needs,status,dropped",
    [
        ("Niente: non serve più", "Dropped", "not needed"),
        ("Niente: vedi altra card", "Dropped", "superseded"),
        ("Niente: già fatto", "Deployed", ""),
    ],
)
def test_partial_curated_close_still_settles_before_text(needs, status, dropped):
    row = run_finish(caller_namespace(), note={"needs": needs})
    assert row["status"] == status
    assert row["dropped"] == dropped
    assert row["your_call"] is False
