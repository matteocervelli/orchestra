from pathlib import Path

import pytest

from orchestra.dashboard.sources import authored_title, task_display_title, tasks


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


@pytest.mark.parametrize(
    "sensitive",
    [
        "ghp_" + "InventedOnlyForTest1234567890",
        "sk-" + "InventedOnlyForTest1234567890",
        "AKIA" + "TESTONLY12345678",
        "0123456789abcdef" * 3,
        "QWJjZGVmR2hpSmtM" * 3,
        "invented.person@example.engineering",
        "invented+tag@sub.example.photography",
        "inventèd@esempio.italia",
        "Synthetic_URL-safe-" + "Ab9_" * 10,
        "secret_" + "a1" * 16,
        "_" + "a1" * 16 + "_",
        "aws_AKIA" + "TESTONLY12345678",
        "ROOT " + "12345678901234567890123456789012" + " Verifica la richiesta",
    ],
)
@pytest.mark.parametrize("route", ["goal", "header", "heading", "objective"])
def test_sensitive_shapes_never_become_authored_titles(
    sensitive: str, route: str
) -> None:
    title = (
        sensitive
        if sensitive.startswith("ROOT ")
        else f"Verifica la richiesta {sensitive}"
    )
    if route == "heading":
        task = {"text": f"# {title}\n"}
    elif route == "objective":
        task = {"text": f"## Obiettivo\n{title}\n"}
    else:
        task = {route: title}
    original = task.copy()
    assert task_display_title(task) == ""
    assert task == original


@pytest.mark.parametrize(
    "title",
    [
        "Correggere i titoli delle card",
        "Verifica la richiesta di accesso per la documentazione",
        "Prepara il catalogo e la compatibilità delle notifiche",
        "Rivedi la proposta per il modello AKIRA",
    ],
)
def test_ordinary_italian_authored_titles_are_preserved(title: str) -> None:
    assert authored_title(title) == title


def test_authored_title_rejects_input_over_existing_bound() -> None:
    assert authored_title("Verifica la richiesta " + "a" * 400) == ""


@pytest.mark.parametrize(
    "opaque, rejected",
    [
        ("a" * 23, False),
        ("a" * 24, True),
        ("Z" * 39, False),
        ("Z" * 40, True),
    ],
)
def test_authored_opaque_run_admission_thresholds(opaque: str, rejected: bool) -> None:
    # These are conservative presentation thresholds, not security guarantees.
    title = f"Verifica la richiesta {opaque}"
    assert authored_title(title) == ("" if rejected else title)


def test_overlong_authored_input_is_rejected_before_regex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnexpectedScan:
        def search(self, value: str) -> None:
            raise AssertionError("overlong input reached sensitive scan")

    monkeypatch.setattr(
        "orchestra.dashboard.sources.AUTHOR_SENSITIVE", UnexpectedScan()
    )
    assert authored_title("Verifica la richiesta " + "a" * 400) == ""


def test_unsafe_heading_can_fall_back_to_clean_objective() -> None:
    assert (
        task_display_title(
            {
                "text": "# Verifica la richiesta secret_"
                + "a1" * 16
                + "\n## Obiettivo\nCorreggere i titoli delle card\n"
            }
        )
        == "Correggere i titoli delle card"
    )


@pytest.mark.parametrize(
    "title", ["Verifica la richiesta task-review", "Verifica la richiesta desk-review"]
)
def test_sk_inside_ordinary_word_is_not_a_credential_prefix(title: str) -> None:
    assert authored_title(title) == title


@pytest.mark.parametrize("prefix", ["ROOT1", "ROOT1651", "key", "0x"])
@pytest.mark.parametrize("delimiter", ["", "_", " "])
@pytest.mark.parametrize(
    "shape",
    [
        "AKIA" + "TESTONLY12345678",
        "abcdef12" * 4,
        "ghp_" + "InventedOnlyForTest1234567890",
        "sk-" + "InventedOnlyForTest1234567890",
    ],
)
@pytest.mark.parametrize("route", ["goal", "header", "heading", "objective"])
def test_adversarial_transformed_source_matrix(
    prefix: str, delimiter: str, shape: str, route: str
) -> None:
    import re

    title = f"{prefix}{delimiter}{shape} Verifica la richiesta"
    task = (
        {"text": f"# {title}\n"}
        if route == "heading"
        else {"text": f"## Obiettivo\n{title}\n"}
        if route == "objective"
        else {route: title}
    )
    candidate = task_display_title(task)
    assert len(candidate) <= 400
    assert not re.search(r"AKIA[A-Z0-9]{16}|[a-f0-9]{24,}", candidate, re.I)
    assert not re.search(r"(?<![a-z0-9])(?:ghp_|sk-)[a-z0-9_-]{8,}", candidate, re.I)


def test_reader_unsafe_goal_and_header_fall_back_to_clean_body(tmp_path: Path) -> None:
    directory = tmp_path / "tasks"
    directory.mkdir()
    (directory / "sample.md").write_text(
        "# Task: sample (ROOT1"
        + "abcdef12" * 4
        + " Verifica la richiesta)\n\n## Obiettivo\nCorreggere i titoli delle card\n"
    )
    task = tasks(tmp_path)["sample"]
    assert "abcdef12" in task["goal"] and "abcdef12" in task["header"]
    assert task_display_title(task) == "Correggere i titoli delle card"
