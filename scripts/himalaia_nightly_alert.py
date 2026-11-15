#!/usr/bin/env python3
"""Post the Himalaia nightly result to Slack #alert in the same shape as the
Alertmanager alerts.

This optional homelab
check reads the nightly jobs with `fj ci tasks`. For the newest finished
nightly run:
- a failed job -> one FIRING attachment (red bar, `NEXUS_ALERT_V1` block,
Fonte: himalaia-nightly),
  with the first failed test of each job and the `fj ci log` command;
- green after an open alert -> clear the local marker silently.
The Alerts app token stays on the configured ALERT_SENDER_HOST: the
attachment is piped
over SSH to the configured ALERT_SENDER_PATH (adlimen-infra), so the
sender is the Alerts app like the other alerts. Only if that fails the
Orchestra bot posts the same
layout and a line says so. State in scratch/himalaia-nightly-alert.json
keeps one alert per
run number (`_open` = the run whose alert is not resolved yet).

Usage: himalaia_nightly_alert.py [--dry-run] [--pages N]"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ORCH = Path(os.environ.get("ORCHESTRA_DIR", "."))
sys.path.insert(0, str(ORCH / "bin"))
STATE = ORCH / "scratch" / "himalaia-nightly-alert.json"
REPO = "adlimen/app-himalaia"
SOURCE = "himalaia-nightly"
SENDER_HOST = os.environ.get("ALERT_SENDER_HOST", "")
SENDER_PATH = os.environ.get("ALERT_SENDER_PATH", "")
RED = "a30200"  # Alertmanager failure colour
# Task names of the jobs in .forgejo/workflows/nightly.yml.
NIGHTLY_JOBS = {
    "Backend Nightly Suite",
    "Frontend Mobile Shell E2E",
    "Clock Edge Guard",
    "Nightly Triage & Digest",
    "Timestamp Benchmark",
}
ROW = re.compile(r"run#(\d+)\s+task#(\d+)\s+(\w+)\s+([0-9a-f]{7,40})\s+(.+?)\s*$")
LOG_TS = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z\s?")
FAILED_LINE = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)(?:\s+-\s+(.*))?$")
SUMMARY_LINE = re.compile(r"^=*\s*(\d+ failed.*?\d+ passed.*?)(?: in [\d.]+s.*)?$")
NODE_DOWN = re.compile(r"\[gw\d+\] node down: .*")


def parse_rows(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        m = ROW.search(line)
        if m and m.group(5) in NIGHTLY_JOBS:
            rows.append(
                {
                    "run": int(m.group(1)),
                    "task": int(m.group(2)),
                    "status": m.group(3),
                    "sha": m.group(4),
                    "job": m.group(5),
                }
            )
    return rows


def newest_finished(rows: list[dict]) -> dict | None:
    """Newest nightly run with no job in flight: {run, sha, jobs:[failed],
    tasks:{job: task}}."""
    by_run: dict[int, list[dict]] = {}
    for r in rows:
        by_run.setdefault(r["run"], []).append(r)
    for run in sorted(by_run, reverse=True):
        jobs = by_run[run]
        if any(j["status"] in ("running", "waiting", "queued") for j in jobs):
            continue  # still in flight: look again at the next check
        bad = sorted(j["job"] for j in jobs if j["status"] == "failure")
        return {
            "run": run,
            "sha": jobs[0]["sha"][:8],
            "jobs": bad,
            "tasks": {j["job"]: j["task"] for j in jobs},
            "cancelled": any(j["status"] == "cancelled" for j in jobs),
        }
    return None


def failed_nightly(rows: list[dict]) -> dict | None:
    """Newest finished nightly run if it has a failed job; None when it is green."""
    hit = newest_finished(rows)
    return hit if hit and hit["jobs"] else None


def first_failure(log: str) -> str:
    """First failed test of a CI log (pytest `FAILED id - reason`), else the first
    crashed
        xdist worker, else a statement that the log shows no failed test
    (runner/infra error)."""
    node_down = None
    for raw in log.splitlines():
        line = LOG_TS.sub("", raw).strip()
        m = FAILED_LINE.match(line)
        if m:
            reason = f" - {m.group(2)[:120]}" if m.group(2) else ""
            return f"{m.group(1)}{reason}"
        node_down = node_down or (NODE_DOWN.search(line) or [None])[0]
    return node_down or "nessun test fallito nel log (errore del runner o timeout)"


def fetch(pages: int) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, pages + 1):
        out = subprocess.run(
            ["fj", "ci", "tasks", REPO, "--limit", "50", "--page", str(page)],
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout
        rows += parse_rows(out)
    return rows


def fetch_first_failure(task: int) -> str:
    try:
        out = subprocess.run(
            ["fj", "ci", "log", REPO, "--task", str(task)],
            cwd="/tmp",
            capture_output=True,
            text=True,
            timeout=180,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return "log non leggibile"
    return first_failure(out)


def iso(now: datetime.datetime) -> str:
    return now.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def build_attachment(hit: dict, failures: dict[str, str], *, start: str) -> dict:
    """Build a failure attachment with the existing Alertmanager layout."""
    ref = f"{SOURCE}-{hit['run']}"
    block = [
        "NEXUS_ALERT_V1",
        f"Fonte: {SOURCE}",
        f"Inizio: {start}",
        "Fine: 0001-01-01T00:00:00Z",
        "Alert: HimalaiaNightlyFailed · stato: firing",
        "Host: homelab · gravità: warning",
        f"Riferimento: {ref}",
        "FINE_NEXUS_ALERT_V1",
    ]
    extra = [f"Run `{hit['run']}` su `{hit['sha']}`, {len(hit['jobs'])} job falliti:"]
    for job in hit["jobs"]:
        extra += [
            f"• *{job}*: {failures.get(job, '-')}",
            f"   `fj ci log {REPO} --task {hit['tasks'][job]}`",
        ]
    return {
        "color": RED,
        "title": ":rotating_light: FIRING [1] HimalaiaNightlyFailed",
        "text": "\n".join(block + extra),
        "fallback": f"[FIRING] HimalaiaNightlyFailed run {hit['run']} {hit['sha']}",
        "mrkdwn_in": ["fallback", "pretext", "text"],
    }


def post_alerts(attachment: dict) -> bool:
    """Pipe the attachment to the configured sender; credentials stay there."""
    if not SENDER_HOST or not SENDER_PATH:
        return False
    try:
        out = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=15",
                SENDER_HOST,
                SENDER_PATH,
            ],
            input=json.dumps(attachment),
            capture_output=True,
            text=True,
            timeout=90,
        )
    except (OSError, subprocess.SubprocessError) as e:
        print(
            f"nightly: Alerts sender unreachable: {type(e).__name__}", file=sys.stderr
        )
        return False
    line = (
        out.stdout.strip().splitlines()
        or [out.stderr.strip()[:200] or f"exit {out.returncode}"]
    )[0]
    if out.returncode == 0 and line.startswith("ok"):
        return True
    print(f"nightly: Alerts sender failed: {line[:200]}", file=sys.stderr)
    return False


def post_orchestra(attachment: dict) -> bool:
    import slack_sink

    try:
        slack_sink.SlackSink.default(ORCH).post("alert", "", attachments=[attachment])
        return True
    except (slack_sink.SlackError, OSError) as e:
        print(f"nightly: slack post failed: {e}", file=sys.stderr)
        return False


def post(attachment: dict) -> bool:
    if post_alerts(attachment):
        return True
    print(
        "nightly: falling back to the orchestra bot "
        "(sender will not be the Alerts app)",
        file=sys.stderr,
    )
    return post_orchestra(attachment)


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("HIMALAIA_NIGHTLY_ALERT_OWNER", "relay") == "workflow":
        print("nightly: delivery owned by workflow; relay silent")
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pages", type=int, default=20)
    args = ap.parse_args(argv)
    latest = newest_finished(fetch(args.pages))
    if not latest:
        print("nightly: no finished run")
        return 0
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    now = datetime.datetime.now(datetime.UTC)
    if latest["jobs"]:
        if str(latest["run"]) in state:
            print(f"nightly: run {latest['run']} already reported")
            return 0
        failures = {
            job: fetch_first_failure(latest["tasks"][job]) for job in latest["jobs"]
        }
        att = build_attachment(latest, failures, start=iso(now))
        state.update(
            {
                str(latest["run"]): latest["sha"],
                "_open": latest["run"],
                "_start": iso(now),
            }
        )
    elif latest.get("cancelled"):
        print("nightly: cancelled without failure; no delivery or recovery")
        return 0
    elif state.get("_open"):
        state.pop("_open"), state.pop("_start", None)
        if not args.dry_run:
            STATE.write_text(json.dumps(state, indent=1))
        print("nightly: green, open marker cleared silently")
        return 0
    else:
        print("nightly: green, nothing open")
        return 0
    if args.dry_run:
        print(json.dumps(att, indent=1, ensure_ascii=False))
        return 0
    if not post(att):
        return 1
    STATE.write_text(json.dumps(state, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
