"""Full emitted finish with selected real page/link bodies and synthetic I/O."""

from __future__ import annotations
import __future__

import ast
import hashlib
import json
import re
import subprocess
import sys
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

import pytest
from test_dashboard_runtime_export import exporter, synthetic_donors

from orchestra.dashboard import common, ownership, text
from orchestra.dashboard.curation import curate
from orchestra.dashboard.identity import card_ids
from orchestra.dashboard.provenance import resolve_work_provenance

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/dashboard_ownership"


def selected(name):
    text = (FIXTURE / name).read_text()
    manifest = json.loads((FIXTURE / "manifest.json").read_text())
    assert hashlib.sha256(text.encode()).hexdigest() == manifest["fixtures"][name]
    return text


def full_caller(tmp_path):
    module = exporter()
    donor = tmp_path / "synthetic-donor"
    synthetic_donors(donor)
    source = (donor / "bin/workitems.py").read_text()
    source = module.replace_symbols(
        source,
        {
            "finish": ast.unparse(
                module._function(selected("workitems_selected.py.txt"), "finish")
            )
        },
    )
    emitted = module._workitems(source, include_project_ownership=True)
    # Status computation/other unrelated presentation callbacks are synthetic.
    # The emitted finish, identify, pages/links, curated asks, steps and UI are real.
    namespace = {
        "re": re,
        "Path": Path,
        "HTMLParser": HTMLParser,
        "urlsplit": urlsplit,
        "unquote": unquote,
        "C": SimpleNamespace(
            O=tmp_path, REPOS=common.REPOS, short_repo=common.short_repo
        ),
        "PAGES_ORIGIN": "https://synthetic.example",
        "REPOS": common.REPOS,
        "FULL": common.FULL,
        "short_repo": common.short_repo,
        "STATUSES": common.STATUSES,
        "STEP_RE": re.compile(r"^[A-Za-z0-9_-]{1,40}$"),
        "ASKING_OLD": set(),
        "wi_repos": ownership,
        "curate": curate,
        "resolve_work_provenance": resolve_work_provenance,
        "clip": lambda value, limit: value[:limit],
        "compute": lambda it, *_: {
            "status": it["status"],
            "asking": False,
            "blocked": "",
            "stage": "",
            "done": "",
        },
        "heuristic_text": lambda *_: None,
        "note_status": lambda *_: None,
        "fill_text": lambda *_: None,
        "gates_of": lambda it, *_: it["gates"],
        "ask_of": text.ask_of,
        "ask_link": text.ask_link,
        "split_advice": text.split_advice,
        "is_nothing": text.is_nothing,
        "NO_REC": text.NO_REC,
        "card_ids": card_ids,
        "attach_refs": lambda *_: None,
        "agent_of": lambda *_: "",
        "reviewer_of": lambda *_: "",
        "history_of": lambda *_: [],
        "priority_of": lambda it, *_: (it["priority"], "synthetic"),
        "order_of": lambda note: note["order"],
        "issue_title": lambda *_: "Synthetic issue",
    }
    for name in ("wi_fields", "wi_sources", "wi_pages", "wi_dedupe"):
        code = compile(
            selected(name + "_selected.py.txt"),
            name,
            "exec",
            flags=__future__.annotations.compiler_flag,
        )
        exec(code, namespace)
    identify = module._function(selected("workitems_selected.py.txt"), "identify")
    asks = module._function(selected("workitems_selected.py.txt"), "asks")
    finish = module._function(emitted, "finish")
    exec(
        compile(
            ast.Module([identify, asks, finish], type_ignores=[]),
            "emitted-caller",
            "exec",
            flags=__future__.annotations.compiler_flag,
        ),
        namespace,
    )
    donor_namespace = {**namespace}
    exec(
        compile(selected("wi_repos.py.txt"), "selected-donor", "exec"), donor_namespace
    )
    donor_namespace["wi_repos"] = SimpleNamespace(**donor_namespace)
    original = module._function(selected("workitems_selected.py.txt"), "finish")
    exec(
        compile(
            ast.Module([original], type_ignores=[]),
            "selected-donor-finish",
            "exec",
            flags=__future__.annotations.compiler_flag,
        ),
        donor_namespace,
    )
    return namespace["finish"], namespace["links_of"], donor_namespace["finish"]


def caller_inputs(tmp_path, *, bound=None, scalar="orchestra", repos=None):
    pages = tmp_path / "pages"
    pages.mkdir()
    bound_page = "synthetic-bound-display.html"
    foreign = "synthetic-task-nexus-display.html"
    orchestra_page = "synthetic-task-orchestra-display.html"
    own_page = "synthetic-task-ratio-display.html"
    for name in (bound_page, foreign, orchestra_page, own_page):
        (pages / name).write_text("<h1>Synthetic page</h1>")
    raw_ask = {
        "id": "exact-ask",
        "question": "Synthetic decision?",
        "rec": "Keep exact scope",
        "link": "https://example.test/exact",
        "kind": "decide",
        "options": [{"value": "keep", "label": "Keep", "recommended": True}],
    }
    note = {
        "pin": True,
        "steps": [{"id": "check", "text": "Synthetic check"}],
        "steps_checked": {},
        "order": 7,
        "ask": [raw_ask],
    }
    if repos is not None:
        note["repos"] = repos
    it = {
        "id": "opaque-exact-card",
        "aliases": ["old-bookmark-exact"],
        "repo": scalar,
        "slugs": ["synthetic-task"],
        "children": [],
        "pr": bound if bound and "/pull/" in bound["url"] else None,
        "issue": bound if bound and "/issues/" in bound["url"] else None,
        "title": "Synthetic source task",
        "kind": "fix",
        "branch": "auto/exact",
        "status": "PR review",
        "priority": 2,
        "pin": True,
        "pages": {"pre": [], "mockup": [], "post": [], "display": [bound_page]},
        "gates": {"mockup": "", "comparison": "", "preview": ""},
        "ask": [
            {
                **deepcopy(raw_ask),
                "multi": False,
                "_item": "opaque-exact-card",
                "_answered": False,
                "questions": [],
                "answered": False,
            }
        ],
        "steps": [{**note["steps"][0], "cmd": "", "link": "", "checked": False}],
        "needs": "",
        "proposals": [],
    }
    ctx = SimpleNamespace(
        notes={it["id"]: note},
        ledger={},
        tasks={"synthetic-task": {"text": "Check PNG/ratio and bounds."}},
        spawns={"synthetic-task": {"workdir": "/synthetic/orchestra"}},
        pages=[foreign, orchestra_page, own_page],
        number_repos={},
        html={},
        probes=object(),
        previews={},
        issue_prio={},
        triage={},
        decisions={},
        answered=[],
        acted=set(),
    )
    return it, note, ctx, bound_page, orchestra_page, own_page


@pytest.mark.parametrize("binding", [None, "pr", "issue"])
def test_complete_emitted_finish_preserves_bound_links_and_protected_fields(
    tmp_path, binding
):
    finish, links_of, baseline = full_caller(tmp_path)
    bound = (
        {
            "number": 1,
            "url": "https://github.com/matteocervelli/app-ratio/"
            + ("pull/1" if binding == "pr" else "issues/1"),
        }
        if binding
        else None
    )
    it, note, ctx, page, generic, own = caller_inputs(
        tmp_path,
        bound=bound,
        scalar="ratio" if binding else "orchestra",
        repos=["app-himalaia"] if binding else None,
    )
    protected = (
        "id",
        "aliases",
        "pr",
        "issue",
        "ask",
        "steps",
        "status",
        "pin",
        "priority",
    )
    before = deepcopy({key: it[key] for key in protected})
    note_before = deepcopy(note)
    links_before = links_of(it)
    baseline_item, baseline_ctx = deepcopy((it, ctx))
    baseline(baseline_item, baseline_item["id"], baseline_ctx)
    finish(it, it["id"], ctx)
    assert {key: it[key] for key in protected} == before
    assert note == note_before
    assert it["repos"] == (["app-himalaia"] if binding else [])
    assert it["repo"] == ("ratio" if binding else "")
    assert it["pages"]["display"] == (
        [page, generic, own] if binding else [page, generic]
    )
    # A generic exact-slug page remains reachable for UNKNOWN, while pages scoped
    # to Nexus/Ratio do not attach. Preserve the established matcher and links.
    assert all(it["links"][key] == value for key, value in links_before.items())
    if binding:
        assert it["pages"] == baseline_item["pages"]
        assert it["links"] == baseline_item["links"]
    else:
        # The old PNG/ratio false owner attached an unrelated scoped Ratio page.
        assert baseline_item["pages"]["display"] == [page, generic, own]
        assert own not in it["pages"]["display"]
    assert it["links"]["display"] == page
    assert it["links"].get(binding, "") == (bound["url"] if bound else "")


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "changed", "extra_index"])
def test_emitter_rejects_unexpected_ownership_shapes(tmp_path, mutation):
    module = exporter()
    synthetic_donors(tmp_path)
    source = (tmp_path / "bin/workitems.py").read_text()
    needle = "it['repo'] = it['repo'] or 'orchestra'"
    if mutation == "missing":
        source = source.replace(needle, "pass")
    elif mutation == "duplicate":
        source = source.replace(needle, needle + "\n    " + needle)
    elif mutation == "changed":
        source = source.replace("it['repos'][0]", "it['repos'][-1]")
    else:
        source = source.replace(needle, "it['repo'] = it['repos'][0]\n    " + needle)
    with pytest.raises(ValueError, match="ownership boundary"):
        module._workitems(source, include_project_ownership=True)


def test_ownership_bundle_requires_explicit_selection_and_preserves_donor(tmp_path):
    module = exporter()
    donor = tmp_path / "donor"
    expected = synthetic_donors(donor)
    default, candidate = tmp_path / "default", tmp_path / "candidate"
    core = module.build_bundle(donor, default, expected)
    chosen = module.build_bundle(
        donor, candidate, expected, include_project_ownership=True
    )
    assert core["project_ownership"] is False
    assert chosen["project_ownership"] is True
    assert chosen["runtime_ready"] is chosen["applied"] is False
    raw = (donor / "bin/wi_repos.py").read_text()
    assert (default / "bin/wi_repos.py").read_text() == raw
    assert (
        "orchestra_dashboard.ownership" in (candidate / "bin/wi_repos.py").read_text()
    )
    for relative, digest in expected.items():
        assert hashlib.sha256((donor / relative).read_bytes()).hexdigest() == digest
    imported = subprocess.run(
        [
            sys.executable,
            "-c",
            "import wi_repos, orchestra_dashboard.ownership as own; "
            "assert wi_repos.derive is own.derive; "
            "assert wi_repos.task_repos is own.task_repos; "
            "assert wi_repos.reference_repos is own.reference_repos",
        ],
        cwd=candidate / "bin",
        check=False,
        capture_output=True,
        text=True,
    )
    assert imported.returncode == 0, imported.stderr
    with pytest.raises(ValueError, match="complete source vector"):
        module.build_applied_delta(candidate, candidate)


@pytest.mark.parametrize(
    "bad", ["missing_donor", "unbound_package", "identity", "not_bool"]
)
def test_ownership_vector_and_selection_fail_before_output(tmp_path, bad):
    donor, output = tmp_path / "donor", tmp_path / "output"
    expected = synthetic_donors(donor)
    kwargs = {"include_project_ownership": True}
    if bad == "missing_donor":
        expected.pop("bin/wi_repos.py")
    elif bad == "unbound_package":
        path = donor / "bin/orchestra_dashboard/common.py"
        path.parent.mkdir()
        path.write_text("# synthetic existing package source\n")
    elif bad == "identity":
        kwargs["include_identity_candidate"] = True
    else:
        kwargs["include_project_ownership"] = "yes"
    with pytest.raises(ValueError, match="ownership"):
        exporter().build_bundle(donor, output, expected, **kwargs)
    assert not output.exists()


def test_ownership_composes_with_current_repository_exporter(tmp_path, monkeypatch):
    from test_dashboard_runtime_export import composition_inputs

    module, _, donor, expected = composition_inputs(tmp_path, monkeypatch)
    output = tmp_path / "composed"
    report = module.build_bundle(
        donor,
        output,
        expected,
        include_repository_compat=True,
        include_project_ownership=True,
    )
    assert report["repository_compat"] is report["project_ownership"] is True
    assert report["identity_candidate"] is report["applied"] is False
    assert (output / "bin/orchestra_dashboard/ownership.py").read_bytes() == Path(
        ownership.__file__
    ).read_bytes()
    assert len(list((output / "bin/orchestra_dashboard").glob("*.py"))) == 23
    for relative, digest in expected.items():
        assert hashlib.sha256((donor / relative).read_bytes()).hexdigest() == digest


def test_cli_refuses_ownership_without_an_explicit_vector(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "exporter",
            "--donor-source",
            "synthetic-donor",
            "--output",
            "synthetic-output",
            "--include-project-ownership",
        ],
    )
    with pytest.raises(SystemExit) as error:
        exporter().main()
    assert error.value.code == 2
    assert "explicit complete --expected-source" in capsys.readouterr().err


def test_cli_refuses_historical_delta_before_reading_vector(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "exporter",
            "--donor-source",
            "synthetic-donor",
            "--output",
            "synthetic-output",
            "--include-project-ownership",
            "--expected-source",
            "not-read.json",
            "--against-applied-bundle",
            "synthetic-applied",
        ],
    )
    with pytest.raises(SystemExit) as error:
        exporter().main()
    assert error.value.code == 2
    assert "cannot use the historical applied-delta" in capsys.readouterr().err
