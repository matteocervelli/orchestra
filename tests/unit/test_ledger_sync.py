from __future__ import annotations

import json
import os
from pathlib import Path

from orchestra import ledger_sync as ls


def child(
    root: Path,
    slug: str,
    err: str,
    events: list[dict[str, object]] | None = None,
    mtime: float = 1791990000,
) -> None:
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / f"{slug}.err").write_text(err, encoding="utf-8")
    os.utime(logs / f"{slug}.err", (mtime, mtime))
    if events is not None:
        (logs / f"{slug}.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events),
            encoding="utf-8",
        )


def claude(text: str) -> list[dict[str, object]]:
    return [{"type": "system"}, {"type": "result", "result": text}]


def codex(text: str) -> list[dict[str, object]]:
    return [
        {"type": "thread.started"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": text}},
    ]


def ledger(root: Path) -> list[dict[str, object]]:
    path = root / "ledger.jsonl"
    return (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )


def test_finished_children_without_row_are_added(tmp_path: Path) -> None:
    child(tmp_path, "a-done", "wall=3\nEXIT=0\n", claude("\n## Done\nmore"))
    child(tmp_path, "b-fail", "EXIT=1\n", codex("Blocked"), mtime=1791990100)

    assert ls.main(["--root", str(tmp_path)]) == 0
    assert ledger(tmp_path) == [
        {
            "ts": "2026-10-14T15:00:00Z",
            "slug": "a-done",
            "tool": "claude",
            "outcome": "done",
            "note": "## Done",
        },
        {
            "ts": "2026-10-14T15:01:40Z",
            "slug": "b-fail",
            "tool": "codex",
            "outcome": "failed",
            "note": "Blocked",
        },
    ]


def test_running_existing_and_malformed_rows_are_skipped(tmp_path: Path) -> None:
    child(tmp_path, "run", "launching\n", claude("x"))
    child(tmp_path, "old", "EXIT=0\n", claude("x"))
    (tmp_path / "ledger.jsonl").write_text(
        "not-json\n" + json.dumps({"slug": "old"}) + "\n", encoding="utf-8"
    )
    assert ls.missing_rows(tmp_path) == []


def test_last_exit_wins_note_is_clipped_and_spawn_tool_is_fallback(
    tmp_path: Path,
) -> None:
    child(tmp_path, "rerun", "EXIT=1\nEXIT=0\n", claude("x" * 300))
    child(tmp_path, "nolog", "EXIT=137\n", mtime=1791990100)
    (tmp_path / "logs" / "spawns.jsonl").write_text(
        json.dumps({"slug": "nolog", "tool": "pi"}) + "\n", encoding="utf-8"
    )
    first, second = ls.missing_rows(tmp_path)
    assert first["outcome"] == "done"
    assert len(first["note"]) == 200 and first["note"].endswith("…")
    assert (second["tool"], second["note"]) == ("pi", "EXIT=137, no final report")


def test_dry_run_writes_nothing_and_second_run_is_idempotent(
    tmp_path: Path, capsys: object
) -> None:
    child(tmp_path, "a", "EXIT=0\n", claude("ok"))
    assert ls.main(["--root", str(tmp_path), "--dry-run"]) == 0
    assert ledger(tmp_path) == []
    assert ls.main(["--root", str(tmp_path)]) == 0
    assert ls.main(["--root", str(tmp_path)]) == 0
    assert [row["slug"] for row in ledger(tmp_path)] == ["a"]
