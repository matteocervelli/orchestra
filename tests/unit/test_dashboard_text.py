from typing import Any

from orchestra.dashboard.curation import curate
from orchestra.dashboard.text import fill_text


def item() -> dict[str, Any]:
    return {
        "id": "sample",
        "repo": "orchestra",
        "title": "Raw title",
        "raw_title": "Raw title",
        "title_it": "Correggere i titoli delle card",
        "problem": "",
        "solution": "",
        "needs": "",
        "status": "Doing",
        "pages": {"pre": [], "post": [], "display": [], "mockup": []},
    }


def test_meaningful_uncurated_title_survives() -> None:
    row = item()
    fill_text(row, set(), False)
    assert row["title"] == "Correggere i titoli delle card"
    assert "title_it" not in row["auto"]


def test_unpinned_note_title_beats_card_title_it() -> None:
    row = item()
    curated, _ = curate(
        row,
        {"title": "Rivedere le richieste indipendenti"},
        {"title_it": "Cambiare il titolo della card"},
    )
    fill_text(row, curated, False)
    assert row["title"] == "Rivedere le richieste indipendenti"


def test_both_curated_title_keys_win_without_requiring_pin() -> None:
    from copy import deepcopy

    for pin in (False, True):
        for note in (
            {"title_it": "Titolo italiano già curato"},
            {"title": "Titolo originale già curato"},
            {
                "title": "Titolo originale già curato",
                "title_it": "Titolo italiano già curato",
            },
        ):
            note = {
                **note,
                "pin": pin,
                "approval": "approved",
                "ask": [{"id": "independent"}],
            }
            before = deepcopy(note)
            row = item()
            curated, _ = curate(
                row, note, {"title_it": "Cambiare il titolo della card"}
            )
            fill_text(row, curated, False)
            assert row["title"] == note.get("title_it", note.get("title"))
            assert "title_it" not in row["auto"]
            assert note == before


def test_edited_fields_win_only_when_explicit_and_present_in_note() -> None:
    from copy import deepcopy

    note = {
        "edited_fields": ["needs", "problem", "solution", "repo"],
        "needs": "Orchestra verifica il seguito tecnico #1564.",
        "problem": "Perimetro Studio e Azienda già approvato.",
        "solution": "Resta da verificare il risultato operativo.",
        "pin": False,
        "status": "Doing",
        "ask": [{"id": "only-q3"}],
    }
    card = {
        "needs": "Rispondere alle vecchie domande di staging.",
        "problem": "Matteo deve scegliere un nuovo perimetro.",
        "solution": "Serve ancora approvare la proposta.",
        "kind": "docs",
        "repo": "nexus",
    }
    original = deepcopy(note)
    row = {**item(), "status": "Doing", "ask": [{"id": "only-q3"}]}
    curated, _ = curate(row, note, card)
    fill_text(row, curated, False)
    assert row["needs"] == note["needs"]
    assert row["problem"] == note["problem"]
    assert row["solution"] == note["solution"]
    assert row["kind"] == card["kind"]
    # repo was listed as edited, but absent from note: do not invent an override.
    assert row["repo"] == card["repo"]
    assert row["status"] == "Doing" and row["ask"] == [{"id": "only-q3"}]
    assert note == original


def test_explicit_edited_blank_uses_existing_fallback_without_old_child_text() -> None:
    row = item()
    curated, _ = curate(
        row,
        {"edited_fields": ["needs"], "needs": ""},
        {"needs": "Matteo deve rispondere alle vecchie tre domande."},
    )
    assert row["needs"] == ""
    fill_text(row, curated, False)
    assert row["needs"] == "Niente per ora: un agente ci sta lavorando."
