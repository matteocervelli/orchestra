#!/usr/bin/env python3
"""Slack sink for Orchestra notifications (used by notify.py and slack_ask.py).

Routing by kind, short Italian mrkdwn format, 1 msg/s per channel (flock'd
state file, so concurrent
processes serialise), retries with exponential backoff / Retry-After. Tokens
come from bin/slack_api.py
(1Password, never printed); every log line is scrubbed of Slack tokens."""

from __future__ import annotations

import datetime
import fcntl
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
from collections.abc import Callable
from pathlib import Path

ORCH = Path(os.environ.get("ORCHESTRA_DIR", str(Path(__file__).resolve().parents[1])))
SLACK_FLAG = (
    "ORCHESTRA_SLACK"  # present in ORCHESTRA_DIR: notify.py also sends to Slack
)

# Dual delivery ends after this inclusive date.
ATRIUM_DUAL_UNTIL = datetime.date(2026, 11, 19)

ROUTES = {
    "decision": "orchestra",
    "blocked": "orchestra",
    "review": "orchestra",
    "status": "orchestra",
    "done": "orchestra",
    "ask": "orchestra",
    "needs-human": "orchestra",
    "ci": "ci",
    "release": "release",
    "deploy": "release",
    "alert": "alert",
    "incident": "alert",
}
LABELS = {
    "decision": "Decisione",
    "blocked": "Bloccato",
    "review": "Da rivedere",
    "status": "Stato",
    "done": "Fatto",
    "ask": "Domanda",
    "needs-human": "Serve una persona",
    "ci": "CI",
    "release": "Rilascio",
    "deploy": "Deploy",
    "alert": "Allarme",
    "incident": "Incidente",
}
EMOJI = {
    "decision": ":question:",
    "ask": ":question:",
    "needs-human": ":raising_hand:",
    "blocked": ":no_entry:",
    "review": ":eyes:",
    "status": ":information_source:",
    "done": ":white_check_mark:",
    "ci": ":gear:",
    "release": ":package:",
    "deploy": ":rocket:",
    "alert": ":rotating_light:",
    "incident": ":rotating_light:",
}
TAILNET_NOTE = "_I link :8460 funzionano solo sulla tailnet._"
MAX_BODY = 2500
MAX_ATTEMPTS = 5
MIN_INTERVAL = 1.0  # Slack: 1 message per second per channel
TRANSIENT = {
    "ratelimited",
    "internal_error",
    "service_unavailable",
    "fatal_error",
    "request_timeout",
}
TOKEN_RE = re.compile(r"xox[a-z]-[\w-]+|xapp-[\w-]+")


class SlackError(Exception):
    """A Slack call failed for good (permanent error or retries exhausted)."""


def route(kind: str) -> str:
    return ROUTES.get(kind, "orchestra")


def atrium_active(today: datetime.date | None = None) -> bool:
    return (today or datetime.date.today()) <= ATRIUM_DUAL_UNTIL


def slack_enabled(orch: Path = ORCH) -> bool:
    return (orch / SLACK_FLAG).exists()


def esc(text: str) -> str:
    """Neutralise Slack control sequences (<!channel>, <@U1>, &) in text coming
    from data."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_mrkdwn(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"<\2|\1>", text)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.M)
    return re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)


def format_message(kind: str, subject: str, body: str) -> str:
    """First line = what happened; identifiers stay in backticks (the caller's body
    already has them)."""
    head = (
        f"{EMOJI.get(kind, ':information_source:')} "
        f"*{LABELS.get(kind, kind)}: {subject.strip()}*"
    )
    body = to_mrkdwn(body.strip())
    if len(body) > MAX_BODY:
        body = body[:MAX_BODY].rstrip() + "…"
    parts = [head, body] if body else [head]
    if ":8460" in head + body:
        parts.append(TAILNET_NOTE)
    return "\n".join(parts)


def load_channels(orch: Path = ORCH) -> dict[str, str]:
    return json.loads((orch / "scratch" / "slack" / "channels.json").read_text())


def default_api() -> Callable[..., dict]:
    import slack_api  # lazy: tests inject their own api

    def call(method: str, args: dict, form: bool = False) -> dict:
        return slack_api.call("notify", method, args, form=form)

    return call


class SlackSink:
    def __init__(
        self,
        api: Callable[..., dict],
        channels: dict[str, str],
        state_dir: Path,
        log_path: Path,
        now: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api, self.channels, self.state_dir, self.log_path, self.now, self.sleep = (
            api,
            {
                "release": "C0CAEALG03V",
                **channels,
                **(
                    {"release": os.environ["RELEASE_CHANNEL_ID"].strip()}
                    if os.environ.get("RELEASE_CHANNEL_ID", "").strip()
                    else {}
                ),
            },
            state_dir,
            log_path,
            now,
            sleep,
        )

    @classmethod
    def default(cls, orch: Path = ORCH) -> SlackSink:
        return cls(
            default_api(),
            load_channels(orch),
            orch / "logs" / "slack-state",
            orch / "logs" / "slack.log",
        )

    def log(self, message: str) -> None:
        line = (
            f"{datetime.datetime.now(datetime.UTC):%Y-%m-%dT%H:%M:%SZ} "
            f"{TOKEN_RE.sub('[redacted]', message)}\n"
        )
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a") as f:
                f.write(line)
        except OSError:
            print(line.rstrip(), file=sys.stderr)

    def call(self, method: str, args: dict, form: bool = False) -> dict:
        """One Slack API call with retries; raises SlackError."""
        last = "unknown error"
        for attempt in range(MAX_ATTEMPTS):
            delay = float(2**attempt)
            try:
                res = self.api(method, args, form=form)
                if res.get("ok"):
                    return res
                last = str(res.get("error", "unknown error"))
                if last not in TRANSIENT:
                    break
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
                if e.code == 429:
                    delay = float(e.headers.get("Retry-After") or delay)
                elif e.code < 500:
                    break
            except (
                FileNotFoundError,
                subprocess.SubprocessError,
            ) as e:  # token lookup, not the network
                last = f"token unavailable: {type(e).__name__}"
                break
            except (OSError, TimeoutError) as e:  # URLError is an OSError
                last = f"network: {getattr(e, 'reason', e)}"
            if attempt < MAX_ATTEMPTS - 1:
                self.sleep(delay)
        self.log(f"{method} failed: {last}")
        raise SlackError(TOKEN_RE.sub("[redacted]", last))

    def _throttle(self, channel_id: str) -> Callable[[], None]:
        """Take the per-channel lock, wait out MIN_INTERVAL; returns the release+stamp
        callback."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        fh = open(self.state_dir / f"{channel_id}.last", "a+")  # noqa: SIM115 - released by callback
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        try:
            last = float(fh.read().strip() or 0)
        except ValueError:
            last = 0.0
        wait = last + MIN_INTERVAL - self.now()
        if wait > 0:
            self.sleep(wait)

        def release() -> None:
            fh.seek(0)
            fh.truncate()
            fh.write(repr(self.now()))
            fh.close()  # also drops the flock

        return release

    def post(
        self,
        channel: str,
        text: str,
        thread_ts: str | None = None,
        blocks: list[dict] | None = None,
        attachments: list[dict] | None = None,
    ) -> dict:
        try:
            channel_id = self.channels[channel]
        except KeyError:
            raise SlackError(f"unknown channel {channel!r}") from None
        args = {
            "channel": channel_id,
            "text": text,
            "unfurl_links": False,
            "unfurl_media": False,
        }
        if thread_ts:
            args["thread_ts"] = thread_ts
        if blocks:
            args["blocks"] = blocks
        if attachments:
            args["attachments"] = attachments
        release = self._throttle(channel_id)
        try:
            return self.call("chat.postMessage", args)
        finally:
            release()

    def permalink(self, channel_id: str, ts: str) -> str | None:
        """Slack's own permalink for a message; None if Slack refuses (then the caller
        links nothing)."""
        try:
            res = self.call(
                "chat.getPermalink",
                {"channel": channel_id, "message_ts": ts},
                form=True,
            )
            return res["permalink"]
        except (SlackError, KeyError):
            return None

    def notify(self, kind: str, subject: str, body: str) -> bool:
        """Never raises: a Slack failure must not break the other sink."""
        try:
            channel = route(kind)
            message = format_message(kind, subject, body)
            if channel == "release" and not self.channels.get("release"):
                channel = "orchestra"
                note = "RELEASE_CHANNEL_ID non configurato: ripiego su #orchestra."
                self.log(note)
                message += "\n_" + note + "_"
            try:
                self.post(channel, message)
            except SlackError as e:
                if channel != "release" or str(e) not in {
                    "not_in_channel",
                    "is_archived",
                    "channel_not_found",
                }:
                    raise
                note = f"#release non disponibile ({e}): ripiego su #orchestra."
                self.log(note)
                self.post("orchestra", message + "\n_" + note + "_")
            return True
        except SlackError as e:
            self.log(f"notify {kind} not sent: {e}")
            return False
        except Exception as e:
            self.log(f"notify {kind} crashed: {type(e).__name__}: {e}")
            return False
