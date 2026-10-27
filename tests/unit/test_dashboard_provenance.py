import json
from copy import deepcopy
from typing import Any

import pytest

from orchestra.dashboard.provenance import (
    parse_task_provenance,
    propose_request_reconciliation,
    resolve_work_provenance,
)


def declaration() -> dict[str, Any]:
    return {
        "kind": "local_artifact_review",
        "subject": {"repo": "orchestra", "artifact": "review://candidate/a"},
        "relation": "primary",
    }


def task_text(value: dict[str, Any]) -> str:
    return (
        "# Rivedere la proposta delle card\n\n```json orchestra-task-meta\n"
        + json.dumps({"schema": "orchestra-task-meta/v1", "work_provenance": value})
        + "\n```\n"
    )


def test_task_origin_assigned_by_parser_and_conflicts_fail_closed() -> None:
    parsed, errors = parse_task_provenance(task_text(declaration()))
    assert errors == [] and parsed and parsed["source"] == "task_contract"
    assert resolve_work_provenance({}, [{"work_provenance": parsed}], {}) == parsed
    different = {**declaration(), "kind": "primary_integration"}
    assert (
        resolve_work_provenance(
            {"work_provenance": different}, [{"work_provenance": parsed}], {}
        )["kind"]
        == "unknown"
    )
    child = resolve_work_provenance({}, [], {"work_provenance": declaration()})
    assert child["source"] == "child_report" and child["validation"] == "unverified"


@pytest.mark.parametrize(
    "mutator",
    [
        lambda s: s + s,
        lambda s: s.replace("\n\n```", "\nProsa prima del blocco\n```"),
        lambda s: s.replace('"schema":', '"schema":"duplicate", "schema":'),
        lambda s: s.replace("review://candidate/a", "a" * 4100),
        lambda s: s.replace("\n```\n", "\n"),
        lambda s: s.replace('"kind":', '"source":"task_contract", "kind":'),
    ],
)
def test_malformed_metadata_cannot_establish_role(mutator: Any) -> None:
    value, errors = parse_task_provenance(mutator(task_text(declaration())))
    assert value is None and errors


def test_receipts_preserve_independent_requests() -> None:
    base = {
        "mandate_id": "ci-token-configuration",
        "repo": "nexus",
        "target": "ci/checkout",
        "action": "configure_ci_token",
        "scope": "authorized-checkout",
        "created_at": "2026-10-18T10:00:00Z",
    }
    requests = [
        {**base, "id": "token"},
        {**base, "id": "activation", "action": "activate"},
        {**base, "id": "visual", "action": "approve_visual"},
    ]
    receipt = {
        **base,
        "id": "receipt-token",
        "recorded_at": "2026-10-21T10:00:00Z",
        "status": "succeeded",
    }
    original = deepcopy(requests)
    proposals = propose_request_reconciliation(requests, [receipt])
    assert [row["result"] for row in proposals] == [
        "satisfied_candidate",
        "unverified",
        "unverified",
    ]
    assert requests == original
    assert all(
        row["result"] == "unverified"
        for row in propose_request_reconciliation(
            requests, [{**receipt, "action": "merge"}]
        )
    )


def test_merged_dependency_and_approval_do_not_prove_delivery() -> None:
    preview = {
        "id": "preview",
        "mandate_id": "preview-studio-company",
        "repo": "app-himalaia",
        "target": "studio+company/preview",
        "action": "deliver_preview",
        "scope": "approved-preview",
        "created_at": "2026-10-18T10:00:00Z",
    }
    base_receipt = {"recorded_at": "2026-10-21T10:00:00Z", "status": "succeeded"}
    approval = {
        **preview,
        **base_receipt,
        "id": "approval",
        "action": "approve_preview",
    }
    dependency = {
        **preview,
        **base_receipt,
        "id": "signature-merge",
        "mandate_id": "email-signature",
        "target": "email/signature",
        "action": "merge",
    }
    assert (
        propose_request_reconciliation([preview], [approval, dependency])[0]["result"]
        == "unverified"
    )
    approval_request = {**preview, "id": "approval-ask", "action": "approve_preview"}
    assert (
        propose_request_reconciliation([approval_request], [approval])[0]["result"]
        == "satisfied_candidate"
    )


def test_missing_heading_and_deep_json_fail_conservatively() -> None:
    assert parse_task_provenance(
        task_text(declaration()).replace("# Rivedere", "Rivedere")
    )[1]
    text = (
        "# Titolo\n```json orchestra-task-meta\n"
        + "[" * 1000
        + "0"
        + "]" * 1000
        + "\n```\n"
    )
    assert parse_task_provenance(text) == (None, ["task_metadata_depth"])


def test_malformed_url_is_not_a_primary_reference() -> None:
    from orchestra.dashboard.provenance import qualified_pr

    assert (
        qualified_pr(
            {"number": 207, "url": "https://[malformed/nexus/pull/207"}, "nexus"
        )
        is None
    )


def test_identity_delta_reports_changes_and_never_authorizes_runtime() -> None:
    from orchestra.dashboard.provenance import identity_delta

    before = [{"id": "opaque-old", "ask": [{"id": "independent"}], "priority": "P1"}]
    after = [{**before[0], "work_provenance": {"kind": "primary_integration"}}]
    report = identity_delta(before, after)
    assert report["added_ids"] == report["removed_ids"] == []
    assert report["changed_ids"] == ["opaque-old"]
    assert report["old_link_ids_preserved"]
    assert all(report["preservation"]["opaque-old"].values())
    assert report["runtime_ready"] is False
    rekey = identity_delta(before, [{**after[0], "id": "new-id"}])
    assert rekey["added_ids"] == ["new-id"] and rekey["removed_ids"] == ["opaque-old"]
    assert rekey["old_link_ids_preserved"] is False


@pytest.mark.parametrize("origin", ["note", "task"])
@pytest.mark.parametrize(
    "invalid_child",
    [
        {
            "kind": "primary_integration",
            "subject": {"repo": "orchestra", "artifact": "patch://synthetic/core"},
            "relation": "primary",
            "source": "task_contract",
        },
        {
            "kind": "invalid_role",
            "subject": {"repo": "orchestra", "artifact": "patch://synthetic/core"},
            "relation": "primary",
        },
        "malformed",
        None,
    ],
)
def test_invalid_child_declaration_blocks_trusted_local_exemption(
    origin: str, invalid_child: object
) -> None:
    from orchestra.dashboard.quality import findings

    trusted, errors = parse_task_provenance(task_text(declaration()))
    assert not errors
    note = {"work_provenance": declaration()} if origin == "note" else {}
    tasks = (
        [{"work_provenance": trusted, "provenance_errors": []}]
        if origin == "task"
        else []
    )
    card = {"work_provenance": invalid_child}
    before = deepcopy((note, tasks, card))
    resolved = resolve_work_provenance(note, tasks, card)
    assert resolved["kind"] == "unknown" and resolved["validation"] == "conflict"
    row = {
        "id": "synthetic-review",
        "repo": "orchestra",
        "status": "PR review",
        "title": "Rivedere il contratto delle card",
        "pr": None,
        "ask": [],
        "work_provenance": resolved,
    }
    assert {"pipeline_without_pr", "conflicting_work_provenance"} <= {
        issue["code"] for issue in findings(row)
    }
    assert (note, tasks, card) == before


@pytest.mark.parametrize("origin", ["note", "task"])
def test_absent_child_declaration_keeps_trusted_local_role(origin: str) -> None:
    from orchestra.dashboard.quality import findings

    trusted, errors = parse_task_provenance(task_text(declaration()))
    assert not errors
    note = {"work_provenance": declaration()} if origin == "note" else {}
    tasks = (
        [{"work_provenance": trusted, "provenance_errors": []}]
        if origin == "task"
        else []
    )
    resolved = resolve_work_provenance(note, tasks, {})
    assert resolved["kind"] == "local_artifact_review"
    row = {
        "id": "synthetic-review",
        "repo": "orchestra",
        "status": "PR review",
        "title": "Rivedere il contratto delle card",
        "pr": None,
        "ask": [],
        "work_provenance": resolved,
    }
    assert not {"pipeline_without_pr", "conflicting_work_provenance"} & {
        issue["code"] for issue in findings(row)
    }


_ADDITIONAL_PROJECTS = (
    "orchestra",
    "adlimen-cicd",
    "adlimen-infra",
    "adlimen-harness",
    "adlimen-auth",
    "limen-assistant",
)


@pytest.mark.parametrize("repo", _ADDITIONAL_PROJECTS)
@pytest.mark.parametrize(
    "host,route", [("github.com", "pull"), ("git.adlimen.dev", "pulls")]
)
def test_verified_project_names_have_authority_without_display_aliases(
    repo: str, host: str, route: str
) -> None:
    from orchestra.dashboard.common import repository_authority
    from orchestra.dashboard.provenance import qualified_pr
    from orchestra.dashboard.quality import findings

    full_name = f"matteocervelli/{repo}"
    assert repository_authority(repo) == full_name
    assert repository_authority(full_name) == full_name
    primary = {"number": 7, "url": f"https://{host}/{full_name}/{route}/7"}
    before = deepcopy(primary)
    assert qualified_pr(primary, repo) == {**primary, "host": host, "repo": full_name}
    assert qualified_pr(primary, full_name) == {
        **primary,
        "host": host,
        "repo": full_name,
    }
    item = {
        "id": "project-card",
        "repo": repo,
        "title": "Verificare la richiesta di integrazione del progetto",
        "status": "Integration",
        "pr": primary,
        "your_call": False,
    }
    before_item = deepcopy(item)
    assert "pipeline_without_pr" not in {row["code"] for row in findings(item)}
    assert primary == before and item == before_item


@pytest.mark.parametrize(
    "repo,url,number",
    [
        ("orchestra", "https://github.com/another-owner/orchestra/pull/7", 7),
        ("orchestra", "https://github.com/matteocervelli/nexus/pull/7", 7),
        ("orchestra", "https://github.com/matteocervelli/orchestra/pull/8", 7),
        ("orchestra", "https://example.com/matteocervelli/orchestra/pull/7", 7),
        ("orchestra", "https://github.com/matteocervelli/orchestra/pulls/7", 7),
        ("orchestra", "https://git.adlimen.dev/matteocervelli/orchestra/pull/7", 7),
        (
            "unregistered-project",
            "https://github.com/matteocervelli/unregistered-project/pull/7",
            7,
        ),
    ],
)
def test_explicit_project_registry_keeps_primary_guards(
    repo: str, url: str, number: int
) -> None:
    from orchestra.dashboard.provenance import qualified_pr

    assert qualified_pr({"number": number, "url": url}, repo) is None


def test_registry_does_not_add_message_abbreviations_or_foreign_authority() -> None:
    from orchestra.dashboard.common import repository_authority
    from orchestra.dashboard.provenance import qualified_pr

    for repo in (
        "infra",
        "harness",
        "auth",
        "another-owner/orchestra",
        "adlimen/adlimen-harness",
        "matteocervelli/unregistered-project",
        "orchestra/extra/path",
    ):
        assert repository_authority(repo) is None

    assert (
        qualified_pr(
            {
                "number": 7,
                "url": "https://git.adlimen.dev/adlimen/adlimen-harness/pulls/7",
            },
            "adlimen-harness",
        )
        is None
    )


def test_registry_does_not_promote_dependency_or_invalid_provenance() -> None:
    from orchestra.dashboard.quality import findings

    dependency = {
        "kind": "primary_integration",
        "relation": "dependency",
        "subject": {
            "repo": "orchestra",
            "pr": {
                "host": "github.com",
                "repo": "matteocervelli/orchestra",
                "number": 7,
                "url": "https://github.com/matteocervelli/orchestra/pull/7",
            },
        },
    }
    classified = resolve_work_provenance({"work_provenance": dependency}, [], {})
    item = {
        "id": "dependency",
        "repo": "orchestra",
        "status": "Integration",
        "title": "Verificare il seguito della proposta",
        "pr": None,
        "work_provenance": classified,
    }
    assert classified["relation"] == "dependency"
    assert "pipeline_without_pr" in {row["code"] for row in findings(item)}
    local = {
        "kind": "local_artifact_review",
        "relation": "primary",
        "subject": {"repo": "orchestra", "artifact": "review://synthetic/candidate"},
    }
    conflict = resolve_work_provenance(
        {"work_provenance": local},
        [],
        {"work_provenance": {**dependency, "source": "task_contract"}},
    )
    assert conflict["validation"] == "conflict"
    assert {"pipeline_without_pr", "conflicting_work_provenance"} <= {
        row["code"] for row in findings({**item, "work_provenance": conflict})
    }
