import json
import multiprocessing
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from orchestra.dashboard.notes import ensure_title_it, notes_lock
from orchestra.dashboard.titles import validate_title_it


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "Nexus",
        "pr-nexus-324",
        "claude-opus-5-5",
        "Orchestra · lavoro",
        "Correzione dopo la revisione",
        "Riga\nnon valida",
        "https://example.test/path",
    ],
)
def test_rejects_generic_or_invalid_admission(bad: object) -> None:
    with pytest.raises(ValueError):
        validate_title_it(bad)


@pytest.mark.parametrize("phase", ["start", "complete"])
def test_preserves_every_note_field(tmp_path: Path, phase: str) -> None:
    data = {
        "sample": {
            "ask": [{"id": "q1", "options": ["a"]}],
            "approval": "approved",
            "status": "Doing",
            "pages": {"post": "sample.html"},
        },
        "other": {"title_it": "Altro lavoro da preservare"},
    }
    path = tmp_path / "workitems-notes.json"
    path.write_text(json.dumps(data))
    assert (
        ensure_title_it(tmp_path, "sample", "Correggere i titoli delle card", phase)
        == "written"
    )
    assert json.loads(path.read_text()) == {
        **data,
        "sample": {**data["sample"], "title_it": "Correggere i titoli delle card"},
    }


@pytest.mark.parametrize("key", ["title", "title_it"])
def test_preserves_curated_title_without_rewrite(tmp_path: Path, key: str) -> None:
    path = tmp_path / "workitems-notes.json"
    raw = json.dumps({"sample": {key: "Titolo curato già presente"}}, indent=3)
    path.write_text(raw)
    assert (
        ensure_title_it(
            tmp_path, "sample", "Correggere i titoli delle card", "complete"
        )
        == "preserved"
    )
    assert path.read_text() == raw


def title_writer(root: Path, entering: Any) -> None:
    from orchestra.dashboard import notes

    original = notes.notes_lock

    @contextmanager
    def observed_lock(path: Path) -> Iterator[None]:
        entering.set()
        with original(path):
            yield

    notes.notes_lock = observed_lock
    notes.ensure_title_it(root, "sample", "Correggere i titoli delle card", "start")


def test_cooperating_writers_do_not_lose_updates(tmp_path: Path) -> None:
    path = tmp_path / "workitems-notes.json"
    path.write_text("{}")
    context = multiprocessing.get_context("fork")
    entering = context.Event()
    with notes_lock(tmp_path):
        process = context.Process(target=title_writer, args=(tmp_path, entering))
        process.start()
        assert entering.wait(timeout=5), "title writer did not reach the lock boundary"
        # Any read-before-lock implementation has already read {} at this point.
        path.write_text('{"other":{"approval":"approved"}}')
    process.join(timeout=5)
    assert process.exitcode == 0
    assert json.loads(path.read_text()) == {
        "other": {"approval": "approved"},
        "sample": {"title_it": "Correggere i titoli delle card"},
    }


def test_invalid_json_is_never_replaced(tmp_path: Path) -> None:
    path = tmp_path / "workitems-notes.json"
    path.write_text("invalid")
    with pytest.raises(json.JSONDecodeError):
        ensure_title_it(tmp_path, "sample", "Correggere i titoli delle card", "start")
    assert path.read_text() == "invalid"


def test_atomic_replace_failure_preserves_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "workitems-notes.json"
    path.write_text('{"sample":{"approval":"approved"}}')
    original = path.read_bytes()

    def fail_replace(self: Path, target: Path) -> Path:
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="synthetic"):
        ensure_title_it(tmp_path, "sample", "Correggere i titoli delle card", "start")
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".notes-title-*"))


@pytest.mark.parametrize("key", ["title", "title_it"])
def test_nonstring_existing_title_is_not_cleared(tmp_path: Path, key: str) -> None:
    path = tmp_path / "workitems-notes.json"
    raw = json.dumps({"sample": {key: 42}})
    path.write_text(raw)
    with pytest.raises(ValueError, match="notes_title_type"):
        ensure_title_it(tmp_path, "sample", "Correggere i titoli delle card", "start")
    assert path.read_text() == raw


@pytest.mark.parametrize(
    "item_id, title, phase",
    [
        ("../escape", "Correggere i titoli delle card", "start"),
        ("sample", None, "start"),
        ("sample", "Correggere i titoli delle card", "unknown"),
    ],
)
def test_invalid_inputs_fail_before_creating_files(
    tmp_path: Path, item_id: str, title: object, phase: str
) -> None:
    with pytest.raises(ValueError):
        ensure_title_it(tmp_path, item_id, title, phase)
    assert list(tmp_path.iterdir()) == []
