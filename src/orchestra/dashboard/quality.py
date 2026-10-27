"""Read-only card readiness audit; no guesses about approvals or delivery status.

Run ``python3 bin/wi_quality.py`` to check the published board. Exit 1 means
human-facing cards require curation. The generator emits the same report on refresh.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .provenance import local_review, qualified_pr
from .titles import generic_title

PENDING = frozenset({"PR review", "PR fix", "Merge", "Integration", "Main"})
GENERIC_QUESTION = "guarda il dettaglio e decidi come procedere"


def _norm(value: object) -> str:
    return str(value or "").strip().rstrip(".! ").casefold()


def findings(item: dict[Any, Any]) -> list[dict[Any, Any]]:
    """Report deficits without changing asks, answers, states or visibility."""
    rows: list[dict[Any, Any]] = []

    def add(code: str, message: str, severity: str = "warning") -> None:
        if not any(row["code"] == code for row in rows):
            rows.append({"code": code, "severity": severity, "message": message})

    human = bool(item.get("your_call"))
    severity = "error" if human else "warning"
    if "title_it" in (item.get("auto") or []) or generic_title(
        str(item.get("title") or "")
    ):
        add(
            "generic_title",
            "Titolo da curare con oggetto e risultato specifici.",
            severity,
        )
    asks = [
        a
        for a in item.get("ask") or []
        if isinstance(a, dict) and (not a.get("answered"))
    ]
    ask_ids = Counter(
        a["id"] for a in asks if isinstance(a.get("id"), str) and a["id"].strip()
    )
    if any(count > 1 for count in ask_ids.values()):
        add(
            "duplicate_ask_id",
            (
                "Domande aperte con lo stesso identificatore: "
                "preservare e distinguere le richieste."
            ),
            severity,
        )
    if human and (not asks):
        add("missing_question", "Richiesta a Matteo senza una domanda aperta.", "error")
    if human:
        for ask in asks:
            question, rec = (_norm(ask.get("question")), _norm(ask.get("rec")))
            if not question or GENERIC_QUESTION in question:
                add(
                    "generic_question",
                    "Recuperare la domanda concreta dalle fonti.",
                    "error",
                )
            if not rec or rec.startswith("nessuno, scegli tu:"):
                add(
                    "missing_recommendation",
                    "Manca una raccomandazione motivata o un limite esplicito.",
                    "error",
                )
            if question.startswith("orchestra:"):
                add(
                    "technical_question",
                    "Il testo assegna lavoro a Orchestra, non una decisione a Matteo.",
                    "error",
                )
            if ask.get("kind") in ("approve UI", "approve mockup"):
                pages = item.get("pages") or {}
                if not any(pages.get(k) for k in ("display", "mockup", "post")):
                    add(
                        "missing_visual_evidence",
                        "Approvazione visiva priva di una proposta collegata.",
                        "error",
                    )
    children = item.get("children") or []
    if any(
        c.get("end") or c.get("exit") is not None
        for c in children
        if isinstance(c, dict)
    ) and "nessun agente l'ha ancora presa" in str(item.get("solution") or ""):
        add(
            "execution_contradiction",
            "Una esecuzione esiste: non descrivere il lavoro come mai iniziato.",
            severity,
        )
    if item.get("status") in PENDING:
        if not qualified_pr(
            item.get("pr"), str(item.get("repo") or "")
        ) and not local_review(item):
            add(
                "pipeline_without_pr",
                (
                    "Stato avanzato senza richiesta di integrazione prima"
                    "ria: verificare la provenienza."
                ),
            )
        if (
            item.get("status") in ("Integration", "Main")
            and _norm(item.get("needs")) == "niente: già fatto"
        ):
            add(
                "integration_not_delivery",
                "Integrazione o main non dimostrano rilascio e verifica operativa.",
            )
    if (item.get("work_provenance") or {}).get("validation") == "conflict":
        add(
            "conflicting_work_provenance",
            "La provenienza richiede verifica delle fonti.",
        )
    return rows


def audit(
    data: dict[Any, Any], *, board_url: str = "/orchestra/board?item="
) -> dict[Any, Any]:
    items = [item for item in data.get("items", []) if isinstance(item, dict)]
    affected = []
    for item in items:
        issues = findings(item)
        if issues:
            affected.append(
                {
                    "id": item["id"],
                    "repo": item.get("repo"),
                    "title": item.get("title"),
                    "status": item.get("status"),
                    "your_call": bool(item.get("your_call")),
                    "issues": issues,
                    "atrium": board_url + item["id"],
                    "owner": "orchestra",
                    "next_action": (
                        "Curare e verificare le fonti prima di chiedere una decisione."
                    ),
                }
            )
    errors = sum(
        row["your_call"] and any(f["severity"] == "error" for f in row["issues"])
        for row in affected
    )
    return {
        "coverage": {"structure": "checked", "semantic_freshness": "not_verified"},
        "generated": data.get("generated"),
        "summary": {
            "cards_checked": len(items),
            "human_cards_checked": sum(bool(i.get("your_call")) for i in items),
            "human_cards_with_errors": errors,
            "cards_with_findings": len(affected),
            "findings_by_code": dict(
                Counter(f["code"] for row in affected for f in row["issues"])
            ),
        },
        "items": affected,
    }


def publication_generated(
    previous: object = None, *, now: datetime | None = None
) -> str:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("publication_time_timezone")
    current = current.astimezone(UTC)
    if isinstance(previous, str):
        try:
            old = datetime.fromisoformat(previous.replace("Z", "+00:00"))
        except ValueError:
            old = None
        if old and old.tzinfo:
            old = old.astimezone(UTC)
            if current <= old:
                current = old + timedelta(microseconds=1)
    return current.isoformat(timespec="microseconds").replace("+00:00", "Z")


def board_digest(board: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            board,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def bind_detail(
    item: dict[str, Any], board: dict[str, Any], *, snapshot_digest: str | None = None
) -> dict[str, Any]:
    generated = board.get("generated")
    if not isinstance(generated, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", generated
    ):
        raise ValueError("publication_generated")
    return {
        **item,
        "_producer_snapshot": {
            "version": 1,
            "item_id": item["id"],
            "generated": generated,
            "board_sha256": snapshot_digest or board_digest(board),
        },
    }


def detail_matches_board(
    row: dict[str, Any],
    board: dict[str, Any],
    item_id: str,
    *,
    snapshot_digest: str | None = None,
) -> bool:
    stamp = row.get("_producer_snapshot")
    generated = board.get("generated")
    return bool(
        isinstance(stamp, dict)
        and type(stamp.get("version")) is int
        and stamp["version"] == 1
        and row.get("id") == item_id
        and stamp.get("item_id") == item_id
        and isinstance(generated, str)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", generated)
        and stamp.get("generated") == generated
        and stamp.get("board_sha256") == (snapshot_digest or board_digest(board))
    )


def load_board(path: Path) -> dict[Any, Any]:
    data = json.loads(path.read_text())
    details = path.parent / "work-items-detail"
    enriched = []
    snapshot_digest = board_digest(data)
    for item in data.get("items", []):
        iid = item.get("id", "")
        if (
            not iid
            or any(
                c
                not in (
                    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
                )
                for c in iid
            )
            or iid in (".", "..")
        ):
            enriched.append(item)
            continue
        detail = details / f"{iid}.json"
        try:
            row = json.loads(detail.read_text())
        except (OSError, ValueError):
            row = {}
        if not isinstance(row, dict) or not detail_matches_board(
            row, data, str(iid), snapshot_digest=snapshot_digest
        ):
            row = {}
        combined = {**row, **item}
        combined["your_call"] = bool(item.get("your_call"))
        combined["ask"] = item.get("ask") or []
        if row.get("children") and all(
            set(c) <= {"slug"} for c in item.get("children", [])
        ):
            combined["children"] = row["children"]
        enriched.append(combined)
    return {**data, "items": enriched}


def main(
    argv: Sequence[str] | None = None,
    *,
    default_path: Path | None = None,
    board_url: str = "/orchestra/board?item=",
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", nargs="?", type=Path, default=default_path)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete audit instead of its summary",
    )
    args = parser.parse_args(argv)
    if args.path is None:
        parser.error("an explicit board path is required")
    report = audit(load_board(args.path), board_url=board_url)
    print(
        json.dumps(
            report if args.json else report["summary"], ensure_ascii=False, indent=2
        )
    )
    return 1 if report["summary"]["human_cards_with_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
