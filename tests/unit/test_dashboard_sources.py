from pathlib import Path

from orchestra.dashboard.sources import tasks


def test_preserves_meaningful_parentheses(tmp_path: Path) -> None:
    directory = tmp_path / "tasks"
    directory.mkdir()
    (directory / "sample.md").write_text(
        "# Task: Correggere le card (titoli e richieste)\nDettagli\n"
    )
    (directory / "COMMON.md").write_text("# Regole comuni\n")
    rows = tasks(tmp_path)
    assert list(rows) == ["sample"]
    assert rows["sample"]["goal"] == "Correggere le card (titoli e richieste)"


def test_task_metadata_enters_internal_reader_shape(tmp_path: Path) -> None:
    directory = tmp_path / "tasks"
    directory.mkdir()
    (directory / "sample.md").write_text(
        "# Rivedere la proposta delle card\n\n```json orchestra-task-meta\n"
        '{"schema":"orchestra-task-meta/v1","work_provenance":'
        '{"kind":"local_artifact_review","subject":{"repo":"orchestra",'
        '"artifact":"review://candidate/a"},"relation":"primary"}}\n```\n'
    )
    row = tasks(tmp_path)["sample"]
    assert row["work_provenance"]["source"] == "task_contract"
    assert row["provenance_errors"] == []


def test_exact_legacy_wrapper_preserves_nested_goal_parentheses(tmp_path: Path) -> None:
    directory = tmp_path / "tasks"
    directory.mkdir()
    (directory / "sample.md").write_text(
        "# Task: sample (Correggere il filtro (telefono))\n"
    )
    assert tasks(tmp_path)["sample"]["goal"] == "Correggere il filtro (telefono)"


def test_exact_legacy_wrapper_extracts_plain_goal(tmp_path: Path) -> None:
    directory = tmp_path / "tasks"
    directory.mkdir()
    (directory / "feat-a.md").write_text("# Task: feat-a (goal A)\n")
    assert tasks(tmp_path)["feat-a"]["goal"] == "goal A"


def test_different_slug_is_not_a_legacy_wrapper(tmp_path: Path) -> None:
    directory = tmp_path / "tasks"
    directory.mkdir()
    (directory / "sample.md").write_text("# Task: different (goal A)\n")
    assert tasks(tmp_path)["sample"]["goal"] == "different (goal A)"


def test_matching_slug_without_exact_task_prefix_keeps_parentheses(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "tasks"
    directory.mkdir()
    (directory / "sample.md").write_text("# sample (goal A)\n")
    assert tasks(tmp_path)["sample"]["goal"] == "sample (goal A)"
