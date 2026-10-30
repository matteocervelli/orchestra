from copy import deepcopy
from typing import Any

from orchestra.dashboard.identity import groups, identity


def ambiguous_item() -> dict[str, Any]:
    return {
        "id": "pr-nexus-324",
        "repo": "nexus",
        "slugs": ["pr-nexus-324"],
        "pr": None,
        "issue": None,
        "children": [
            {"report": "Risultato: https://github.com/matteocervelli/nexus/pull/207"}
        ],
        "outcomes": [],
        "aliases": ["old-review"],
        "approval": "approved",
        "ask": [{"id": "activation", "question": "Attivare il risultato?"}],
    }


def test_bare_dependency_and_card_id_do_not_become_primary_pr() -> None:
    item = ambiguous_item()
    tasks = {
        "pr-nexus-324": {
            "header": "# Rivedere la dipendenza Atrium #324",
            "text": (
                "Dipendenza Atrium #324; risultato Nexus: https://git"
                "hub.com/matteocervelli/nexus/pull/207"
            ),
        }
    }
    assert identity(item, {}, tasks, {}, set()) == ("nexus", None, None)
    before = deepcopy(item)
    mapping, _ = groups({item["id"]: item}, {}, tasks, {})
    assert mapping == {"pr-nexus-324": ["pr-nexus-324"]}
    assert item == before


def test_shared_root_cannot_promote_an_unproven_continuation() -> None:
    anchor = {
        **ambiguous_item(),
        "id": "candidate",
        "slugs": ["candidate"],
        "pr": {
            "number": 207,
            "url": "https://github.com/matteocervelli/nexus/pull/207",
        },
    }
    unrelated = {
        **ambiguous_item(),
        "id": "candidate-review",
        "slugs": ["candidate-review"],
    }
    rows = {anchor["id"]: anchor, unrelated["id"]: unrelated}
    before = deepcopy(rows)
    mapping, _ = groups(rows, {}, {}, {})
    assert mapping == {
        "candidate": ["candidate"],
        "candidate-review": ["candidate-review"],
    }
    assert rows == before


def test_same_qualified_primary_still_groups_without_input_mutation() -> None:
    primary = {"number": 207, "url": "https://github.com/matteocervelli/nexus/pull/207"}
    rows = {
        name: {**ambiguous_item(), "id": name, "slugs": [name], "pr": primary}
        for name in ("first", "second")
    }
    for row in rows.values():
        row.pop("approval", None)
        row.pop("ask", None)
    before = deepcopy(rows)
    mapping, _ = groups(rows, {}, {}, {})
    assert mapping == {"first": ["first", "second"]}
    assert rows == before


def test_different_owner_and_forge_numbers_do_not_collapse() -> None:
    rows = {}
    for name, url in (
        ("github", "https://github.com/matteocervelli/nexus/pull/207"),
        ("other-owner", "https://github.com/another-owner/nexus/pull/207"),
        ("forgejo", "https://git.adlimen.dev/matteocervelli/nexus/pulls/207"),
    ):
        rows[name] = {
            **ambiguous_item(),
            "id": name,
            "slugs": [name],
            "pr": {"number": 207, "url": url},
        }
    mapping, _ = groups(rows, {}, {}, {})
    assert mapping == {
        "github": ["github"],
        "other-owner": ["other-owner"],
        "forgejo": ["forgejo"],
    }


def test_collapse_preserves_historical_aliases_and_never_recovers_issue_from_id() -> (
    None
):
    from types import SimpleNamespace

    from orchestra.dashboard.curation import collapse

    row = {
        **ambiguous_item(),
        "id": "issue-nexus-324",
        "slugs": ["candidate"],
        "aliases": ["historical-alias"],
        "source": ["task"],
        "prs": [],
        "updated": "2026-10-27T10:00:00Z",
        "pages": {"post": []},
    }
    notes = {
        "historical-alias": {
            "approval": "approved",
            "status": "Doing",
            "ask": [{"id": "independent"}],
        }
    }
    before = deepcopy(notes)
    assembly = SimpleNamespace(
        items={row["id"]: row}, pr_by={}, pr_issue=lambda ref: None, probes=None
    )
    seen = []

    def effective(data: Any, aliases: Any, target: Any, children: Any) -> Any:
        seen.extend(aliases)
        return (
            deepcopy(data["historical-alias"]) if "historical-alias" in aliases else {}
        )

    result = collapse(
        assembly,
        notes,
        {},
        compute=lambda *args: {"status": "PR review"},
        effective_note=effective,
        issue_ref=lambda repo, number: {"number": number},
    )
    assert assembly.items[row["id"]]["issue"] is None
    assert "historical-alias" in assembly.items[row["id"]]["aliases"]
    assert "historical-alias" in seen
    assert result[row["id"]]["ask"] == [{"id": "independent"}]
    assert result[row["id"]]["approval"] == "approved"
    assert notes == before


def test_canonical_target_collision_does_not_merge_unproven_existing_card() -> None:
    proved = {
        **ambiguous_item(),
        "id": "legacy-task",
        "slugs": ["legacy-task"],
        "pr": {
            "number": 207,
            "url": "https://github.com/matteocervelli/nexus/pull/207",
        },
    }
    ambiguous = {**ambiguous_item(), "id": "pr-nexus-207", "slugs": ["pr-nexus-207"]}
    mapping, _ = groups({proved["id"]: proved, ambiguous["id"]: ambiguous}, {}, {}, {})
    assert mapping == {"legacy-task": ["legacy-task"], "pr-nexus-207": ["pr-nexus-207"]}


def test_conflicting_trusted_role_does_not_get_ignored_for_existing_pr() -> None:
    row = {
        **ambiguous_item(),
        "pr": {
            "number": 207,
            "url": "https://github.com/matteocervelli/nexus/pull/207",
        },
    }
    local = {
        "kind": "local_artifact_review",
        "relation": "primary",
        "subject": {"repo": "nexus", "artifact": "review://candidate/a"},
    }
    assert identity(row, {"work_provenance": local}, {}, {}) == ("nexus", None, None)


def test_curated_opaque_id_and_exact_id_lookup_survive_primary_correction() -> None:
    old = {
        **ambiguous_item(),
        "id": "pr-nexus-324",
        "pr": {
            "number": 207,
            "url": "https://github.com/matteocervelli/nexus/pull/207",
        },
        "steps": [{"id": "s1"}],
        "priority": "P1",
        "answers": [{"id": "q1"}],
    }
    mapping, refs = groups(
        {old["id"]: old},
        {old["id"]: {"title_it": "Titolo curato da preservare"}},
        {},
        {},
    )
    assert mapping == {"pr-nexus-324": ["pr-nexus-324"]}
    assert refs[old["id"]] == ("nexus", None, 207)
    projected = [{**old, "id": next(iter(mapping))}]
    # Atrium's observed consumer chooses exact id, not aliases. No real API called.
    assert next((row for row in projected if row["id"] == "pr-nexus-324"), None) == old


def test_two_curated_objects_with_same_primary_remain_distinct() -> None:
    rows = {
        name: {
            **ambiguous_item(),
            "id": name,
            "pr": {
                "number": 207,
                "url": "https://github.com/matteocervelli/nexus/pull/207",
            },
        }
        for name in ("first-curated", "second-curated")
    }
    mapping, _ = groups(rows, {name: {"priority": "P1"} for name in rows}, {}, {})
    assert mapping == {name: [name] for name in rows}


def test_explicit_references_keep_repo_and_forge_boundaries() -> None:
    from orchestra.dashboard.identity import explicit_refs

    text = (
        "PR nexus #207; issue nexus #12; Forgejo PR nexus #33; "
        "https://github.com/matteocervelli/nexus/issues/19 "
        "https://github.com/another-owner/nexus/pull/99 PR ratio #50"
    )
    assert explicit_refs(text, "nexus") == {"pr": {207}, "issue": {12, 19}}
    assert explicit_refs("PR #12", "orchestra") == {"pr": set(), "issue": set()}


def test_legacy_reference_context_is_distinct_from_primary_identity_proof() -> None:
    from orchestra.dashboard.common import refs, repository_authority, short_repo
    from orchestra.dashboard.identity import card_ids, repo_of, root_task

    assert refs("nexus #207, #208; ratio #7, #8") == [
        ("nexus", 207),
        ("nexus", 208),
        ("ratio", 7),
        ("ratio", 8),
    ]
    assert refs("PR nexus #207; nexus #208", pr_prefix=True) == [("nexus", 207)]
    assert refs("#9", default="nexus") == [("nexus", 9)]
    assert short_repo("owner/app-ratio") == "ratio"
    assert (
        repository_authority("matteocervelli/app-ratio") == "matteocervelli/app-ratio"
    )
    assert repository_authority("another-owner/nexus") is None
    assert root_task("candidate-review-fix2-next3") == "candidate"
    row = {
        **ambiguous_item(),
        "aliases": ["pr-nexus-207", "issue-nexus-19", "candidate-review"],
    }
    assert card_ids(row) == {"pr-nexus-324", "pr-nexus-207", "issue-nexus-19"}
    generic = {"repo": "orchestra", "slugs": ["ratio-review"]}
    assert repo_of(generic, {}, {"ratio-review": {"text": ""}}) == "ratio"
    assert (
        repo_of({**generic, "slugs": ["sample"]}, {}, {"sample": {"text": "nexus #7"}})
        == "nexus"
    )


def test_qualified_task_primary_and_authoritative_issue_link_preserve_object_id() -> (
    None
):
    import json

    from orchestra.dashboard.provenance import parse_task_provenance

    declaration = {
        "kind": "primary_integration",
        "relation": "primary",
        "subject": {
            "repo": "nexus",
            "pr": {
                "host": "github.com",
                "repo": "matteocervelli/nexus",
                "number": 207,
                "url": "https://github.com/matteocervelli/nexus/pull/207",
            },
        },
    }
    text = (
        "# Rivedere il risultato della proposta\n```json orchestra-task-meta\n"
        + json.dumps(
            {"schema": "orchestra-task-meta/v1", "work_provenance": declaration}
        )
        + "\n```\n"
    )
    parsed, errors = parse_task_provenance(text)
    assert errors == []
    row = {**ambiguous_item(), "slugs": ["sample"]}
    tasks = {"sample": {"work_provenance": parsed}}
    assert identity(row, {}, tasks, {("nexus", 207): 19}) == ("nexus", 19, 207)
    qualified_issue = {
        "number": 22,
        "url": "https://github.com/matteocervelli/nexus/issues/22",
    }
    assert identity(
        {**row, "issue": qualified_issue}, {}, tasks, {("nexus", 207): 19}
    ) == ("nexus", 22, 207)
    assert identity(row, {"repo": "another-owner/nexus"}, tasks, {}) == (
        "nexus",
        None,
        None,
    )
    assert row["id"] == "pr-nexus-324"
