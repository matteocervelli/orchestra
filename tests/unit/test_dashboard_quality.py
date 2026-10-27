from typing import Any

from orchestra.dashboard.quality import findings


def local_item() -> dict[str, Any]:
    return {
        "id": "sample",
        "status": "PR review",
        "pr": None,
        "title": "Rivedere la proposta delle card",
        "work_provenance": {
            "kind": "local_artifact_review",
            "subject": {"repo": "orchestra", "artifact": "review://candidate/a"},
            "relation": "primary",
            "source": "task_contract",
            "validation": "validated",
        },
    }


def test_explicit_local_artifact_is_not_missing_integration_pr() -> None:
    assert "pipeline_without_pr" not in {row["code"] for row in findings(local_item())}


def test_primary_integration_still_requires_pr() -> None:
    item = local_item()
    item["work_provenance"]["kind"] = "primary_integration"
    assert "pipeline_without_pr" in {row["code"] for row in findings(item)}


def test_unstamped_detail_cannot_suppress_missing_pr(tmp_path: Any) -> None:
    import json

    from orchestra.dashboard.quality import load_board

    board = {
        "generated": "2026-10-27T20:00:00.000001Z",
        "items": [
            {
                "id": "sample",
                "status": "PR review",
                "title": "Rivedere la proposta delle card",
            }
        ],
    }
    path = tmp_path / "work-items.json"
    path.write_text(json.dumps(board))
    directory = tmp_path / "work-items-detail"
    directory.mkdir()
    (directory / "sample.json").write_text(json.dumps(local_item()))
    assert "pipeline_without_pr" in {
        row["code"] for row in findings(load_board(path)["items"][0])
    }


def test_bound_snapshot_audits_match_direct_and_loaded(tmp_path: Any) -> None:
    import json

    from orchestra.dashboard.quality import audit, bind_detail, load_board

    item = local_item()
    board = {
        "generated": "2026-10-27T20:00:00.000001Z",
        "items": [
            {key: value for key, value in item.items() if key != "work_provenance"}
        ],
    }
    path = tmp_path / "work-items.json"
    path.write_text(json.dumps(board))
    directory = tmp_path / "work-items-detail"
    directory.mkdir()
    (directory / "sample.json").write_text(json.dumps(bind_detail(item, board)))
    assert audit({**board, "items": [item]}) == audit(load_board(path))


def test_every_stale_or_mismatched_detail_is_conservative(tmp_path: Any) -> None:
    import json
    from copy import deepcopy

    from orchestra.dashboard.quality import bind_detail, findings, load_board

    item = local_item()
    board = {
        "generated": "2026-10-27T20:00:00.000001Z",
        "items": [
            {key: value for key, value in item.items() if key != "work_provenance"}
        ],
    }
    path = tmp_path / "work-items.json"
    path.write_text(json.dumps(board))
    directory = tmp_path / "work-items-detail"
    directory.mkdir()
    original = bind_detail(item, board)
    for field, value in (
        ("item_id", "wrong"),
        ("generated", "2026-10-26T20:00:00.000001Z"),
        ("board_sha256", "0" * 64),
        ("version", True),
    ):
        changed = deepcopy(original)
        changed["_producer_snapshot"][field] = value
        (directory / "sample.json").write_text(json.dumps(changed))
        assert "pipeline_without_pr" in {
            r["code"] for r in findings(load_board(path)["items"][0])
        }
    changed = {**original, "id": "wrong"}
    (directory / "sample.json").write_text(json.dumps(changed))
    assert "pipeline_without_pr" in {
        r["code"] for r in findings(load_board(path)["items"][0])
    }


def test_generation_is_unique_across_same_second_and_clock_rollback() -> None:
    from datetime import UTC, datetime

    from orchestra.dashboard.quality import publication_generated

    now = datetime(2026, 10, 27, 20, tzinfo=UTC)
    first = publication_generated(now=now)
    second = publication_generated(first, now=now)
    third = publication_generated(second, now=now.replace(year=2025))
    assert first == "2026-10-27T20:00:00.000000Z"
    assert first < second < third


def test_offset_previous_generation_normalizes_to_utc() -> None:
    from datetime import UTC, datetime

    from orchestra.dashboard.quality import publication_generated

    assert (
        publication_generated(
            "2026-10-27T22:00:00.000010+02:00",
            now=datetime(2026, 10, 27, 19, tzinfo=UTC),
        )
        == "2026-10-27T20:00:00.000011Z"
    )


def test_duplicate_open_ask_ids_report_without_mutating_questions() -> None:
    from copy import deepcopy

    for human, severity in ((True, "error"), (False, "warning")):
        row = {
            **local_item(),
            "your_call": human,
            "ask": [
                {
                    "id": "same-q",
                    "question": "Prima decisione concreta?",
                    "rec": "Procedere con la prima proposta.",
                },
                {
                    "id": "same-q",
                    "question": "Seconda decisione indipendente?",
                    "rec": "Mantenere separata questa scelta.",
                },
            ],
        }
        before = deepcopy(row)
        duplicate = [
            issue for issue in findings(row) if issue["code"] == "duplicate_ask_id"
        ]
        assert len(duplicate) == 1 and duplicate[0]["severity"] == severity
        assert row == before


def test_empty_and_answered_ids_do_not_collide_as_open_questions() -> None:
    for questions in (
        [{"id": ""}, {"id": ""}],
        [{"id": "same-q"}, {"id": "same-q", "answered": True}],
    ):
        row = {**local_item(), "ask": questions}
        assert "duplicate_ask_id" not in {issue["code"] for issue in findings(row)}
