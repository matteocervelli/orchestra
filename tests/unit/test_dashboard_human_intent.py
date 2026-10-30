"""Author information is scoped to selected text; emitted caller owns answers."""

from copy import deepcopy
from typing import Any

import pytest
from test_dashboard_real_card_quality_regressions import (
    quality_caller as quality_caller,
)

from orchestra.dashboard.curation import curate

REJECTIONS = (
    "RESPINTA DA MATTEO: candidata UI peggiorativa e non aderente al mockup. "
    "Non promuovere né proseguire questa proposta.",
    "RESPINTA: candidata UI non aderente al mockup. "
    "Review tecniche storiche restano prove, non approvazione funzionale.",
    "Matteo ha respinto la candidata UI. Richiesto riesame del prodotto verso "
    "mockup, senza nuova implementazione prima di verifica. Nessun GO release.",
)


def information(value: str) -> dict[str, str]:
    return {"kind": "information", "text": value}


@pytest.fixture
def intent_caller(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Any:
    finish, item, note, ctx = request.getfixturevalue("quality_caller")
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
    return finish, item, note, ctx


@pytest.mark.parametrize("needs", REJECTIONS)
def test_authored_information_does_not_become_an_approval(intent_caller, needs):
    finish, item, note, ctx = intent_caller
    note.update(needs=needs, needs_intent=information(needs))
    before = deepcopy(note)
    before_identity = deepcopy({key: item[key] for key in ("id", "aliases", "slugs")})

    finish(item, item["id"], ctx)

    assert item["needs"] == needs
    assert item["ask"] == [] and item["your_call"] is False
    assert item["serve_te"] is False and item["call_kind"] == ""
    assert item["status"] == "Backlog"
    assert {key: item[key] for key in before_identity} == before_identity
    assert note == before and "ask" not in note


@pytest.mark.parametrize(
    "marker",
    [
        None,
        "information",
        {},
        {"kind": "information"},
        {"kind": "information", "text": "Older rejection"},
        {"kind": "request", "text": "Quale pagina esaminare dopo il mockup respinto?"},
        {"kind": "other", "text": "Quale pagina esaminare dopo il mockup respinto?"},
    ],
)
def test_stale_or_invalid_information_keeps_new_needs(intent_caller, marker):
    finish, item, note, ctx = intent_caller
    question = "Quale pagina esaminare dopo il mockup respinto?"
    note.update(needs=question, needs_intent=marker)
    finish(item, item["id"], ctx)
    assert item["your_call"] is True
    assert item["ask"][0]["question"] == question
    assert item["ask"][0]["kind"] == "decide"


def test_unmarked_legacy_needs_remains_visible(intent_caller):
    finish, item, note, ctx = intent_caller
    note["needs"] = REJECTIONS[0]
    finish(item, item["id"], ctx)
    assert item["your_call"] is True
    assert item["ask"][0]["kind"] == "decide"


def test_information_does_not_hide_later_explicit_asks_and_owners(intent_caller):
    finish, item, note, ctx = intent_caller
    note.update(needs=REJECTIONS[0], needs_intent=information(REJECTIONS[0]))
    note["ask"] = [
        {
            "id": "old-choice",
            "question": "Quale proposta?",
            "kind": "decide",
            "_item": "synthetic-old-owner",
            "_answered": True,
        },
        {
            "id": "new-choice",
            "question": "Mockup respinto: quale pagina esaminare?",
            "rec": "Esaminare la pagina iniziale.",
            "_item": "synthetic-new-owner",
            "options": [{"value": "first", "label": "Prima pagina"}],
        },
        {"kind": "approve mockup", "link": "https://example.test/new-proposal"},
    ]
    before = deepcopy(note)
    finish(item, item["id"], ctx)
    assert len(item["ask"]) == 3 and item["your_call"] is True
    assert item["ask"][0]["_item"] == "synthetic-old-owner"
    assert item["ask"][0]["answered"] is True
    assert item["ask"][1]["_item"] == "synthetic-new-owner"
    assert item["ask"][1]["answered"] is False
    assert item["ask"][1]["kind"] == "decide"
    assert item["ask"][1]["options"] == [
        {"value": "first", "label": "Prima pagina", "recommended": False}
    ]
    assert item["ask"][2]["kind"] == "approve mockup"
    assert note == before


def test_information_preserves_decisions_and_recorded_answer(intent_caller):
    finish, item, note, ctx = intent_caller
    note.update(needs=REJECTIONS[0], needs_intent=information(REJECTIONS[0]))
    item["decisions"] = [
        {
            "id": "synthetic-decision",
            "title": "Quale seguito?",
            "rec": "Procedere con la verifica.",
            "link": "choice.html",
        }
    ]
    ctx.decisions = {"synthetic-decision": {"call": "action", "questions": []}}
    finish(item, item["id"], ctx)
    assert item["ask"][0]["id"] == "synthetic-decision"
    assert item["ask"][0]["kind"] == "action"
    assert item["ask"][0]["link"] == "choice.html"
    assert item["your_call"] is True
    # Exercise the existing alias-aware answer matcher, with no new matcher.
    from types import SimpleNamespace

    ctx.answered = [
        SimpleNamespace(
            decision=item["aliases"][0], questions=frozenset({"quale seguito"})
        )
    ]
    finish(item, item["id"], ctx)
    assert item["ask"][0]["answered"] is True and item["your_call"] is False


@pytest.mark.parametrize(
    "pin,edited,note_kind,card_kind,expected",
    [
        (False, False, "information", "request", "request"),
        (True, False, "information", "request", "information"),
        (False, True, "information", "request", "information"),
        (False, False, "request", "information", "information"),
        (True, False, "request", "information", "request"),
    ],
)
def test_intent_follows_the_source_that_supplied_needs(
    pin,
    edited,
    note_kind,
    card_kind,
    expected,
):
    value = "Stesso testo in due fonti."
    note = {
        "needs": value,
        "needs_intent": {"kind": note_kind, "text": value},
        "pin": pin,
        "edited_fields": ["needs"] if edited else [],
    }
    card = {"needs": value, "needs_intent": {"kind": card_kind, "text": value}}
    item = {"pages": {}}
    before = deepcopy((note, card))
    curate(item, note, card)
    assert item["needs_intent"]["kind"] == expected
    assert (note, card) == before
    # A winning source without metadata must not inherit the losing marker.
    (note if expected == note_kind and (pin or edited) else card).pop("needs_intent")
    curate(item, note, card)
    assert "needs_intent" not in item


@pytest.mark.parametrize(
    "question,rec,expected",
    [
        ("Approvi il mockup nuovo?", "Confermare il perimetro.", "approve mockup"),
        (
            "Il vecchio mockup è respinto. Approvi il nuovo mockup?",
            "",
            "approve mockup",
        ),
        ("Il mockup è respinto. Quale pagina esaminare?", "", "decide"),
        ("Quale pagina esaminare?", "Approvi il mockup nuovo?", "decide"),
        ("Non approvare il mockup.", "", "decide"),
        ("Il mockup non è approvato.", "", "decide"),
        ("Approviamo il mockup domani.", "", "decide"),
        ("Approvi il mockup?" + "x" * 2000, "", "decide"),
        ("Esito. " * 17 + "Approvi il mockup?", "", "decide"),
    ],
)
def test_emitted_classifier_uses_positive_question_not_recommendation(
    intent_caller,
    question,
    rec,
    expected,
):
    finish, item, note, ctx = intent_caller
    note["ask"] = [{"question": question, "rec": rec}]
    finish(item, item["id"], ctx)
    assert item["your_call"] is True
    assert item["ask"][0]["kind"] == expected


def test_metadata_does_not_project_unknown_payload():
    from orchestra.dashboard.text import clean_needs_intent

    value = "Informazione corrente."
    marker = {**information(value), "unknown_payload": {"sentinel": "not-public"}}
    note = {"needs": value, "needs_intent": marker}
    item = {"pages": {}}
    before = deepcopy(note)
    curate(item, note, {})
    assert "needs_intent" not in item and "not-public" not in repr(item)
    assert clean_needs_intent(marker) is None
    assert note == before


def test_same_note_can_ask_new_question_without_clearing_metadata(intent_caller):
    finish, item, note, ctx = intent_caller
    note.update(needs=REJECTIONS[0], needs_intent=information(REJECTIONS[0]))
    finish(item, item["id"], ctx)
    assert not item["your_call"]
    note["needs"] = "Quale pagina esaminare dopo il mockup respinto?"
    finish(item, item["id"], ctx)
    assert item["your_call"] and item["ask"][0]["question"] == note["needs"]


@pytest.mark.parametrize("signal", ["pr", "triage"])
def test_information_keeps_independently_grounded_gate(intent_caller, signal):
    finish, item, note, ctx = intent_caller
    note.update(needs=REJECTIONS[0], needs_intent=information(REJECTIONS[0]))
    if signal == "pr":
        item["pr"] = {"number": 7, "state": "open", "url": "https://example.test/pr/7"}
        item["labels"] = ["needs-human"]
        expected_kind = "approve merge"
    else:
        item["triage"] = {"verdict": "done?"}
        expected_kind = "decide"
    finish(item, item["id"], ctx)
    assert item["your_call"]
    assert item["ask"][0]["kind"] == expected_kind
    assert item["ask"][0]["question"] != REJECTIONS[0]
    assert item["needs"] == REJECTIONS[0]


@pytest.mark.parametrize(
    "marker",
    [
        {"kind": "information", "text": []},
        {"kind": ["information"], "text": "Esito corrente."},
        {"kind": "information", "text": " "},
        {"kind": "information", "text": "Esito corrente.", "extra": True},
    ],
)
def test_malformed_marker_never_hides_explicit_request(intent_caller, marker):
    finish, item, note, ctx = intent_caller
    note.update(
        needs="Esito corrente.",
        needs_intent=marker,
        ask={"question": "Approvi il nuovo mockup?", "kind": "decide"},
    )
    finish(item, item["id"], ctx)
    assert item["your_call"] and item["ask"][0]["kind"] == "decide"
