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


def test_fallback_titles_describe_reference_and_work_kind() -> None:
    from orchestra.dashboard.text import fallback_title

    base = {"id": "candidate", "repo": "orchestra", "pr": None, "issue": None}
    cases = [
        (
            {
                **base,
                "id": "review-candidate",
                "repos": ["app-ratio", "nexus"],
                "pr": {"number": 17},
            },
            "",
            "Ratio · Nexus · Revisione indipendente · PR #17",
        ),
        (
            {**base, "id": "candidate-fix2", "repo": "atrium", "issue": {"number": 12}},
            "",
            "Atrium · Correzione dopo la revisione · Issue #12",
        ),
        (base, "feat(scope): add a feature", "Orchestra · nuova funzione"),
        (base, "plain English heading", "Orchestra · lavoro"),
        ({**base, "pr": {"number": 5}}, "", "Orchestra · PR #5"),
    ]
    for row, raw, expected in cases:
        assert fallback_title(row, raw) == expected


def test_missing_text_keeps_execution_blocking_and_human_followup_distinct() -> None:
    from orchestra.dashboard.text import SERVE_NEEDS

    finished = {**item(), "status": "Backlog", "children": [{"exit": "0"}]}
    fill_text(finished, set(), False)
    assert finished["solution"].startswith("È già stata avviata un'esecuzione;")
    assert "verificarne esito e seguito" in finished["solution"]
    blocked = {**item(), "blocked": "verifica CI"}
    fill_text(blocked, set(), False)
    assert blocked["needs"] == "Niente per ora: è bloccata (verifica CI)."
    assert "needs" not in blocked["auto"]
    human = item()
    fill_text(human, set(), True)
    assert human["needs"] == SERVE_NEEDS and "needs" in human["auto"]
    fallback = {**item(), "title_it": "Orchestra · lavoro", "raw_title": "fix: repair"}
    fill_text(fallback, set(), False)
    assert fallback["title"] == "Orchestra · correzione"
    assert "title_it" in fallback["auto"]


def test_options_reject_bad_reserved_and_duplicate_values_and_bound_choices() -> None:
    from orchestra.dashboard.text import clean_options

    assert clean_options({"value": "a", "label": "Wrong container"}) == []
    bad = [
        None,
        {"value": [], "label": "Bad type"},
        {"value": "other", "label": "Reserved"},
        {"value": "bad value", "label": "Invalid"},
        {"value": "blank", "label": " "},
    ]
    options = clean_options(
        [
            *bad,
            {"value": "a", "label": "  Option A  ", "recommended": True},
            {"value": "a", "label": "Duplicate"},
            {"value": "b", "label": "L" * 220, "recommended": "yes"},
        ]
    )
    assert options == [
        {"value": "a", "label": "Option A", "recommended": True},
        {"value": "b", "label": "L" * 200, "recommended": False},
    ]
    assert (
        len(
            clean_options(
                [{"value": str(i), "label": f"Choice {i}"} for i in range(30)]
            )
        )
        == 24
    )


def test_ask_precedence_preserves_explicit_choices_and_separates_advice() -> None:
    from orchestra.dashboard.text import ask_of

    row = {
        **item(),
        "pr": {"url": "https://example.test/pr/1"},
        "issue": None,
        "needs": "Scegliere il seguito.",
        "decisions": [
            {
                "id": "decision-1",
                "title": "Quale percorso?",
                "rec": "Percorso A.",
                "link": "decision.html",
            }
        ],
    }
    override = {
        "id": "explicit",
        "question": "Quale opzione? Consiglio: Procedere con A.",
        "options": [{"value": "a", "label": "A"}],
        "multi": True,
    }
    asks = ask_of(row, override)
    assert asks[0]["id"] == "explicit"
    assert asks[0]["question"] == "Quale opzione?"
    assert asks[0]["rec"] == "Procedere con A."
    assert asks[0]["multi"] is True and asks[0]["options"][0]["value"] == "a"
    assert ask_of(row, []) == []
    assert ask_of(row)[0]["id"] == "decision-1"
    no_decision = {**row, "decisions": []}
    assert ask_of(no_decision)[0]["link"] == "https://example.test/pr/1"
    assert ask_of({**no_decision, "needs": "Niente per ora."}) == []


def test_needs_and_links_come_from_the_declared_source() -> None:
    from orchestra.dashboard.text import ask_link, needs_of

    row = {
        "pr": {"url": "pr.html", "state": "open"},
        "issue": {"url": "issue.html"},
        "labels": ["needs-human"],
        "decisions": [
            {"id": "m1", "title": "Scegliere il seguito", "rec": "Procedere con A"}
        ],
    }
    assert ask_link(row) == "pr.html"
    assert "Mail m1:" in needs_of(row) and "PR etichettata needs-human" in needs_of(row)
    issue = {**row, "pr": None, "decisions": [], "triage": {"verdict": "done?"}}
    assert ask_link(issue) == "issue.html"
    assert needs_of(issue) == "Conferma che è già risolta e chiudi la issue."
    assert ask_link({"pr": None, "issue": None}) == ""


def test_structural_text_errors_and_uncurated_queue_remain_separate() -> None:
    from orchestra.dashboard.text import uncurated_open, validate

    bad = {
        "id": "missing",
        "title": "",
        "problem": "",
        "solution": "Present",
        "needs": "Present",
        "status": "Unknown",
        "your_call": True,
        "ask": [],
    }
    human = {
        "id": "question",
        "title": "Present",
        "problem": "Present",
        "solution": "Present",
        "needs": "Present",
        "status": "Doing",
        "serve_te": True,
        "ask": [{"question": "", "rec": ""}],
    }
    assert validate({"items": [bad, human]}) == [
        "missing: empty title",
        "missing: empty problem",
        "missing: unknown status 'Unknown'",
        "missing: your_call without ask",
        "question: ask without question",
        "question: ask without rec",
    ]
    queued = [
        {"id": "open", "status": "Doing", "auto": ["title_it"]},
        {"id": "closed", "status": "Main", "auto": ["title_it"]},
        {"id": "curated", "status": "Doing", "auto": []},
    ]
    assert uncurated_open({"items": queued}) == [queued[0]]
