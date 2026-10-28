"""Explicit ownership and exported caller regressions; synthetic inputs only."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestra.dashboard import ownership as canonical_ownership
from orchestra.dashboard.common import FULL, REPOS, short_repo

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/dashboard_ownership"


@pytest.fixture
def ownership():
    return canonical_ownership


@pytest.fixture
def donor_ownership():
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    source = (FIXTURES / "wi_repos.py.txt").read_text()
    assert (
        hashlib.sha256(source.encode()).hexdigest()
        == manifest["fixtures"]["wi_repos.py.txt"]
    )
    tree = ast.parse(source)
    assert all(isinstance(node, (ast.Assign, ast.FunctionDef)) for node in tree.body)
    namespace = {
        "re": re,
        "Path": Path,
        "FULL": FULL,
        "REPOS": REPOS,
        "short_repo": short_repo,
    }
    exec(compile(tree, "selected-synthetic-ownership", "exec"), namespace)
    return SimpleNamespace(**namespace)


def test_pinned_donor_reproduces_original_three_failures(donor_ownership):
    assert donor_ownership.task_repos("Check PNG/ratio and bounds.") == ["app-ratio"]
    assert donor_ownership.task_repos("Do not modify Nexus/exporter/allowlist.") == [
        "nexus"
    ]
    assert derive(
        donor_ownership,
        text="Repo: app-himalaia\nDependency: "
        "https://github.com/matteocervelli/app-ratio/pull/1",
    ) == ["app-ratio"]


def item(**fields):
    return {"repo": "", "slugs": ["synthetic-task"], "children": [], **fields}


def derive(ownership, *, text="", card=None, note=None, spawns=None, ledger=None, **kw):
    return ownership.derive(
        item(**kw),
        card or {},
        note or {},
        {"synthetic-task": {"text": text}},
        spawns or {},
        ledger or [],
    )


@pytest.mark.parametrize(
    "text",
    [
        "Check PNG/ratio and bounds.",
        "Do not modify Nexus/exporter/allowlist.",
        "Dependency: https://github.com/matteocervelli/app-ratio/pull/1",
        "Reference: https://github.com/matteocervelli/nexus/issues/2",
        "Repo: no Nexus changes",
        "Use app-himalaia as an example.",
    ],
)
def test_incidental_text_is_not_ownership(ownership, text):
    assert ownership.task_repos(text) == []
    assert derive(ownership, text=text) == []


@pytest.mark.parametrize("outside", [False, True])
@pytest.mark.parametrize(
    "opening,inner,closing",
    [
        ("````markdown", "```", "````"),
        ("~~~~markdown", "~~~", "~~~~"),
        ("```markdown", "```not-a-closing-fence", "```"),
        ("~~~markdown", "~~~not-a-closing-fence", "~~~"),
        ("```markdown", "~~~", "```"),
        ("~~~markdown", "```", "~~~"),
        ("```markdown", "nested text", "```` \t"),
        ("~~~markdown", "nested text", "~~~~ \t"),
    ],
)
def test_fence_requires_matching_delimiter_length_and_whitespace_tail(
    ownership, opening, inner, closing, outside
):
    text = (
        f"{opening}\n{inner}\n"
        "Worktree: /data/dev/services/nexus/.worktrees/example\n"
        f"{closing}\n"
    )
    if outside:
        text += "Repo: app-himalaia\n"
    expected = ["app-himalaia"] if outside else []
    assert ownership.task_repos(text) == expected
    assert derive(ownership, text=text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Repo: app-himalaia", ["app-himalaia"]),
        ("Repo: ratio", ["app-ratio"]),
        ("Repos: app-himalaia, nexus", ["app-himalaia", "nexus"]),
    ],
)
def test_positive_explicit_task_scope(ownership, text, expected):
    assert derive(ownership, text=text) == expected


def test_explicit_scope_precedes_dependency_url(ownership):
    text = (
        "Repo: app-himalaia\n"
        "Dependency: https://github.com/matteocervelli/app-ratio/pull/1"
    )
    assert derive(ownership, text=text) == ["app-himalaia"]


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "Same privacy author/isolated worktree "
            "/data/dev/projects/app-himalaia/.worktrees/synthetic-source",
            ["app-himalaia"],
        ),
        (
            "Worktree: /data/dev/projects/app-himalaia/.worktrees/synthetic-source",
            ["app-himalaia"],
        ),
        ("Source target: app-himalaia", ["app-himalaia"]),
        (
            "Authorized worktree is NEW "
            "/data/dev/projects/app-himalaia/.worktrees/synthetic-source.",
            ["app-himalaia"],
        ),
        (
            "Resume ONLY /data/dev/projects/app-himalaia/.worktrees/synthetic-source,",
            ["app-himalaia"],
        ),
        (
            "Resume SAME /data/dev/projects/app-himalaia/.worktrees/synthetic-source "
            "after author terminal",
            ["app-himalaia"],
        ),
        ("Canonical repo /data/dev/libs/adlimen-auth.", ["adlimen-auth"]),
        (
            "Worktree /data/dev/libs/adlimen-auth/.worktrees/synthetic-source,",
            ["adlimen-auth"],
        ),
        (
            "Source worktree "
            "/data/dev/projects/app-himalaia/.worktrees/synthetic-source; HEAD abc1234",
            ["app-himalaia"],
        ),
        (
            "Read-only app worktree: "
            "/data/dev/projects/app-himalaia/.worktrees/synthetic-review.",
            ["app-himalaia"],
        ),
        (
            "Review only committed source delta abc1234 in your dedicated detached "
            "worktree /data/dev/projects/app-himalaia/.worktrees/synthetic-review.",
            ["app-himalaia"],
        ),
        (
            "Atrium: nuovo worktree dedicato sotto .worktrees dalla "
            "auto/integration corrente, verificando la base.\n"
            "Task coordinati da Orchestra.\n"
            "Nessun cambiamento a exporter Nexus o allowlist.",
            ["atrium"],
        ),
    ],
)
def test_positive_source_assignment_survives_without_repo_heading(
    ownership, text, expected
):
    assert ownership.task_repos(text) == expected
    assert derive(ownership, text=text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Read-only reference: /data/dev/projects/app-himalaia/.worktrees/reference",
        "Dependency worktree: /data/dev/projects/app-himalaia/.worktrees/dependency",
        "Do not modify /data/dev/projects/app-himalaia/.worktrees/excluded",
        "Nessuna modifica in /data/dev/projects/app-himalaia/.worktrees/escluso",
        "Example: Worktree: /data/dev/projects/app-himalaia/.worktrees/example",
        "Worktree: /data/dev/projects/app-himalaia/.worktrees/reference "
        "(read-only reference)",
        "Source target: no app-himalaia changes",
        "Reference: Source target: app-himalaia",
        "Reference: Atrium: nuovo worktree dedicato sotto .worktrees "
        "dalla auto/integration corrente",
        "Atrium: nessun nuovo worktree dedicato sotto .worktrees "
        "dalla auto/integration corrente",
        "Reference: Resume ONLY /data/dev/projects/app-himalaia/.worktrees/reference,",
        "Do not resume ONLY /data/dev/projects/app-himalaia/.worktrees/excluded,",
        "Reference: Canonical repo /data/dev/libs/adlimen-auth.",
        "Do not review committed source delta abc1234 in your dedicated detached "
        "worktree /data/dev/projects/app-himalaia/.worktrees/excluded.",
        "Example:\n```text\nWorktree: "
        "/data/dev/projects/app-himalaia/.worktrees/example\n```",
    ],
)
def test_source_references_and_exclusions_are_not_assignments(ownership, text):
    assert ownership.task_repos(text) == []
    assert derive(ownership, text=text) == []


def test_assigned_source_excludes_dependency_and_reference_paths(ownership):
    text = (
        "Same privacy author/isolated worktree "
        "/data/dev/projects/app-himalaia/.worktrees/synthetic-source\n"
        "Read-only reference: /data/dev/services/nexus/.worktrees/reference\n"
        "Dependency: https://github.com/matteocervelli/app-ratio/pull/1"
    )
    assert ownership.task_repos(text) == ["app-himalaia"]
    assert derive(ownership, text=text) == ["app-himalaia"]


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "Apply the fix skill. Resume ONLY "
            "/data/dev/projects/app-himalaia/.worktrees/synthetic-source, "
            "after the author is terminal. Other owners retain Nexus.",
            ["app-himalaia"],
        ),
        (
            "Same author continues. Worktree "
            "/data/dev/libs/adlimen-auth/.worktrees/synthetic-source. "
            "Review the scoped delta. Dependency: app-ratio.",
            ["adlimen-auth"],
        ),
        (
            "Apply the fix skill. Source worktree "
            "/data/dev/projects/app-himalaia/.worktrees/branch.with.dots; "
            "HEAD abc1234. No changes to Nexus.",
            ["app-himalaia"],
        ),
        (
            "Review the patch. Atrium: nuovo worktree dedicato sotto .worktrees "
            "dalla auto/integration corrente, verificando la base. "
            "Task coordinati da Orchestra. Nessun cambiamento Nexus.",
            ["atrium"],
        ),
    ],
)
def test_positive_assignments_in_paragraphs(ownership, text, expected):
    assert ownership.task_repos(text) == expected
    assert derive(ownership, text=text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Apply the fix skill. Do not Resume ONLY "
        "/data/dev/projects/app-himalaia/.worktrees/excluded.",
        "Read the dependency. Reference: Worktree "
        "/data/dev/projects/app-himalaia/.worktrees/reference.",
        'Review this quoted example: "Resume ONLY '
        '/data/dev/projects/app-himalaia/.worktrees/example."',
        "Review this example: `Worktree "
        "/data/dev/projects/app-himalaia/.worktrees/example.`",
        "Reference: earlier instructions. Resume ONLY "
        "/data/dev/projects/app-himalaia/.worktrees/reference.",
        "Apply the fix skill. Do not use this example. Worktree "
        "/data/dev/projects/app-himalaia/.worktrees/reference.",
        "Source target: /data/dev/projects/app-himalaia/.worktrees/x/../other",
    ],
)
def test_negated_or_quoted_paragraphs_do_not_assign(ownership, text):
    assert ownership.task_repos(text) == []
    assert derive(ownership, text=text) == []


@pytest.mark.parametrize(
    "extra",
    [
        {"ledger": [{"note": "nexus #2", "gates": "ratio #3"}]},
        {"children": [{"start": 1, "repo_refs": ["app-ratio"]}]},
        {"issue": {"url": "https://github.com/matteocervelli/nexus/issues/2"}},
        {"prs": [{"url": "https://github.com/matteocervelli/app-ratio/pull/1"}]},
        {"repo": "app-ratio"},
        {"spawns": {"synthetic-task": {"workdir": "/synthetic/orchestra"}}},
        {
            "spawns": {
                "synthetic-task": {"workdir": "/synthetic/app-himalaia/.worktrees/x"}
            }
        },
    ],
)
def test_references_launch_directory_and_stale_scalar_do_not_assign(ownership, extra):
    assert derive(ownership, **extra) == []


@pytest.mark.parametrize(
    "pr",
    [
        {"url": "https://github.com/matteocervelli/app-ratio/pull/1", "number": 2},
        {"url": "https://github.com/foreign/app-ratio/pull/1", "number": 1},
        {
            "url": "https://github.com/matteocervelli/app-ratio/pull/1",
            "number": 1,
            "host": "git.adlimen.dev",
        },
    ],
)
def test_unverified_primary_is_not_ownership(ownership, pr):
    assert derive(ownership, pr=pr) == []


def test_verified_primary_is_preserved(ownership):
    pr = {"url": "https://github.com/matteocervelli/app-ratio/pull/1", "number": 1}
    assert derive(ownership, pr=pr) == ["app-ratio"]


@pytest.mark.parametrize(
    "extra",
    [
        {"note": {"repos": ["himalaia", "nexus", "himalaia"]}},
        {"card": {"repos": ["himalaia", "nexus", "himalaia"]}},
        {
            "children": [
                {"start": 1, "card": {"repos": ["ratio"]}},
                {"start": 2, "card": {"repos": ["himalaia", "nexus", "himalaia"]}},
            ]
        },
    ],
)
def test_positive_structured_declarations_are_preserved(ownership, extra):
    assert derive(ownership, text="Check PNG/ratio.", **extra) == [
        "app-himalaia",
        "nexus",
    ]


def test_ownership_does_not_mutate_identity_or_curated_inputs(ownership):
    it = item(
        id="opaque-card",
        aliases=["bookmark-exact"],
        pr={"url": "https://github.com/matteocervelli/app-ratio/pull/1", "number": 1},
        ask=[{"id": "ask-exact"}],
        status="PR review",
        steps={"merge": {"state": "pending"}},
    )
    note = {"repos": ["app-himalaia"], "pin": True}
    before = deepcopy((it, note))
    assert ownership.derive(it, {}, note, {}, {}, []) == ["app-himalaia"]
    assert (it, note) == before


@pytest.fixture
def emitted_finish(tmp_path):
    from test_dashboard_runtime_export import exporter, synthetic_donors

    synthetic_donors(tmp_path)
    module = exporter()
    source = (tmp_path / "bin/workitems.py").read_text()
    selected = (FIXTURES / "workitems_selected.py.txt").read_text()
    source = module.replace_symbols(
        source, {"finish": ast.unparse(module._function(selected, "finish"))}
    )
    return module._function(
        module._workitems(source, include_project_ownership=True), "finish"
    )


def test_unknown_caller_prefix_handles_empty_ownership(emitted_finish):
    it = item(repo="orchestra")
    namespace = {
        "it": it,
        "iid": "opaque-card",
        "wi_repos": SimpleNamespace(derive=lambda *args: []),
        "card": {},
        "note": {},
        "ctx": SimpleNamespace(tasks={}, spawns={}, notes={}, ledger={}),
        "rows": [],
        "REPOS": REPOS,
    }
    prefix = emitted_finish.body[:7]
    exec(
        compile(ast.Module(prefix, type_ignores=[]), "emitted-finish-prefix", "exec"),
        namespace,
    )
    assert it["repos"] == []
    assert it["repo"] == ""


def test_unknown_caller_late_fallback_does_not_invent_orchestra(emitted_finish):
    fallback = ast.dump(ast.parse("it['repo'] = it['repo'] or 'orchestra'").body[0])
    assert all(ast.dump(node) != fallback for node in ast.walk(emitted_finish))
