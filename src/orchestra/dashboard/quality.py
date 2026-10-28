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
from .repository import repository_key
from .titles import generic_title

PENDING = frozenset({"PR review", "PR fix", "Merge", "Integration", "Main"})
GENERIC_QUESTION = "guarda il dettaglio e decidi come procedere"


def _norm(value: object) -> str:
    return str(value or "").strip().rstrip(".! ").casefold()


def findings(item: dict[Any, Any]) -> list[dict[Any, Any]]:
    """Report deficits without changing asks, answers, states or visibility."""
    human = bool(item.get("your_call"))
    severity = "error" if human else "warning"
    rows = _title_findings(item, severity)
    asks = _open_asks(item)
    rows.extend(_duplicate_ask_findings(asks, severity))
    if human and not asks:
        rows.append(
            _finding(
                "missing_question",
                "Richiesta a Matteo senza una domanda aperta.",
                "error",
            )
        )
    if human:
        for ask in asks:
            rows.extend(_human_ask_findings(ask, item))
    rows.extend(_execution_findings(item, severity))
    rows.extend(_pipeline_findings(item))
    if (item.get("work_provenance") or {}).get("validation") == "conflict":
        rows.append(
            _finding(
                "conflicting_work_provenance",
                "La provenienza richiede verifica delle fonti.",
            )
        )
    return _unique_findings(rows)


def audit(
    data: dict[Any, Any], *, board_url: str = "/orchestra/board?item="
) -> dict[Any, Any]:
    items = [item for item in data.get("items", []) if isinstance(item, dict)]
    affected = []
    for item in items:
        issues = findings(item)
        if issues:
            affected.append(_affected_item(item, issues, board_url))
    return {
        "coverage": {"structure": "checked", "semantic_freshness": "not_verified"},
        "generated": data.get("generated"),
        "summary": _quality_summary(items, affected),
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
    snapshot_digest = board_digest(data)
    enriched = [
        _enrich_board_item(item, details, data, snapshot_digest)
        for item in data.get("items", [])
    ]
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


def _finding(code: str, message: str, severity: str = "warning") -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message}


def _unique_findings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out, seen = [], set()
    for row in rows:
        if row["code"] not in seen:
            out.append(row)
            seen.add(row["code"])
    return out


def _title_findings(item: dict[str, Any], severity: str) -> list[dict[str, Any]]:
    if "title_it" in (item.get("auto") or []) or generic_title(
        str(item.get("title") or "")
    ):
        return [
            _finding(
                "generic_title",
                "Titolo da curare con oggetto e risultato specifici.",
                severity,
            )
        ]
    return []


def _open_asks(item: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        ask
        for ask in item.get("ask") or []
        if isinstance(ask, dict) and not ask.get("answered")
    ]


def _duplicate_ask_findings(
    asks: list[dict[str, Any]], severity: str
) -> list[dict[str, Any]]:
    ids = Counter(
        ask["id"]
        for ask in asks
        if isinstance(ask.get("id"), str) and ask["id"].strip()
    )
    if any(count > 1 for count in ids.values()):
        return [
            _finding(
                "duplicate_ask_id",
                "Domande aperte con lo stesso identificatore: "
                "preservare e distinguere le richieste.",
                severity,
            )
        ]
    return []


def _human_ask_findings(
    ask: dict[str, Any], item: dict[str, Any]
) -> list[dict[str, Any]]:
    rows = []
    question, rec = _norm(ask.get("question")), _norm(ask.get("rec"))
    if not question or GENERIC_QUESTION in question:
        rows.append(
            _finding(
                "generic_question",
                "Recuperare la domanda concreta dalle fonti.",
                "error",
            )
        )
    if not rec or rec.startswith("nessuno, scegli tu:"):
        rows.append(
            _finding(
                "missing_recommendation",
                "Manca una raccomandazione motivata o un limite esplicito.",
                "error",
            )
        )
    if question.startswith("orchestra:"):
        rows.append(
            _finding(
                "technical_question",
                "Il testo assegna lavoro a Orchestra, non una decisione a Matteo.",
                "error",
            )
        )
    if _missing_visual_evidence(ask, item):
        rows.append(
            _finding(
                "missing_visual_evidence",
                "Approvazione visiva priva di una proposta collegata.",
                "error",
            )
        )
    return rows


def _missing_visual_evidence(ask: dict[str, Any], item: dict[str, Any]) -> bool:
    if ask.get("kind") not in ("approve UI", "approve mockup"):
        return False
    pages = item.get("pages") or {}
    return not any(pages.get(key) for key in ("display", "mockup", "post"))


def _finished_children(item: dict[str, Any]) -> bool:
    return any(
        child.get("end") or child.get("exit") is not None
        for child in item.get("children") or []
        if isinstance(child, dict)
    )


def _execution_findings(item: dict[str, Any], severity: str) -> list[dict[str, Any]]:
    if _finished_children(item) and "nessun agente l'ha ancora presa" in str(
        item.get("solution") or ""
    ):
        return [
            _finding(
                "execution_contradiction",
                "Una esecuzione esiste: non descrivere il lavoro come mai iniziato.",
                severity,
            )
        ]
    return []


def _pipeline_findings(item: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if item.get("status") not in PENDING:
        return rows
    if not qualified_pr(
        item.get("pr"), str(item.get("repo") or "")
    ) and not local_review(item):
        rows.append(
            _finding(
                "pipeline_without_pr",
                (
                    "Stato avanzato senza richiesta di integrazione primaria: "
                    "verificare la provenienza."
                ),
            )
        )
    if (
        item.get("status") in ("Integration", "Main")
        and _norm(item.get("needs")) == "niente: già fatto"
    ):
        rows.append(
            _finding(
                "integration_not_delivery",
                "Integrazione o main non dimostrano rilascio e verifica operativa.",
            )
        )
    return rows


def _affected_item(
    item: dict[str, Any], issues: list[dict[str, Any]], board_url: str
) -> dict[str, Any]:
    return {
        "id": item["id"],
        "repo": repository_key(item.get("repo")),
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


def _human_error_count(affected: list[dict[str, Any]]) -> int:
    return sum(
        row["your_call"]
        and any(issue["severity"] == "error" for issue in row["issues"])
        for row in affected
    )


def _quality_summary(
    items: list[dict[str, Any]], affected: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "cards_checked": len(items),
        "human_cards_checked": sum(bool(item.get("your_call")) for item in items),
        "human_cards_with_errors": _human_error_count(affected),
        "cards_with_findings": len(affected),
        "findings_by_code": dict(
            Counter(issue["code"] for row in affected for issue in row["issues"])
        ),
    }


def _safe_detail_id(iid: Any) -> bool:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    return not (
        not iid or any(char not in allowed for char in iid) or iid in (".", "..")
    )


def _load_bound_detail(
    details: Path, iid: Any, data: dict[str, Any], digest: str
) -> dict[str, Any]:
    try:
        row = json.loads((details / f"{iid}.json").read_text())
    except (OSError, ValueError):
        row = {}
    if not isinstance(row, dict) or not detail_matches_board(
        row, data, str(iid), snapshot_digest=digest
    ):
        return {}
    return row


def _enrich_board_item(
    item: dict[str, Any], details: Path, data: dict[str, Any], digest: str
) -> dict[str, Any]:
    iid = item.get("id", "")
    if not _safe_detail_id(iid):
        return item
    row = _load_bound_detail(details, iid, data, digest)
    combined = {**row, **item}
    combined["your_call"] = bool(item.get("your_call"))
    combined["ask"] = item.get("ask") or []
    if row.get("children") and all(
        set(child) <= {"slug"} for child in item.get("children", [])
    ):
        combined["children"] = row["children"]
    return combined


if __name__ == "__main__":
    raise SystemExit(main())
