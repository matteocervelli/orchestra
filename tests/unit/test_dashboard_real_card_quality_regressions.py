"""Real finish/text regressions from the task-input and Levero public audits.

Task excerpts below retain author intent, not execution/approval claims. The
existing caller fixture supplies synthetic I/O and compute; finish, asks,
curation, task parsing and text rendering are the real selected/emitted code.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from test_dashboard_ownership_caller import caller_inputs, full_caller

from orchestra.dashboard import sources, text
from orchestra.dashboard.quality import findings


@pytest.fixture
def quality_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, dict[str, Any], dict[str, Any], Any]:
    finish, _, _ = full_caller(tmp_path)
    item, note, ctx, *_ = caller_inputs(
        tmp_path, scalar="orchestra", repos=["orchestra"]
    )
    note.pop("ask")
    note.pop("steps")
    note["pin"] = False
    item.update(
        title="",
        raw_title="",
        problem="",
        solution="",
        needs="",
        status="Backlog",
        ask=[],
        steps=[],
        labels=[],
        decisions=[],
    )
    ctx.tasks = {}
    ctx.spawns = {}
    ctx.pages = []
    # Replace only the fixture's presentation no-op with canonical SOURCE text.
    monkeypatch.setitem(finish.__globals__, "fill_text", text.fill_text)
    return finish, item, note, ctx


def test_zero_child_task_keeps_specific_preview_subject(
    tmp_path: Path, quality_caller: tuple[Any, dict[str, Any], dict[str, Any], Any]
) -> None:
    finish, item, note, ctx = quality_caller
    directory = tmp_path / "tasks"
    directory.mkdir()
    slug = "hima22-isolated-candidate-preview-1651-sol61"
    item["id"], item["slugs"] = slug, [slug]
    ctx.notes = {slug: note}
    (directory / f"{slug}.md").write_text(
        "# ROOT1651 — build e preview .22 IN QA, fonte accettata\n\n"
        "Preparare build e preview isolata di Himalaia .22 per la verifica QA.\n"
    )
    ctx.tasks = sources.tasks(tmp_path)
    item["goal"] = ctx.tasks[slug]["goal"]
    before_tasks = deepcopy(ctx.tasks)
    assert item["children"] == []

    finish(item, item["id"], ctx)

    title = item["title"].casefold()
    assert "preview" in title and ".22" in title
    assert not title.endswith("· lavoro")
    assert "generic_title" not in {finding["code"] for finding in findings(item)}
    assert note["pin"] is False
    assert ctx.tasks == before_tasks


def test_levero_repeated_heading_does_not_discard_specific_body_goal(
    tmp_path: Path, quality_caller: tuple[Any, dict[str, Any], dict[str, Any], Any]
) -> None:
    finish, item, note, ctx = quality_caller
    directory = tmp_path / "tasks"
    directory.mkdir()
    slug = "levero-goal-assessment-m2-20261028"
    item["id"], item["slugs"] = slug, [slug]
    ctx.notes = {slug: note}
    # Minimal author text, not the child's execution report/logs.
    (directory / f"{slug}.md").write_text(
        "# Levero goal attivo — 28 ottobre 2026\n\n"
        "## Consegna corrente\n"
        "IMPLEMENTA M2 PostgreSQL/API/UI minima per Assessment.\n"
        "Bozza, ripresa, submit e risultato persistito su dati sintetici.\n"
    )
    ctx.tasks = sources.tasks(tmp_path)
    item["goal"] = ctx.tasks[slug]["goal"]
    before_tasks = deepcopy(ctx.tasks)
    assert item["goal"] == "Levero goal attivo — 28 ottobre 2026"

    finish(item, item["id"], ctx)

    title = item["title"].casefold()
    assert "postgresql" in title and "m2" in title
    assert not title.endswith("· lavoro")
    assert "generic_title" not in {finding["code"] for finding in findings(item)}
    assert ctx.tasks == before_tasks


def test_failed_child_without_human_intent_does_not_create_placeholder_call(
    quality_caller: tuple[Any, dict[str, Any], dict[str, Any], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finish, item, note, ctx = quality_caller
    item["id"] = "levero-goal-preview-resume-20261028"
    ctx.notes = {item["id"]: note}
    note["title_it"] = "Verificare la prova privata Levero"
    item["children"] = [
        {
            "slug": item["id"],
            "start": "2026-10-28T07:00:00Z",
            "end": "2026-10-28T07:08:20Z",
            "exit": "1",
            "running": False,
            "tool": "synthetic",
            "model": "synthetic",
            "duration": 500,
            "cost": 0,
        }
    ]
    # Observed upstream state of the four Levero cards; compute itself is not
    # part of this selected SOURCE caller fixture. Do not reimplement it here.
    monkeypatch.setitem(
        finish.__globals__,
        "compute",
        lambda *_: {
            "status": "Backlog",
            "asking": True,
            "blocked": "",
            "stage": "",
            "done": "",
        },
    )
    assert "ask" not in note and item["decisions"] == []

    finish(item, item["id"], ctx)

    assert item["your_call"] is False
    assert item["serve_te"] is False
    assert item["ask"] == []
    assert item["needs"] != text.SERVE_NEEDS


def test_concrete_future_card_question_remains_an_independent_open_call(
    quality_caller: tuple[Any, dict[str, Any], dict[str, Any], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finish, item, note, ctx = quality_caller
    note["title_it"] = "Verificare la prova privata Levero"
    explicit = {
        "id": "independent-private-qa-choice",
        "question": "Usare il solo dataset sintetico per la prossima prova privata?",
        "rec": "Usare il dataset sintetico nel perimetro già definito.",
        "kind": "decide",
        "options": [
            {"value": "synthetic", "label": "Solo dati sintetici", "recommended": True},
            {"value": "hold", "label": "Tenere sospesa la prova"},
        ],
    }
    # Synthetic future explicit intent, deliberately absent from the failed
    # Levero witness. A generic failure signal must not swallow this question.
    item["children"] = [
        {
            "slug": "synthetic-task",
            "start": "2026-10-28T07:00:00Z",
            "end": "2026-10-28T07:08:20Z",
            "exit": "1",
            "running": False,
            "tool": "synthetic",
            "model": "synthetic",
            "duration": 500,
            "cost": 0,
            "card": {"ask": [deepcopy(explicit)]},
        }
    ]
    monkeypatch.setitem(
        finish.__globals__,
        "compute",
        lambda *_: {
            "status": "Backlog",
            "asking": True,
            "blocked": "",
            "stage": "",
            "done": "",
        },
    )

    finish(item, item["id"], ctx)

    assert item["your_call"] is True
    assert len(item["ask"]) == 1
    question = item["ask"][0]
    assert question["id"] == explicit["id"]
    assert question["question"] == explicit["question"]
    assert question["rec"] == explicit["rec"]
    assert question["_item"] == item["id"]
    assert question["answered"] is False


def test_curated_title_and_protected_identity_outrank_task_fallback(
    quality_caller: tuple[Any, dict[str, Any], dict[str, Any], Any],
) -> None:
    finish, item, note, ctx = quality_caller
    note["title_it"] = "Conservare il perimetro italiano già curato"
    item["title"] = "# ROOT1651 — build e preview .22 IN QA"
    item["priority"] = "P0"
    before_note = deepcopy(note)
    protected = ("id", "repo", "status", "priority", "aliases", "ask", "steps")
    before_fields = deepcopy({key: item[key] for key in protected})

    finish(item, item["id"], ctx)

    assert item["title"] == before_note["title_it"]
    assert {key: item[key] for key in protected} == before_fields
    assert "title_it" not in item["auto"]
    assert note == before_note


def test_failed_child_keeps_explicit_note_question_and_empty_override(
    quality_caller: tuple[Any, dict[str, Any], dict[str, Any], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finish, item, note, ctx = quality_caller
    item["children"] = [
        {
            "slug": "synthetic-task",
            "start": "2026-10-28T07:00:00Z",
            "end": "2026-10-28T07:08:20Z",
            "exit": "1",
            "running": False,
            "tool": "synthetic",
            "model": "synthetic",
            "duration": 500,
            "cost": 0,
        }
    ]
    question = {
        "id": "manual-choice",
        "question": "Confermare il perimetro dei dati sintetici?",
        "rec": "Mantenere il perimetro sintetico.",
        "kind": "decide",
    }
    note["ask"] = [deepcopy(question)]
    monkeypatch.setitem(
        finish.__globals__,
        "compute",
        lambda *_: {
            "status": "Backlog",
            "asking": True,
            "blocked": "",
            "stage": "",
            "done": "",
        },
    )
    before = deepcopy(note)
    finish(item, item["id"], ctx)
    assert item["your_call"] is True
    assert item["ask"][0]["id"] == question["id"]
    assert note == before
    # Existing deliberate note retirement remains authoritative over card.ask.
    note["ask"] = []
    item["children"][0]["card"] = {"ask": [deepcopy(question)]}
    finish(item, item["id"], ctx)
    assert item["ask"] == [] and item["your_call"] is False


def test_failed_child_keeps_concrete_authored_needs(
    quality_caller: tuple[Any, dict[str, Any], dict[str, Any], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finish, item, _, ctx = quality_caller
    item["children"] = [
        {
            "slug": "synthetic-task",
            "start": "2026-10-28T07:00:00Z",
            "end": "2026-10-28T07:08:20Z",
            "exit": "1",
            "running": False,
            "tool": "synthetic",
            "model": "synthetic",
            "duration": 500,
            "cost": 0,
        }
    ]
    manual = "Confermare la finestra della prova privata su dati sintetici."
    item["needs"] = manual
    monkeypatch.setitem(
        finish.__globals__,
        "compute",
        lambda *_: {
            "status": "Backlog",
            "asking": True,
            "blocked": "",
            "stage": "",
            "done": "",
        },
    )
    finish(item, item["id"], ctx)
    assert item["needs"] == manual
    assert item["your_call"] is True
    assert item["ask"][0]["question"] == manual


def test_english_unsafe_and_ambiguous_author_sources_keep_honest_fallback(
    quality_caller: tuple[Any, dict[str, Any], dict[str, Any], Any],
) -> None:
    finish, item, _, ctx = quality_caller
    for value in (
        "Implement a complete private preview with isolated data",
        "Correggere il comando python3 /private/synthetic.py --apply",
        "Verifica completata e rilascio APPROVE",
        "review delta Sol separata (da avviare da Orchestra)",
        "Richiesta chat-alerts → Orchestra Plan — 28 ottobre 2026",
        "FB05-B GO sorgenti — Atrium A1+A2 integrati",
    ):
        assert sources.authored_title(value) == ""
    for heading, subject in (
        ("Oracolo — catalogo documenti reali e compatibilità fase1", "catalogo"),
        ("Review indipendente — DCF e catalogo voci Oracolo", "dcf"),
        ("Oracolo — review separata sorgenti immagine/config", "immagine"),
        ("Delta-review indipendente P7 mapper R1/R2", "mapper"),
        ("Ratio — review P2 metriche backup", "metriche"),
        (
            "FB05 K1 — client condiviso, source-only e subordinato al freeze A2",
            "client",
        ),
    ):
        assert subject in sources.authored_title(heading).casefold()
    inline = sources.task_display_title(
        {
            "goal": "Programma: goal attivo",
            "header": "# Programma: goal attivo",
            "text": (
                "# Programma: goal attivo\n"
                "Scopo: permettere un nuovo tentativo sintetico sullo staging .21.\n"
            ),
        }
    )
    assert "staging" in inline and ".21" in inline
    objective = sources.task_display_title(
        {
            "goal": "Programma: goal attivo",
            "text": (
                "# Programma: goal attivo\n"
                "## Obiettivo: una candidata integrata "
                "auth+UI+CI+security revisionabile\n"
                "Base 784c405 era remota ieri; verifica ora.\n"
            ),
        }
    )
    assert "candidata integrata" in objective and "Base" not in objective
    assert (
        sources.task_display_title(
            {
                "goal": "Programma: goal attivo",
                "text": (
                    "# Programma: goal attivo\n## Scopo\n"
                    "Base 784c405 era remota ieri; verifica ora.\n"
                ),
            }
        )
        == ""
    )
    assert "preview" in sources.task_display_title(
        {
            "goal": "Read COMMON fully before working.",
            "header": "Read COMMON fully before working.",
            "text": (
                "Read COMMON fully before working.\n\n"
                "# Preparare la preview isolata per la verifica\n"
            ),
        }
    )
    item["slugs"] = ["first", "second"]
    ctx.tasks = {
        "first": {"goal": "Preparare la preview isolata per la verifica"},
        "second": {"goal": "Correggere il recupero del backup prima della verifica"},
    }
    before = deepcopy(ctx.tasks)
    finish(item, item["id"], ctx)
    assert item["title"].endswith("· lavoro")
    assert "generic_title" in {finding["code"] for finding in findings(item)}
    assert ctx.tasks == before


def test_mixed_explicit_questions_keep_positional_answer_ownership(
    quality_caller: tuple[Any, dict[str, Any], dict[str, Any], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finish, item, note, ctx = quality_caller
    item["needs"] = text.SERVE_NEEDS
    note["ask"] = [
        {
            "kind": "approve merge",
            "link": "https://example.test/pull/1",
            "_item": "retired-child",
            "_answered": True,
        },
        {
            "id": "future-choice",
            "question": "Confermare i dati sintetici?",
            "rec": "Usare solo dati sintetici.",
            "_item": "future-child",
        },
    ]
    monkeypatch.setitem(
        finish.__globals__,
        "compute",
        lambda *_: {
            "status": "Backlog",
            "asking": True,
            "blocked": "",
            "stage": "",
            "done": "",
        },
    )
    finish(item, item["id"], ctx)
    assert len(item["ask"]) == 2
    assert item["ask"][0]["_item"] == "retired-child"
    assert item["ask"][0]["answered"] is True
    assert item["ask"][1]["_item"] == "future-child"
    assert item["ask"][1]["answered"] is False
    assert item["your_call"] is True


@pytest.mark.parametrize("failed", [False, True])
def test_explicit_kind_only_question_remains_visible(
    failed: bool,
    quality_caller: tuple[Any, dict[str, Any], dict[str, Any], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finish, item, note, ctx = quality_caller
    note["ask"] = [{"kind": "approve merge", "link": "https://example.test/pull/1"}]
    if failed:
        item["children"] = [
            {
                "slug": "synthetic-task",
                "start": "2026-10-28T07:00:00Z",
                "exit": "1",
                "running": False,
                "tool": "synthetic",
                "model": "synthetic",
                "duration": 1,
                "cost": 0,
            }
        ]
    monkeypatch.setitem(
        finish.__globals__,
        "compute",
        lambda *_: {
            "status": "Backlog",
            "asking": True,
            "blocked": "",
            "stage": "",
            "done": "",
        },
    )
    finish(item, item["id"], ctx)
    assert len(item["ask"]) == 1
    assert item["ask"][0]["kind"] == "approve merge"
    assert item["your_call"] is True


def test_failed_child_retires_only_heuristic_generated_placeholder(
    quality_caller: tuple[Any, dict[str, Any], dict[str, Any], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finish, item, _, ctx = quality_caller
    item["children"] = [
        {
            "slug": "synthetic-task",
            "start": "2026-10-28T07:00:00Z",
            "exit": "1",
            "running": False,
            "tool": "synthetic",
            "model": "synthetic",
            "duration": 1,
            "cost": 0,
        }
    ]
    monkeypatch.setitem(
        finish.__globals__,
        "heuristic_text",
        lambda it, *_: it.update(needs=text.SERVE_NEEDS),
    )
    monkeypatch.setitem(
        finish.__globals__,
        "compute",
        lambda *_: {
            "status": "Backlog",
            "asking": True,
            "blocked": "",
            "stage": "",
            "done": "",
        },
    )
    finish(item, item["id"], ctx)
    assert item["ask"] == []
    assert item["your_call"] is False
    assert item["needs"] != text.SERVE_NEEDS


@pytest.mark.parametrize(
    "title",
    [
        "Add solo mode for e-mail digest",
        "Review la cache initialization",
    ],
)
def test_raw_pr_title_does_not_bypass_task_only_presentation_fallback(
    title: str,
    quality_caller: tuple[Any, dict[str, Any], dict[str, Any], Any],
) -> None:
    _, item, _, _ = quality_caller
    item.update(title=title, raw_title=title, pr={"number": 7})
    text.fill_text(item, set(), False)
    assert "title_it" in item["auto"]
    assert item["title"] != title


@pytest.mark.parametrize(
    "title",
    [
        "Verificare il file pyproject.toml prima della prova",
        "Verificare il file compose.yaml prima della prova",
        "Correggere il renderer in src/ui/renderer prima della prova",
        "Verificare il comando git status prima della prova",
        "Verificare `python3 helper` prima della prova",
        "Verificare il servizio 192.0.2.10 prima della prova",
        "Verificare il servizio example.dev prima della prova",
    ],
)
def test_author_title_does_not_publish_operational_paths_or_commands(
    title: str,
) -> None:
    assert sources.authored_title(title) == ""
