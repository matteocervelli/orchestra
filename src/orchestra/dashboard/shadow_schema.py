"""Fixed records at the approved M3S boundary; not inferred from input."""

from __future__ import annotations

from typing import Any

Schema = Any


def record(
    required: dict[str, Schema], optional: dict[str, Schema] | None = None
) -> Schema:
    return ("record", required, optional or {})


def seq(value: Schema) -> Schema:
    return ("list", value)


def mapping(key: Schema, value: Schema) -> Schema:
    return ("map", key, value)


def union(*values: Schema) -> Schema:
    return ("union", values)


TEXT = dict.fromkeys(("problem", "solution", "needs", "title", "kind", "title_it"), "T")
TEXT["repo"] = "S"
FORBIDDEN = frozenset(
    [
        "auth",
        "authorization",
        "auth_http_headers",
        "http_headers",
        "headers",
        "env",
        "environment",
        "token",
        "cookie",
        "password",
        "secret",
        "session_id",
        "native_session_id",
        "transcript",
        "rawsession",
        "jsonl",
        "stdout",
        "stderr",
    ]
)
PAGES = record(dict.fromkeys(("pre", "post", "mockup", "display"), seq("U")))
CARD_PAGES = record({}, {**PAGES[1], "preview": "U"})
OPTION = record({"value": "S64", "label": "T"}, {"recommended": "B"})
QUESTION = record({"id": "S", "text": "T"}, {"options": seq(OPTION), "multi": "B"})
ASK = record(
    {},
    {
        "id": "S",
        "_item": "ID",
        "_answered": "B",
        "answered": "B",
        "question": "T",
        "rec": "T",
        "link": "U",
        "kind": "S",
        "options": seq(OPTION),
        "multi": "B",
        "questions": seq(QUESTION),
    },
)
STEP = record(
    {"id": "StepID", "text": "T500"},
    {
        "cmd": "T1000",
        "link": "T500",
        "checked": "B",
    },
)
QPR = record(
    {
        "host": ("enum", ("github.com", "git.adlimen.dev")),
        "repo": "S",
        "number": "I+",
        "url": "U",
    }
)
SUBJECT = union(
    record({"repo": "S", "artifact": "T500"}), record({"repo": "S", "pr": QPR})
)
RAW_PROVENANCE = {
    "kind": ("enum", ("local_artifact_review", "primary_integration")),
    "subject": SUBJECT,
    "relation": ("enum", ("primary", "dependency")),
}
PROVENANCE = union(
    record(RAW_PROVENANCE),
    record(
        {
            **RAW_PROVENANCE,
            "source": ("enum", ("curated_note", "task_contract", "child_report")),
            "validation": ("enum", ("validated", "unverified")),
        }
    ),
    record(
        {
            "kind": ("enum", ("unknown",)),
            "validation": ("enum", ("unverified", "conflict")),
            "source": ("enum", ("unverified",)),
        }
    ),
)
REVIEW = record(
    {"verdict": "S", "finding": "T", "mtime": "N0", "file": "S", "reviewer": "S"}
)
PR = record(
    {"number": "I+", "url": "U"},
    {
        **dict.fromkeys(("state", "head_sha", "closed", "branch", "host", "repo"), "S"),
        "title": "T",
        "review": ("nullable", REVIEW),
    },
)
ISSUE = record({"number": "I+", "url": "U"}, {"host": "S", "repo": "S"})
PROPOSAL = record({"id": "ID"}, {"title": "T", "kind": "S", "link": "U", "status": "S"})
CARD = record(
    {},
    {
        **TEXT,
        "repos": seq("S"),
        "pages": CARD_PAGES,
        "preview": "U",
        "ask": union(ASK, seq(ASK)),
        "steps": seq(STEP),
        "work_provenance": PROVENANCE,
    },
)
CHILD = record(
    {
        "slug": "ID",
        "tool": "S",
        "model": "S",
        "running": "B",
        "duration": "I",
        "idle": "I",
        "exit": "S?",
        "cost": "N0?",
        "start": "TS",
        "end": "TS",
        "outcome": "T",
        "report": "OSTR",
        "card": ("nullable", CARD),
        "repo_refs": seq("S"),
    }
)
CHILD_SUMMARY = record(
    {
        "slug": "ID",
        "tool": "S",
        "model": "S",
        "duration": "I",
        "cost": "N0?",
        "running": "B",
    }
)
RUN = record(
    {
        "slug": "ID",
        "tool": "S",
        "model": "S",
        "effort": "S",
        "liveness": "S",
        "running": "B",
        "exit": "S?",
        "start": "N0",
        "end": "N0?",
        "duration": "I",
        "idle": "I",
        "cost": "N0?",
        "final": "OSTR",
        "last": "OSTR",
    }
)
TASK = record(
    {
        "slug": "ID",
        "goal": "T",
        "header": "T",
        "text": "T",
        "work_provenance": ("nullable", PROVENANCE),
        "provenance_errors": seq("S"),
        "mtime": "N0",
    }
)
SPAWN = record(
    {"slug": "ID"},
    {"tool": "S", "model": "S", "effort": "S", "start": "N0", "workdir": "OSTR"},
)
LEDGER = record(
    {"slug": "ID"},
    {
        "outcome": "T?",
        "gates": "T?",
        "note": "T?",
        "cost_usd": "N0?",
        "ts": "TS",
        "exit": "S?",
        "duration": "N0",
    },
)
OUTCOME = record({"slug": "ID", "outcome": "T?", "gates": "T?", "note": "T?"})
DECISION = record(
    {"id": "ID"},
    {
        "title": "T",
        "link": "U",
        "kind": "S",
        "status": "S",
        "repo": "S",
        "questions": seq(QUESTION),
        "ts": "TS",
    },
)
QUEUE = record(
    {"item": "ID"},
    {
        "lane": "S",
        "state": "S",
        "repo": "S",
        "kind": "S",
        "goal": "T",
        "ts": "TS",
        "parent": "ID",
        "priority": "Priority",
    },
)
TRIAGE_RAW = record(
    {"repo": "S", "number": "I+"},
    {
        "title": "T",
        "verdict": "T?",
        "size": "T?",
        "why": "T?",
        "test": "T?",
        "score": "N?",
    },
)
TRIAGE = record(
    {"verdict": "T?", "size": "T?", "why": "T?", "test": "T?", "score": "N?"}
)
NOTE = record(
    {},
    {
        **TEXT,
        **dict.fromkeys(("pin", "hide", "pages_exact", "ui", "mockup_approved"), "B"),
        **dict.fromkeys(("status", "blocked", "dropped", "branch", "approval"), "T"),
        "edited_fields": seq(("enum", tuple(TEXT))),
        "priority": "Priority",
        "order": "Order",
        "repos": seq("S"),
        "pages": CARD_PAGES,
        "preview": "U",
        "ask": union(ASK, seq(ASK)),
        "steps": seq(STEP),
        "steps_checked": mapping("StepID", "B"),
        "step_aliases": mapping("S", "StepID"),
        "step_checks": mapping("ID", mapping("StepID", "B")),
        "ask_overrides": seq("ID"),
        "step_overrides": seq("ID"),
        "proposals": seq(PROPOSAL),
        "work_provenance": PROVENANCE,
        "merged_into": "ID",
        "detach_prs": seq("U"),
        "issue": union("I+", ("nullable", ISSUE)),
        "pr": union("I+", ("nullable", PR)),
        "review": ("nullable", REVIEW),
        "answers": mapping("ID", "B"),
    },
)
ITEM = record(
    {
        "id": "ID",
        **dict.fromkeys(
            (
                "repo",
                "kind",
                "title",
                "branch",
                "status",
                "problem",
                "solution",
                "needs",
                "evidence",
            ),
            "T",
        ),
        "issue": ("nullable", ISSUE),
        "pr": ("nullable", PR),
        "pages": PAGES,
        "review": ("nullable", REVIEW),
        "child": ("nullable", CHILD_SUMMARY),
        "children": seq(CHILD),
        "slugs": seq("ID"),
        "labels": seq("S"),
        "updated": "TS",
        "source": seq("S"),
    },
    {
        "goal": "T",
        "_reftext": seq("T"),
        "prs": seq(PR),
        "reviews": seq(REVIEW),
        "outcomes": seq(OUTCOME),
        "decisions": seq(DECISION),
        "queue": QUEUE,
        "triage": TRIAGE,
        "aliases": seq("ID"),
        "_deduped": "B",
        "_note_aliases": seq("ID"),
        "_ask_overrides": seq("ID"),
        "ask": seq(ASK),
        "steps": seq(STEP),
        "approval": "T",
        "pin": "B",
        "hide": "B",
        "priority": "Priority",
        "answers": mapping("ID", "B"),
        "work_provenance": PROVENANCE,
    },
)
REPOSITORY = record({"name": "S"}, {"owner": record({"login": "S"})})
CLOSING_ISSUE = record({"number": "I+"}, {"url": "U", "repository": REPOSITORY})
META_FIELDS = {
    **dict.fromkeys(
        (
            "headRefName",
            "baseRefName",
            "headRefOid",
            "mergedAt",
            "closedAt",
            "updatedAt",
        ),
        "S?",
    ),
    "body": "T",
    "labels": seq(record({"name": "S"})),
    "closingIssuesReferences": seq(CLOSING_ISSUE),
    "mergeCommit": ("nullable", record({"oid": "SHA40"})),
    "reviewDecision": "S?",
    "mergeable": "S?",
}
RAW_PR = record(
    {"repository": REPOSITORY, "number": "I+", "url": "U", "state": "S", "title": "T"},
    META_FIELDS,
)
PR_META = record(
    {"number": "I+"},
    {
        **{k: v for k, v in META_FIELDS.items() if k not in {"body", "labels"}},
        "state": "S?",
        "title": "T?",
    },
)
REF = ("tuple", ("S", "I+"))
ASSEMBLY = {
    "items": mapping("ID", ITEM),
    "spawns": mapping("ID", SPAWN),
    "led": mapping("ID", LEDGER),
    "probes": "Probe",
    "pr_by": mapping(REF, RAW_PR),
    "produced": mapping(REF, "ID"),
}
CTX = {
    "pages": seq("U"),
    "triage": mapping(REF, TRIAGE_RAW),
    "notes": mapping("ID", NOTE),
    "probes": "Probe",
    "now": "N0",
    "decisions": mapping("ID", DECISION),
    "ledger": mapping("ID", seq(LEDGER)),
    "answered": seq("AnswerRec"),
    "acted": ("set", "ID"),
    "issue_prio": mapping("U", "Priority"),
    "html": mapping("U", "OSTR"),
    "previews": mapping("ID", "U"),
    "number_repos": mapping("S", ("set", "S")),
    "tasks": mapping("ID", TASK),
    "spawns": mapping("ID", SPAWN),
}
LOCALS = {
    "spawns": ASSEMBLY["spawns"],
    "tk": CTX["tasks"],
    "ordinary_tasks": CTX["tasks"],
    "runs": mapping("ID", RUN),
    "ledger": seq(LEDGER),
    "led": ASSEMBLY["led"],
    "by_slug": CTX["ledger"],
    "decisions": seq(DECISION),
    "triage": CTX["triage"],
    "all_prs": seq(RAW_PR),
    "revs": mapping(REF, REVIEW),
    "probes": "Probe",
}
PROBE_FIELDS = {
    "cache": "OPATH",
    "budget": "I0",
    "now": "N0",
    "calls": ("counter", "CounterKey"),
    "_memo": "Memo",
    "_anc_file": "OPATH",
    "_anc": mapping("S", "B"),
    "_anc_dirty": "B",
}
ROOT_FIELDS = {
    "asm": "Assembly",
    "ctx": "Ctx",
    "locals": record(LOCALS),
    "original_notes": CTX["notes"],
    "return_notes": ("nullable", CTX["notes"]),
    "tasks": CTX["tasks"],
    "globals": "Globals",
}
