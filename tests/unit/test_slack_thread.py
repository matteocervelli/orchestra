from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestra import slack_thread


def runtime(tmp_path: Path) -> Path:
    slack = tmp_path / "scratch" / "slack"
    slack.mkdir(parents=True)
    (slack / "channels.json").write_text(json.dumps({"orchestra": "CORCH"}))
    (slack / "threads.json").write_text(json.dumps({"chat-nexus": "100.0"}))
    return tmp_path


def test_central_thread_post(tmp_path: Path) -> None:
    root = runtime(tmp_path)
    assert slack_thread.post_payload(root, "chat-nexus", "status") == {
        "channel": "CORCH",
        "thread_ts": "100.0",
        "text": "status",
    }


def test_project_route_and_reply_anchor(tmp_path: Path) -> None:
    root = runtime(tmp_path)
    slack = root / "scratch" / "slack"
    (slack / "routes.json").write_text(json.dumps({"CNEXUS": "chat-nexus"}))
    assert slack_thread.post_payload(root, "chat-nexus", "new") == {
        "channel": "CNEXUS",
        "text": "new",
    }
    (slack / "reply_to.json").write_text(
        json.dumps({"chat-nexus": {"channel": "CNEXUS", "thread_ts": "200.0"}})
    )
    assert slack_thread.post_payload(root, "chat-nexus", "reply") == {
        "channel": "CNEXUS",
        "thread_ts": "200.0",
        "text": "reply",
    }
    assert slack_thread.post_payload(root, "chat-nexus", "fresh", new=True) == {
        "channel": "CNEXUS",
        "text": "fresh",
    }


def test_matteo_replies_are_filtered_and_sorted(tmp_path: Path) -> None:
    root = runtime(tmp_path)

    def api_call(
        app: str, method: str, args: dict[str, object], form: bool
    ) -> dict[str, object]:
        assert (app, method, form) == ("notify", "conversations.replies", True)
        assert args == {"channel": "CORCH", "ts": "100.0", "limit": 200}
        return {
            "messages": [
                {"user": slack_thread.MATTEO, "ts": "100.0", "text": "root"},
                {"user": "BOT", "ts": "101.0", "text": "ignore"},
                {"user": slack_thread.MATTEO, "ts": "103.0", "text": "later"},
                {"user": slack_thread.MATTEO, "ts": "102.0", "text": "earlier"},
            ]
        }

    assert slack_thread.read_replies(root, "chat-nexus", 101.0, api_call=api_call) == [
        {"ts": "102.0", "text": "earlier"},
        {"ts": "103.0", "text": "later"},
    ]


def test_post_message_returns_explicit_slack_outcome(tmp_path: Path) -> None:
    root = runtime(tmp_path)
    calls: list[tuple[str, str, dict[str, object] | None, bool]] = []

    def api_call(
        app: str, method: str, args: dict[str, object] | None, form: bool
    ) -> dict[str, object]:
        calls.append((app, method, args, form))
        return {"ok": True}

    assert slack_thread.post_message(root, "chat-nexus", "done", api_call=api_call)
    assert calls == [
        (
            "notify",
            "chat.postMessage",
            {"channel": "CORCH", "thread_ts": "100.0", "text": "done"},
            False,
        )
    ]


def test_invalid_reply_anchor_fails_closed(tmp_path: Path) -> None:
    root = runtime(tmp_path)
    (root / "scratch" / "slack" / "reply_to.json").write_text(
        json.dumps({"chat-nexus": {"channel": "C1"}})
    )
    with pytest.raises(ValueError, match="invalid reply anchor"):
        slack_thread.post_payload(root, "chat-nexus", "message")


def test_default_root_honors_explicit_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORCHESTRA_ROOT", str(tmp_path))
    assert slack_thread.default_root() == tmp_path
