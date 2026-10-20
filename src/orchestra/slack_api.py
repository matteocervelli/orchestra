"""Minimal Slack Web API client with externally injected 1Password auth."""

from __future__ import annotations

import functools
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from collections.abc import Sequence
from typing import BinaryIO, Final

JsonObject = dict[str, object]

ITEMS: Final = {
    "notify": "slack-app-adlimen-notify",
    "limen": "slack-app-limen",
}
METHOD = re.compile(r"^[a-z][A-Za-z0-9.]+$")


class CredentialUnavailable(RuntimeError):
    """The caller did not inject the credential required to query 1Password."""


class SlackResponseError(RuntimeError):
    """Slack returned a response that is not a JSON object."""


@functools.lru_cache(maxsize=8)
def token(app: str, field: str = "bot_token") -> str:
    """Resolve one Slack token without persisting or printing it."""
    item = ITEMS.get(app)
    if item is None:
        raise ValueError(f"unsupported Slack app: {app}")
    service_account = os.environ.get("OP_SERVICE_ACCOUNT_TOKEN")
    if not service_account:
        raise CredentialUnavailable("OP_SERVICE_ACCOUNT_TOKEN must be injected")
    environment = dict(os.environ, OP_SERVICE_ACCOUNT_TOKEN=service_account)
    result = subprocess.run(
        ["op", "read", f"op://orchestra-smoke/{item}/{field}"],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    value = result.stdout.strip()
    if not value:
        raise CredentialUnavailable(f"1Password returned an empty {field}")
    return value


def decode_response(response: BinaryIO) -> JsonObject:
    """Decode a Slack response and reject unexpected top-level values."""
    value: object = json.load(response)
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise SlackResponseError("Slack response must be a JSON object")
    return value


def call(
    app: str,
    method: str,
    args: JsonObject | None = None,
    form: bool = False,
) -> JsonObject:
    """Call Slack with JSON, or URL-encoded form data for read methods."""
    if not METHOD.fullmatch(method):
        raise ValueError(f"invalid Slack API method: {method}")
    if form:
        data = urllib.parse.urlencode(args or {}).encode()
        content_type = "application/x-www-form-urlencoded"
    else:
        data = json.dumps(args or {}).encode()
        content_type = "application/json; charset=utf-8"
    request = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token(app)}",
            "Content-Type": content_type,
            "User-Agent": "orchestra-slack/1.0",
        },
    )
    # Method validation plus the literal HTTPS origin prevent alternate schemes.
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
        return decode_response(response)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the small compatibility CLI."""
    values = list(sys.argv[1:] if argv is None else argv)
    if len(values) not in {2, 3}:
        print(
            "usage: slack_api.py <notify|limen> <method> [json-object]", file=sys.stderr
        )
        return 2
    payload: object = json.loads(values[2]) if len(values) == 3 else None
    if payload is not None and not isinstance(payload, dict):
        raise ValueError("Slack arguments must be a JSON object")
    print(json.dumps(call(values[0], values[1], payload), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
