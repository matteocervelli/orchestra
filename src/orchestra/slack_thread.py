"""Route Orchestra session updates to Slack channels or anchored threads."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path

from orchestra.slack_api import JsonObject, call

MATTEO = "U0CAE3R24TV"
ApiCall = Callable[[str, str, JsonObject | None, bool], JsonObject]


def load_object(path: Path) -> JsonObject:
    """Load a required JSON object from runtime configuration."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"expected JSON object: {path}")
    return value


def slack_dir(root: Path) -> Path:
    return root / "scratch" / "slack"


def required_string(values: JsonObject, key: str, source: Path) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing string {key!r} in {source}")
    return value


def routed_channel(config: Path, name: str) -> str | None:
    """Return the project channel mapped to a session, when configured."""
    routes_path = config / "routes.json"
    routes = load_object(routes_path) if routes_path.exists() else {}
    return next(
        (
            route
            for route, session in routes.items()
            if session == name and isinstance(route, str) and route
        ),
        None,
    )


def reply_payload(config: Path, name: str, text: str) -> JsonObject | None:
    """Return the latest explicit reply anchor, when one exists."""
    reply_path = config / "reply_to.json"
    replies = load_object(reply_path) if reply_path.exists() else {}
    reply = replies.get(name)
    if reply is None:
        return None
    if not isinstance(reply, dict):
        raise ValueError(f"invalid reply anchor for {name}")
    channel = reply.get("channel")
    thread = reply.get("thread_ts")
    if not isinstance(channel, str) or not isinstance(thread, str):
        raise ValueError(f"invalid reply anchor for {name}")
    return {"channel": channel, "thread_ts": thread, "text": text}


def post_payload(root: Path, name: str, text: str, *, new: bool = False) -> JsonObject:
    """Resolve one post destination without calling Slack."""
    config = slack_dir(root)
    channels_path = config / "channels.json"
    threads_path = config / "threads.json"
    channel = required_string(load_object(channels_path), "orchestra", channels_path)
    thread = required_string(load_object(threads_path), name, threads_path)

    project_channel = routed_channel(config, name)
    payload: JsonObject = (
        {"channel": project_channel, "text": text}
        if project_channel
        else {"channel": channel, "thread_ts": thread, "text": text}
    )
    anchored = None if new else reply_payload(config, name, text)
    return anchored or payload


def post_message(
    root: Path,
    name: str,
    text: str,
    *,
    new: bool = False,
    api_call: ApiCall = call,
) -> bool:
    """Post one routed update and return Slack's explicit outcome."""
    response = api_call(
        "notify", "chat.postMessage", post_payload(root, name, text, new=new), False
    )
    return response.get("ok") is True


def read_replies(
    root: Path,
    name: str,
    since: float = 0.0,
    *,
    api_call: ApiCall = call,
) -> list[JsonObject]:
    """Return Matteo's replies after a timestamp, excluding the root message."""
    config = slack_dir(root)
    channels_path = config / "channels.json"
    threads_path = config / "threads.json"
    channel = required_string(load_object(channels_path), "orchestra", channels_path)
    thread = required_string(load_object(threads_path), name, threads_path)
    response = api_call(
        "notify",
        "conversations.replies",
        {"channel": channel, "ts": thread, "limit": 200},
        True,
    )
    raw_messages = response.get("messages", [])
    if not isinstance(raw_messages, list):
        raise ValueError("Slack messages must be a list")
    replies: list[JsonObject] = []
    for raw in raw_messages:
        if not isinstance(raw, dict) or raw.get("user") != MATTEO:
            continue
        timestamp = raw.get("ts")
        if (
            not isinstance(timestamp, str)
            or timestamp == thread
            or float(timestamp) <= since
        ):
            continue
        text = raw.get("text")
        replies.append({"ts": timestamp, "text": text if isinstance(text, str) else ""})
    return sorted(replies, key=lambda message: float(str(message["ts"])))


def default_root() -> Path:
    """Resolve runtime root only from explicit injection or the checkout root."""
    configured = os.environ.get("ORCHESTRA_ROOT")
    return Path(configured) if configured else Path(__file__).resolve().parents[2]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the compatibility CLI for post/read operations."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    post = subparsers.add_parser("post")
    post.add_argument("thread")
    post.add_argument("text")
    post.add_argument("--new", action="store_true")
    read = subparsers.add_parser("read")
    read.add_argument("thread")
    read.add_argument("since", nargs="?", type=float, default=0.0)
    args = parser.parse_args(argv)

    if args.command == "post":
        ok = post_message(default_root(), args.thread, args.text, new=args.new)
        print("ok" if ok else "error")
        return 0 if ok else 1
    for message in read_replies(default_root(), args.thread, args.since):
        print(json.dumps(message, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
