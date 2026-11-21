"""Exercise the exported caller's actual override guard from the static donor."""

import ast
from pathlib import Path

import pytest
from test_dashboard_runtime_export import exporter, synthetic_donors

from orchestra.dashboard.common import STATUSES

ROOT = Path(__file__).resolve().parents[2]


def caller(tmp_path: Path) -> str:
    synthetic_donors(tmp_path)
    donor = tmp_path / "bin/workitems.py"
    source = donor.read_text()
    selected = (
        ROOT / "tests/fixtures/dashboard_ownership/workitems_selected.py.txt"
    ).read_text()
    module = exporter()
    finish = module._function(selected, "finish")
    source = module.replace_symbols(source, {"finish": ast.unparse(finish)})
    return module._workitems(source)


def resolve(source: str, computed: str, override: str | None, running=False):
    finish = exporter()._function(source, "finish")
    start = next(
        n
        for n, node in enumerate(finish.body)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "override" for t in node.targets)
    )
    end = next(
        n
        for n in range(start + 1, len(finish.body))
        if isinstance(finish.body[n], ast.Assign)
        and ast.unparse(finish.body[n].targets[0]) == "it['status']"
    )
    block = ast.Module(body=finish.body[start : end + 1], type_ignores=[])
    item = {"_deduped": True, "prs": [{"state": "merged"}, {"state": "merged"}]}
    scope = {
        "it": item,
        "res": {"status": computed},
        "note": {"status": override},
        "running": running,
        "ch": [],
        "STATUSES": STATUSES,
        "note_status": lambda value, computed: value,
    }
    exec(compile(block, "<exported-closure-guard>", "exec"), scope)
    return item["status"]


@pytest.mark.parametrize("computed", ["Integration", "Main", "Deployed"])
def test_merged_aggregate_honors_explicit_closure(tmp_path, computed):
    assert resolve(caller(tmp_path), computed, "Dropped") == "Dropped"


@pytest.mark.parametrize("computed", ["Integration", "Main", "Deployed"])
def test_merged_aggregate_still_rejects_stale_earlier_status(tmp_path, computed):
    assert resolve(caller(tmp_path), computed, "PR review") == computed


def test_no_override_does_not_invent_completion(tmp_path):
    assert resolve(caller(tmp_path), "Main", None) == "Main"


def test_running_child_still_prevents_closure(tmp_path):
    assert resolve(caller(tmp_path), "Main", "Dropped", running=True) == "Main"


def test_canonical_closure_survives_note_merge_and_preserves_curated_fields():
    from test_dashboard_alias_intent import FIXTURE, execute

    namespace = execute(exporter().dedupe_intent_adapter(FIXTURE.read_text()))
    namespace["STATUSES"] = STATUSES
    canonical = {
        "status": "Dropped",
        "title_it": "Titolo curato",
        "problem": "Problema",
        "solution": "Soluzione",
        "needs": "Niente: gia unita.",
        "pin": True,
        "work_provenance": {"kind": "local_artifact_review"},
    }
    notes = {"card": canonical, "longer-alias": {"status": "PR review"}}
    merged = namespace["effective_note"](notes, list(notes), "card", [])
    assert merged["status"] == "Dropped"
    for key in ("title_it", "problem", "solution", "needs", "work_provenance"):
        assert merged[key] == canonical[key]


def test_dropped_alias_does_not_close_canonical_card():
    from test_dashboard_alias_intent import FIXTURE, execute

    namespace = execute(exporter().dedupe_intent_adapter(FIXTURE.read_text()))
    namespace["STATUSES"] = STATUSES
    notes = {"card": {"status": "Main"}, "alias": {"status": "Dropped"}}
    merged = namespace["effective_note"](notes, list(notes), "card", [])
    assert merged["status"] == "Main"
