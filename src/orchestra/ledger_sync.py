"""Reconcile finished child logs into an append-only runtime ledger."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

JsonObject = dict[str, object]

NOTE_MAX = 200
CODEX_EVENTS = frozenset({"thread.started", "turn.started", "item.completed"})
CLAUDE_EVENTS = frozenset({"system", "result", "assistant"})


def read_jsonl(path: Path) -> list[JsonObject]:
    """Return valid JSON objects from a JSON-lines file."""
    rows: list[JsonObject] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            value: object = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and all(isinstance(key, str) for key in value):
            rows.append(value)
    return rows


def exit_code(err: Path) -> str | None:
    """Return the last EXIT marker from a child stderr file."""
    code = None
    for line in err.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("EXIT="):
            code = line[5:].strip()
    return code


def tool_of(events: list[JsonObject], spawn: JsonObject) -> str:
    """Infer the adapter from events before falling back to spawn metadata."""
    event_types = {event.get("type") for event in events}
    if event_types & CODEX_EVENTS:
        return "codex"
    if event_types & CLAUDE_EVENTS:
        return "claude"
    value = spawn.get("tool")
    return value if isinstance(value, str) and value else "unknown"


def final_report(events: list[JsonObject]) -> str:
    """Return the latest Claude result or Codex agent message."""
    last = ""
    for event in events:
        result = event.get("result")
        if event.get("type") == "result" and result:
            last = str(result)
            continue
        item = event.get("item")
        if (
            event.get("type") == "item.completed"
            and isinstance(item, dict)
            and item.get("type") == "agent_message"
        ):
            text = item.get("text")
            last = str(text) if text else ""
    return last


def first_line(text: str) -> str:
    """Return the first non-empty line, clipped for the ledger."""
    line = next(
        (candidate.strip() for candidate in text.splitlines() if candidate.strip()), ""
    )
    return line if len(line) <= NOTE_MAX else line[: NOTE_MAX - 1] + "…"


def iso(timestamp: float) -> str:
    """Format a Unix timestamp as a stable UTC ledger timestamp."""
    return datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def row_for_error(
    err: Path, existing: set[object], spawns: dict[str, JsonObject]
) -> tuple[float, JsonObject] | None:
    """Build one ledger candidate from a child stderr marker."""
    slug = err.name.removesuffix(".err")
    code = exit_code(err)
    if code is None or slug in existing:
        return None
    events = read_jsonl(err.with_name(f"{slug}.jsonl"))
    modified_at = err.stat().st_mtime
    report = first_line(final_report(events)) or f"EXIT={code}, no final report"
    return (
        modified_at,
        {
            "ts": iso(modified_at),
            "slug": slug,
            "tool": tool_of(events, spawns.get(slug, {})),
            "outcome": "done" if code == "0" else "failed",
            "note": report,
        },
    )


def missing_rows(root: Path) -> list[JsonObject]:
    """Build rows for finished children that have no ledger entry, oldest first."""
    logs = root / "logs"
    existing = {row.get("slug") for row in read_jsonl(root / "ledger.jsonl")}
    spawns = {
        slug: row
        for row in read_jsonl(logs / "spawns.jsonl")
        if isinstance((slug := row.get("slug")), str)
    }
    errors = logs.glob("*.err") if logs.is_dir() else []
    candidates = [
        candidate
        for err in errors
        if (candidate := row_for_error(err, existing, spawns)) is not None
    ]
    return [
        row
        for _, row in sorted(candidates, key=lambda item: (item[0], item[1]["slug"]))
    ]


def append(root: Path, rows: list[JsonObject]) -> None:
    """Append rows to the runtime ledger without rewriting prior state."""
    if not rows:
        return
    with (root / "ledger.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        )


def main(argv: list[str] | None = None) -> int:
    """Run ledger reconciliation for an explicitly selected runtime root."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="print rows, write nothing"
    )
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    rows = missing_rows(args.root)
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))
    if not args.dry_run:
        append(args.root, rows)
    action = "to add" if args.dry_run else "added"
    print(f"ledger_sync: {len(rows)} row(s) {action}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
