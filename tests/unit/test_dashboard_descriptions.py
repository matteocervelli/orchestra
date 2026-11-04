"""Authored descriptions retain exact primary ownership and curation priority."""

from copy import deepcopy

import pytest

from orchestra.dashboard.curation import curate
from orchestra.dashboard.descriptions import recover_descriptions
from orchestra.dashboard.quality import findings
from orchestra.dashboard.text import fill_text

TITLE = "fix(runtime): accept employee execution package fields"
URL = "https://github.com/matteocervelli/nexus/pull/207"
BODY = (
    "## Problem\nEmployee execution packages discard `execution_id`.\n\n"
    "## Solution\nAccept `execution_id` and preserve package fields.\n"
)


def source(**changes):
    return {
        "number": 207,
        "url": URL,
        "title": TITLE,
        "repository": {"nameWithOwner": "matteocervelli/nexus", "name": "nexus"},
        "body": BODY,
        **changes,
    }


def item(**changes):
    return {
        "id": "opaque-card",
        "repo": "nexus",
        "pr": {"number": 207, "url": URL, "title": TITLE},
        "title": TITLE,
        "raw_title": TITLE,
        "problem": TITLE,
        "solution": TITLE,
        "needs": "",
        "status": "Integration",
        "children": [],
        **changes,
    }


def test_recover_primary_authored_sections_after_curate_with_bound_provenance():
    row, inputs = item(), [source()]
    original = deepcopy(inputs)
    fill_text(row, set(), False, source_prs=inputs)
    assert (
        row["problem"] == "Descrizione PR (testo dell'autore):\n"
        "Employee execution packages discard `execution_id`."
    )
    assert (
        row["solution"] == "Descrizione PR (testo dell'autore):\n"
        "Accept `execution_id` and preserve package fields."
    )
    assert row["description_provenance"]["problem"]["url"] == URL
    assert set(row["description_provenance"]["problem"]) == {
        "url",
        "field_sha256",
        "body_sha256",
    }
    assert inputs == original
    assert not {"problem", "solution"} & set(row["auto"])
    assert not {r["code"] for r in findings(row)} & {
        "missing_pr_description",
        "technical_title_as_detail",
    }


@pytest.mark.parametrize(
    "bad",
    [
        {"url": "https://github.com/matteocervelli/nexus/pull/208", "number": 208},
        {"url": "https://github.com/other/nexus/pull/207"},
        {"repository": {"nameWithOwner": "other/nexus", "name": "nexus"}},
        {"repository": {"nameWithOwner": "matteocervelli/nexus", "name": "atrium"}},
        {"repository": {}},
        {"body": ""},
        {"body": "Ordinary free text cannot become a description."},
        {"body": "## Problem\nwrong\n## Problem\nconflicting\n## Solution\nchange"},
        {"body": "## Problem\n" + "x" * 1201},
        {"body": "x" * 65537},
    ],
)
def test_missing_or_unqualified_evidence_yields_honest_placeholders(bad):
    row = item()
    fill_text(row, set(), False, source_prs=[source(**bad)])
    assert (
        row["problem"] == "Descrizione del problema non disponibile dalla PR primaria."
    )
    assert (
        row["solution"]
        == "Descrizione della soluzione non disponibile dalla PR primaria."
    )
    assert "description_provenance" not in row
    assert "missing_pr_description" in {r["code"] for r in findings(row)}


@pytest.mark.parametrize(
    "secret",
    [
        "user@example.test",
        "Authorization: Bearer secret-value",
        "API_KEY=secret-value",
        "ghp_" + "a" * 36,
        "-----BEGIN PRIVATE KEY-----",
        "password: secret-value",
        "<script>alert(1)</script>",
        "control\x00value",
        "bidi\u202evalue",
        "```py\nprint('text')\n```",
    ],
)
def test_sensitive_authored_candidate_is_rejected_without_raw_export(secret):
    row = item()
    fill_text(
        row,
        set(),
        False,
        source_prs=[source(body=f"## Problem\n{secret}\n## Solution\nvalid")],
    )
    assert secret not in str(row)
    assert "description_provenance" not in row


def test_conflicting_duplicate_source_bodies_or_heads_fail_closed():
    for sources in (
        [source(), source(body=BODY + "\nchanged")],
        [source(headRefOid="abc")],
        [
            source(),
            source(repository={"nameWithOwner": "other/nexus", "name": "nexus"}),
        ],
    ):
        row = item(pr={**item()["pr"], "headRefOid": "def"})
        fill_text(row, set(), False, source_prs=sources)
        assert "description_provenance" not in row


def test_solution_precedes_summary_and_fenced_headings_are_not_evidence():
    result = recover_descriptions(
        item(),
        [
            source(
                body="```md\n## Problem\nnot a heading\n```\n"
                "## Summary\nsummary\n## Solution\nchosen\n## Problem\nproblem"
            )
        ],
    )
    assert result is not None and result["solution"] == "chosen"
    assert result["problem"] == "problem"
    assert (
        recover_descriptions(
            item(), [source(body="```\n## Problem\nno\n## Solution\nno\n```")]
        )
        is None
    )


def test_curated_edited_and_meaningful_fields_remain_authoritative():
    for note in (
        {"problem": TITLE, "solution": TITLE},
        {"edited_fields": ["problem", "solution"], "problem": "", "solution": ""},
    ):
        row = item(pages={"pre": [], "post": [], "display": [], "mockup": []})
        curated, _ = curate(row, note, {})
        fill_text(row, curated, False, source_prs=[source()])
        assert "description_provenance" not in row
        if note.get("problem"):
            assert row["problem"] == TITLE == row["solution"]
            assert "technical_title_as_detail" in {r["code"] for r in findings(row)}
    row = item(
        problem="Exact meaningful existing problem", solution="Existing proposed change"
    )
    fill_text(row, set(), False, source_prs=[source()])
    assert row["problem"] == "Exact meaningful existing problem"
    assert row["solution"] == "Existing proposed change"


def test_partial_evidence_and_stale_provenance_do_not_follow_edited_field():
    row = item()
    fill_text(row, set(), False, source_prs=[source(body="## Problema\nproblema")])
    assert "problem" in row["description_provenance"]
    assert "solution" not in row["description_provenance"]
    row["problem"] = "Edited elsewhere"
    assert "stale_description_provenance" in {r["code"] for r in findings(row)}
    fill_text(row, {"problem"}, False, source_prs=[source()])
    assert "description_provenance" not in row


def test_nonpr_fallback_unchanged_and_quality_is_read_only():
    row = item(pr=None, problem="", solution="", status="Doing")
    fill_text(row, set(), False, source_prs=[source()])
    assert row["problem"] == row["title"]
    assert (
        row["solution"]
        == "In lavorazione: un agente ci sta lavorando, nessun risultato ancora."
    )
    row = item()
    before = deepcopy(row)
    assert "technical_title_as_detail" in {r["code"] for r in findings(row)}
    assert row == before


def test_actual_primary_head_sha_and_conflicting_duplicate_heads_fail_closed():
    row = item(pr={**item()["pr"], "head_sha": "primary-head"})
    fill_text(row, set(), False, source_prs=[source(headRefOid="other-head")])
    assert "description_provenance" not in row
    assert row["solution"].startswith("Descrizione della soluzione non disponibile")
    row = item()
    fill_text(
        row,
        set(),
        False,
        source_prs=[source(headRefOid="first"), source(headRefOid="second")],
    )
    assert "description_provenance" not in row
    assert row["solution"].startswith("Descrizione della soluzione non disponibile")


@pytest.mark.parametrize("invalid", ["invalid", ["invalid"], 1, {"problem": "invalid"}])
def test_malformed_provenance_is_reported_read_only_and_does_not_crash(invalid):
    from orchestra.dashboard.descriptions import valid_description_provenance

    row = item(description_provenance=invalid)
    before = deepcopy(row)
    assert valid_description_provenance(row, "problem") is False
    assert "stale_description_provenance" in {r["code"] for r in findings(row)}
    assert row == before


def test_unwired_sources_preserve_ordinary_exact_title_behavior():
    row = item()
    fill_text(row, set(), False)
    assert row["problem"] == row["solution"] == TITLE
    row = item()
    fill_text(row, set(), False, source_prs=[])
    assert (
        row["problem"] == "Descrizione del problema non disponibile dalla PR primaria."
    )


def test_blank_fields_without_evidence_keep_ordinary_execution_honest_fallback():
    row = item(problem="", solution="", status="Backlog", children=[{"exit": "0"}])
    fill_text(row, set(), False, source_prs=[])
    assert row["problem"] == row["title"]
    assert row["solution"].startswith("È già stata avviata un'esecuzione")
    row = item(problem="", solution="")
    fill_text(row, set(), False, source_prs=[source()])
    assert row["problem"].startswith("Descrizione PR (testo dell'autore):")


@pytest.mark.parametrize(
    "secret",
    [
        "SECRET_KEY: abc",
        "JWT_SECRET_KEY: abc",
        "secret_key=abc",
        "secret-key: abc",
        '"secret_key": "x"',
        "API_TOKEN:abc",
        "NPM_TOKEN: abc",
        "foo_token=abc",
        '"password": "x"',
        '"api_key": "x"',
        "'client_secret': 'x'",
        "DB_PASSWORD=x",
        "client_secret: x",
        "AWS_SECRET_ACCESS_KEY=x",
        "- API_TOKEN=abc",
        "`FOO_TOKEN=abc`",
        "run with FOO_TOKEN=abc",
        "Bearer xyz",
        "x-auth-token: private",
        "X-Api-Key: private",
        "accesskey: private",
        "some_PASSWORD: private",
        "some_SECRET: private",
    ],
)
def test_review_sensitive_prefixed_inline_and_bullet_forms_are_rejected(secret):
    row = item()
    fill_text(row, set(), False, source_prs=[source(body=f"## Solution\n{secret}")])
    assert secret not in str(row)
    assert "description_provenance" not in row


@pytest.mark.parametrize(
    "duplicate",
    [
        {"url": URL, "number": 208},
        {"url": URL, "number": "207"},
        {"url": URL, "number": None},
        {"url": "https://github.com/matteocervelli/nexus/pull/208", "number": 207},
    ],
)
def test_partially_matching_duplicate_identity_cannot_silently_lose(duplicate):
    assert recover_descriptions(item(), [source(), source(**duplicate)]) is None


def test_body_absent_duplicates_do_not_shadow_valid_body_but_conflicts_reject():
    absent = source()
    absent.pop("body")
    for missing in (absent, source(body=None)):
        assert recover_descriptions(item(), [source(), missing])["solution"]
    for conflicting in (source(body=""), source(body="## Solution\nOther")):
        assert recover_descriptions(item(), [source(), conflicting]) is None
    assert (
        recover_descriptions(
            item(),
            [source(), {**absent, "headRefOid": "new"}],
        )
        is not None
    )
    assert (
        recover_descriptions(
            item(pr={**item()["pr"], "head_sha": "old"}),
            [source(), {**absent, "headRefOid": "new"}],
        )
        is None
    )


@pytest.mark.parametrize("pr", ["invalid", ["invalid"], 1])
def test_invalid_primary_object_does_not_crash_readonly_content_findings(pr):
    row = item(pr=pr)
    before = deepcopy(row)
    findings(row)
    assert row == before
    from orchestra.dashboard.descriptions import fill_descriptions

    fill_descriptions(row, set(), [])
    assert "description_provenance" not in row


def test_single_technical_field_is_reported_and_empty_solution_is_authoritative():
    row = item(solution="Meaningful authored result")
    assert "technical_title_as_detail" in {r["code"] for r in findings(row)}
    result = recover_descriptions(
        item(), [source(body="## Summary\nSummary\n## Solution\n\n## Problem\nProblem")]
    )
    assert result is not None and "solution" not in result


@pytest.mark.parametrize("control", ["\x0b", "\x0c", "\x85", "\x1f"])
def test_control_line_separators_cannot_be_silently_stripped(control):
    assert (
        recover_descriptions(item(), [source(body=f"## Solution\n{control}value")])
        is None
    )


def test_long_unsupported_heading_is_bounded_without_backtracking():
    result = recover_descriptions(
        item(), [source(body="## x" + " " * 60000 + "y\n## Summary\nSpecific summary")]
    )
    assert result["solution"] == "Specific summary"


@pytest.mark.parametrize("text", ["token_expiry: 3600", "password-reset: handled"])
def test_credential_filter_does_not_match_arbitrary_keyword_suffixes(text):
    result = recover_descriptions(item(), [source(body=f"## Summary\n{text}")])
    assert result["solution"] == text
