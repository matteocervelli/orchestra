from copy import deepcopy
from typing import Any

import pytest

from orchestra.dashboard.identity import groups


def historical_row(name: str, *, pr: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": name,
        "repo": "nexus",
        "slugs": [name],
        "pr": pr,
        "issue": None,
        "children": [],
        "source": ["pr" if pr else "task"],
        "prs": [pr] if pr else [],
        "updated": "2026-10-27T10:00:00Z",
        "pages": {"post": []},
        "outcomes": [],
        "aliases": [],
    }


def binding(key: str, owner: str, kind: str = "task") -> dict[str, str]:
    return {"kind": kind, "key": key, "owner": owner}


def historical_collapse(
    rows: dict[str, Any], notes: dict[str, Any], bindings: Any
) -> Any:
    from types import SimpleNamespace

    from orchestra.dashboard.curation import collapse

    assembly = SimpleNamespace(
        items=rows, pr_by={}, pr_issue=lambda ref: None, probes=None
    )

    def effective(data: Any, aliases: Any, target: Any, children: Any) -> Any:
        assert target in aliases
        return deepcopy(data.get(target, {}))

    effective_notes = collapse(
        assembly,
        notes,
        {},
        historical_bindings=bindings,
        compute=lambda *args: {"status": "PR review"},
        effective_note=effective,
        issue_ref=lambda repo, n: {"number": n},
    )
    return assembly.items, effective_notes


def test_history_missing_raw_target_reaches_note_and_preserves_child_routes() -> None:
    row = historical_row("employee-task")
    row["children"] = [
        {
            "slug": "child-a",
            "card": {
                "ask": [{"id": "same", "_item": "child-a"}],
                "steps": [{"id": "s", "checked": True}],
                "hide": True,
            },
        },
        {
            "slug": "child-b",
            "card": {
                "ask": [{"id": "same", "_item": "child-b"}],
                "steps": [{"id": "s", "checked": False}],
                "approval": "approved",
            },
        },
    ]
    row.update(pin=True, hide=False, approval="approved", status="Doing")
    notes = {
        "pr-nexus-324": {
            "pin": True,
            "title_it": "Titolo storico",
            "needs": "Approvare anteprima",
            "ask": [{"id": "preview"}],
            "steps": [{"id": "human"}],
        }
    }
    before = deepcopy((row, notes))
    output, projected = historical_collapse(
        {row["id"]: row}, notes, [binding("employee-task", "pr-nexus-324")]
    )
    assert list(output) == ["pr-nexus-324"]
    item = output["pr-nexus-324"]
    assert item["pr"] is None and item["issue"] is None
    assert item["children"] == row["children"]
    assert {k: item[k] for k in ("pin", "hide", "approval", "status")} == {
        k: row[k] for k in ("pin", "hide", "approval", "status")
    }
    assert "pr-nexus-324" in item["_note_aliases"]
    assert projected["pr-nexus-324"] == notes["pr-nexus-324"]
    assert (row, notes) == before


def test_history_two_owners_with_same_primary_and_new_tasks_remain_distinct() -> None:
    pr = {"number": 207, "url": "https://github.com/matteocervelli/nexus/pull/207"}
    rows = {
        name: historical_row(name, pr=pr) for name in ("task-a", "task-b", "new-task")
    }
    bindings = [binding("task-a", "old-a"), binding("task-b", "old-b")]
    mapping, _ = groups(rows, {}, {}, {}, historical_bindings=bindings)
    assert mapping == {
        "old-a": ["task-a"],
        "old-b": ["task-b"],
        "new-task": ["new-task"],
    }
    assert groups(rows, {}, {}, {}, historical_bindings=[])[0] == {
        name: [name] for name in rows
    }


def test_history_exact_qualified_pr_and_task_bindings_share_one_owner() -> None:
    pr = {"number": 207, "url": "https://github.com/matteocervelli/nexus/pull/207"}
    rows = {
        "pr-source": historical_row("pr-source", pr=pr),
        "review": historical_row("review"),
    }
    bindings = [binding(pr["url"], "opaque-207", "pr"), binding("review", "opaque-207")]
    output, _ = historical_collapse(rows, {}, [*bindings, bindings[0]])
    assert list(output) == ["opaque-207"]
    assert output["opaque-207"]["pr"] == pr
    assert set(output["opaque-207"]["slugs"]) == set(rows)


def test_history_conflicts_are_atomic_and_include_owner_evidence() -> None:
    import pytest

    from orchestra.dashboard.history import HistoricalBindingConflict

    rows = {"task": historical_row("task")}
    before = deepcopy(rows)
    with pytest.raises(HistoricalBindingConflict) as caught:
        historical_collapse(
            rows, {}, [binding("task", "old-a"), binding("task", "old-b")]
        )
    assert set(caught.value.owners) == {"old-a", "old-b"}
    assert rows == before


def test_history_target_collision_and_multi_key_owner_conflict_fail_closed() -> None:
    import pytest

    from orchestra.dashboard.history import HistoricalBindingConflict

    pr = {"number": 207, "url": "https://github.com/matteocervelli/nexus/pull/207"}
    cases = [
        (
            {"task": historical_row("task"), "old": historical_row("old")},
            [binding("task", "old")],
        ),
        (
            {"task": historical_row("task", pr=pr)},
            [binding("task", "old-a"), binding(pr["url"], "old-b", "pr")],
        ),
    ]
    cases.append(
        (
            {"a": historical_row("a"), "b": historical_row("b")},
            [binding("a", "b"), binding("b", "c")],
        )
    )
    for rows, bindings in cases:
        before = deepcopy(rows)
        with pytest.raises(HistoricalBindingConflict):
            historical_collapse(rows, {}, bindings)
        assert rows == before


def test_history_invalid_schema_or_unqualified_pr_is_not_authority() -> None:
    import pytest

    from orchestra.dashboard.history import HistoricalBindingConflict

    invalid: list[Any] = [
        None,
        "task",
        {},
        {"kind": "dependency", "key": "task", "owner": "old"},
        binding("task", "../old"),
        binding("#207", "old", "pr"),
        binding("https://[broken", "old", "pr"),
        binding("https://github.com/foreign/nexus/pull/207", "old", "pr"),
        {**binding("task", "old"), "source": "curated_note"},
    ]
    for record in invalid:
        with pytest.raises(HistoricalBindingConflict):
            groups(
                {"task": historical_row("task")},
                {},
                {},
                {},
                historical_bindings=[record],
            )


def test_history_primary_conflict_never_chooses_a_pr_or_changes_assembly() -> None:
    import pytest

    from orchestra.dashboard.history import HistoricalBindingConflict

    first = {"number": 207, "url": "https://github.com/matteocervelli/nexus/pull/207"}
    second = {"number": 208, "url": "https://github.com/matteocervelli/nexus/pull/208"}
    rows = {"a": historical_row("a", pr=first), "b": historical_row("b", pr=second)}
    before = deepcopy(rows)
    with pytest.raises(HistoricalBindingConflict):
        historical_collapse(rows, {}, [binding("a", "old"), binding("b", "old")])
    assert rows == before
    note = {
        "work_provenance": {
            "kind": "primary_integration",
            "relation": "primary",
            "subject": {
                "repo": "nexus",
                "pr": {**second, "host": "github.com", "repo": "matteocervelli/nexus"},
            },
        }
    }
    with pytest.raises(HistoricalBindingConflict):
        groups(
            {"a": rows["a"]},
            {"a": note},
            {},
            {},
            historical_bindings=[binding("a", "old")],
        )


def test_history_dependency_and_unmatched_task_do_not_bind_or_infer_primary() -> None:
    row = historical_row("fresh")
    row["children"] = [
        {"report": "PR https://github.com/matteocervelli/nexus/pull/207"}
    ]
    tasks = {
        "fresh": {"header": "# Atrium #324 dependency", "text": "Nexus PR #207 result"}
    }
    bindings = [
        binding("different-slug", "old"),
        binding(
            "https://github.com/matteocervelli/nexus/pull/207", "pr-nexus-207", "pr"
        ),
    ]
    mapping, refs = groups({"fresh": row}, {}, tasks, {}, historical_bindings=bindings)
    assert mapping == {"fresh": ["fresh"]}
    assert refs["fresh"] == ("nexus", None, None)


def test_history_protected_values_are_preserved_or_conflict_before_mutation() -> None:
    import pytest

    from orchestra.dashboard.history import HistoricalBindingConflict

    rows = {name: historical_row(name) for name in ("a", "b")}
    rows["b"].update(approval="approved", hide=True, ask=[{"id": "independent"}])
    bindings = [binding("a", "old"), binding("b", "old")]
    output, _ = historical_collapse(rows, {}, bindings)
    assert output["old"]["approval"] == "approved" and output["old"]["hide"] is True
    assert output["old"]["ask"] == rows["b"]["ask"]
    rows["a"]["approval"] = "rejected"
    before = deepcopy(rows)
    with pytest.raises(HistoricalBindingConflict):
        historical_collapse(rows, {}, bindings)
    assert rows == before


def test_history_does_not_borrow_note_from_unbound_primary_number_alias() -> None:
    pr = {"number": 207, "url": "https://github.com/matteocervelli/nexus/pull/207"}
    row = historical_row("task", pr=pr)
    notes = {"pr-nexus-207": {"ask": [{"id": "other-owner"}], "pin": True}}
    output, effective = historical_collapse(
        {"task": row}, notes, [binding("task", "old-task")]
    )
    assert "pr-nexus-207" not in output["old-task"]["_note_aliases"]
    assert effective["old-task"] == {}
    assert effective["pr-nexus-207"] == notes["pr-nexus-207"]


def test_history_alias_to_other_curated_owner_fails_before_mutation() -> None:
    import pytest

    from orchestra.dashboard.history import HistoricalBindingConflict

    row = historical_row("task")
    row["aliases"] = ["other-curated"]
    before = deepcopy(row)
    with pytest.raises(HistoricalBindingConflict):
        historical_collapse(
            {"task": row}, {"other-curated": {"pin": True}}, [binding("task", "old")]
        )
    assert row == before


def test_history_forgejo_primary_is_preserved_without_a_github_rewrite() -> None:
    pr = {
        "number": 207,
        "url": "https://git.adlimen.dev/matteocervelli/nexus/pulls/207",
        "state": "open",
    }
    row = historical_row("forgejo-source", pr=pr)
    output, _ = historical_collapse(
        {row["id"]: row}, {}, [binding(pr["url"], "old-fj", "pr")]
    )
    assert output["old-fj"]["pr"] == pr
    assert output["old-fj"]["prs"] == [pr]
    assert output["old-fj"]["issue"] is None


def test_history_owner_note_conflict_and_invalid_primary_are_not_ignored() -> None:
    import pytest

    from orchestra.dashboard.history import HistoricalBindingConflict

    row = historical_row(
        "task",
        pr={"number": 207, "url": "https://github.com/matteocervelli/nexus/pull/207"},
    )
    local = {
        "work_provenance": {
            "kind": "local_artifact_review",
            "relation": "primary",
            "subject": {"repo": "nexus", "artifact": "review://local/a"},
        }
    }
    with pytest.raises(HistoricalBindingConflict):
        historical_collapse({"task": row}, {"old": local}, [binding("task", "old")])
    row["pr"] = {"number": 207, "url": "https://github.com/foreign/nexus/pull/207"}
    with pytest.raises(HistoricalBindingConflict):
        historical_collapse({"task": row}, {}, [binding("task", "old")])


def test_history_same_pr_disagreeing_state_is_conflict_without_compute() -> None:
    import pytest

    from orchestra.dashboard.history import HistoricalBindingConflict

    pr = {"number": 207, "url": "https://github.com/matteocervelli/nexus/pull/207"}
    rows = {
        "a": historical_row("a", pr={**pr, "state": "open"}),
        "b": historical_row("b", pr={**pr, "state": "merged"}),
    }
    with pytest.raises(HistoricalBindingConflict):
        historical_collapse(rows, {}, [binding("a", "old"), binding("b", "old")])
    rows["a"]["repo"] = "foreign/nexus"
    with pytest.raises(HistoricalBindingConflict):
        historical_collapse({"a": rows["a"]}, {}, [binding("a", "old")])


@pytest.mark.parametrize(
    ("owner_repo", "accepted"),
    [
        ("foreign/nexus", False),
        ("app-himalaia", False),
        ("nexus", True),
        ("matteocervelli/nexus", True),
        (None, True),
    ],
)
def test_history_reached_owner_repo_matches_raw_authority_atomically(
    owner_repo: str | None,
    accepted: bool,
) -> None:
    from types import SimpleNamespace

    from orchestra.dashboard.curation import collapse, curate
    from orchestra.dashboard.history import HistoricalBindingConflict

    pr = {"number": 207, "url": "https://github.com/matteocervelli/nexus/pull/207"}
    row = historical_row("task", pr=pr)
    row.update(pin=True, hide=False, approval="approved", status="Doing")
    row["children"] = [
        {
            "slug": "child",
            "card": {
                "ask": [{"id": "independent", "_item": "task"}],
                "steps": [{"id": "human", "checked": False}],
                "hide": False,
            },
        }
    ]
    rows = {"task": row}
    notes = {
        "old": {
            "repo": owner_repo,
            "pin": True,
            "title_it": "Titolo storico",
            "needs": "Approvare anteprima",
            "ask": [{"id": "preview"}],
        }
    }
    if owner_repo is None:
        notes["old"].pop("repo")
    bindings = [binding("task", "old")]
    before = deepcopy((rows, notes, bindings))
    assembly = SimpleNamespace(
        items=rows, pr_by={}, pr_issue=lambda ref: None, probes=None
    )

    def project() -> Any:
        return collapse(
            assembly,
            notes,
            {},
            historical_bindings=bindings,
            compute=lambda *args: {"status": "PR review"},
            effective_note=lambda data, aliases, target, children: deepcopy(
                data[target]
            ),
            issue_ref=lambda repo, n: {"number": n},
        )

    if accepted:
        assert groups(rows, notes, {}, {}, historical_bindings=bindings)[0] == {
            "old": ["task"]
        }
        effective = project()
        projected = deepcopy(assembly.items["old"])
        curate(projected, effective["old"], {})
        assert projected["repo"] == (owner_repo or "nexus")
        assert projected["pr"] == pr
        assert projected["children"] == row["children"]
        assert projected["status"] == "Doing" and projected["approval"] == "approved"
        assert effective["old"] == notes["old"]
    else:
        with pytest.raises(HistoricalBindingConflict):
            groups(rows, notes, {}, {}, historical_bindings=bindings)
        with pytest.raises(HistoricalBindingConflict):
            project()
        assert assembly.items is rows
    assert (rows, notes, bindings) == before
