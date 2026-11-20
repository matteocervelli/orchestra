"""Selected pinned SOURCE bodies in synthetic namespaces; no module readers run."""

from __future__ import annotations
import __future__

import copy
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

from orchestra.dashboard import common, curation, text

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/dashboard-shadow-donors.json"


def load_sources() -> dict[str, dict[str, Any]]:
    data = json.loads(FIXTURE.read_text())
    common_globals = {
        "copy": copy,
        "hashlib": hashlib,
        "json": json,
        "re": re,
        "Counter": Counter,
        "dataclass": dataclass,
        "field": field,
        "datetime": datetime,
        "timezone": __import__("datetime").timezone,
        "Path": Path,
        "FULL": common.FULL,
        "REPOS": common.REPOS,
        "STATUSES": common.STATUSES,
        "CLOSED": common.CLOSED,
        "short_repo": common.short_repo,
        "refs": common.refs,
        "is_nothing": text.is_nothing,
        "STEP_RE": re.compile(r"^[A-Za-z0-9_-]{1,40}$"),
        "_DETACHED": set(),
        "REPO_GIT": {
            key: (
                "synthetic-clone-" + key,
                "github" if key == "adlimenui" else "origin",
            )
            for key in (
                "ratio",
                "himalaia",
                "atrium",
                "nexus",
                "adlimenui",
                "adlimen-infra",
                "adlimen-cicd",
                "limen-assistant",
                "orchestra",
                "dotfiles",
            )
        },
        "FORGEJO_REPO": {
            "atrium": "matteocervelli/atrium",
            "nexus": "matteocervelli/nexus",
        },
    }
    result = {}
    for name in (
        "wi_common",
        "wi_identity",
        "wi_sources",
        "wi_probes",
        "wi_assembly",
        "wi_status",
        "wi_dedupe",
        "wi_fields",
        "workitems",
    ):
        namespace = {**common_globals, "__name__": name}
        if name == "wi_assembly":
            namespace["explicit_refs"] = result["wi_identity"]["explicit_refs"]
        if name == "wi_dedupe":
            namespace.update(
                {
                    "groups": result["wi_identity"]["groups"],
                    "issue_ref": result["wi_assembly"]["issue_ref"],
                    "compute": result["wi_status"]["compute"],
                    "clean_steps": result["wi_sources"]["clean_steps"],
                }
            )
        namespace.update(
            {
                key: value
                for key, value in result.get("wi_common", {}).items()
                if key in {"clip", "iso"}
            }
        )
        # No top-level import/readers or __init__ of Probes are in this AST slice.
        code = compile(
            data["modules"][name]["code"],
            name + ".py",
            "exec",
            flags=__future__.annotations.compiler_flag,
        )
        if name in {"workitems", "wi_fields"}:
            temporary = ModuleType(name)
            previous = sys.modules.get(name)
            sys.modules[name] = temporary
            try:
                temporary.__dict__.update(namespace)
                exec(code, temporary.__dict__)
                namespace = temporary.__dict__
            finally:
                if previous is None:
                    sys.modules.pop(name)
                else:
                    sys.modules[name] = previous
        else:
            exec(code, namespace)
        result[name] = namespace
    return result


def boundary(reports: tuple[str, str] | None = None) -> dict[str, Any]:
    source = load_sources()
    Probe = source["wi_probes"]["Probes"]
    probe = object.__new__(Probe)
    probe.cache, probe._anc_file = Path("synthetic-cache"), Path("synthetic-ancestry")
    probe.budget, probe.now, probe.calls = 0, 1.0, Counter()
    probe._memo, probe._anc, probe._anc_dirty = {}, {}, False
    tasks = {
        slug: {
            "slug": slug,
            "goal": "synthetic",
            "header": "synthetic",
            "text": "synthetic",
            "work_provenance": None,
            "provenance_errors": [],
            "mtime": 1.0,
        }
        for slug in ("synthetic", "synthetic-review")
    }
    notes = {
        slug: {
            "steps": [{"id": "check", "text": "synthetic"}],
            "steps_checked": {"check": True},
            "ask": [
                {
                    "id": "ask",
                    "question": "synthetic?",
                    "options": [{"value": "yes", "label": "Yes"}],
                }
            ],
        }
        for slug in tasks
    }
    asm = source["wi_assembly"]["Assembly"]({}, {}, [], probe)
    item = source["wi_assembly"]["new_item"]("synthetic")
    item.update(repo="atrium", slugs=list(tasks), source=["task"], prs=[], reviews=[])
    reports = reports or ("synthetic opaque alpha", "synthetic opaque beta")
    item["children"] = [
        {
            "slug": "synthetic",
            "tool": "synthetic",
            "model": "synthetic",
            "running": False,
            "duration": 1,
            "idle": 0,
            "exit": "0",
            "cost": 1.0,
            "start": "",
            "end": "",
            "outcome": "synthetic",
            "report": report,
            "card": {"steps": [{"id": "child-check", "text": "synthetic child step"}]},
            "repo_refs": [],
        }
        for report in reports
    ]
    asm.items = {"synthetic": item}
    Ctx = source["workitems"]["Ctx"]
    # Ctx is populated field by field; no reader or producer build is imported.
    ctx = object.__new__(Ctx)
    values = {
        "pages": [],
        "triage": {},
        "notes": notes,
        "probes": probe,
        "now": 1.0,
        "decisions": {},
        "ledger": {},
        "answered": [],
        "acted": set(),
        "issue_prio": {},
        "html": {},
        "previews": {},
        "number_repos": {},
        "tasks": tasks,
        "spawns": asm.spawns,
    }
    for key, value in values.items():
        object.__setattr__(ctx, key, value)
    local = {
        "spawns": asm.spawns,
        "tk": tasks,
        "ordinary_tasks": tasks,
        "runs": {},
        "ledger": [],
        "led": asm.led,
        "by_slug": ctx.ledger,
        "decisions": [],
        "triage": ctx.triage,
        "all_prs": [],
        "revs": {},
        "probes": probe,
    }
    return {
        "source": source,
        "asm": asm,
        "ctx": ctx,
        "locals": local,
        "notes": notes,
        "tasks": tasks,
        "baseline": source["wi_dedupe"]["collapse"],
        "candidate": curation.collapse,
        "callbacks": {
            key: source["wi_dedupe"][key]
            for key in ("compute", "effective_note", "issue_ref")
        },
    }
