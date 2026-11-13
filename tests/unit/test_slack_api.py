from __future__ import annotations

import io
import json
import urllib.error
from types import SimpleNamespace
from typing import Any

import pytest

from orchestra import slack_api


class Response(io.BytesIO):
    def __enter__(self) -> Response:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def test_token_requires_injected_service_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OP_SERVICE_ACCOUNT_TOKEN", raising=False)
    slack_api.token.cache_clear()
    with pytest.raises(slack_api.CredentialUnavailable):
        slack_api.token("notify")


def test_token_is_read_once_from_injected_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []
    monkeypatch.setenv("OP_SERVICE_ACCOUNT_TOKEN", "service-account")

    def run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append((command, kwargs["env"]))
        return SimpleNamespace(stdout="bot-token\n")

    monkeypatch.setattr(slack_api.subprocess, "run", run)
    slack_api.token.cache_clear()
    assert slack_api.token("notify") == "bot-token"
    assert slack_api.token("notify") == "bot-token"
    assert len(calls) == 1
    assert calls[0][0] == [
        "op",
        "read",
        "op://orchestra-smoke/slack-app-adlimen-notify/bot_token",
    ]
    assert calls[0][1]["OP_SERVICE_ACCOUNT_TOKEN"] == "service-account"


def test_json_call_sets_headers_without_exposing_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(slack_api, "token", lambda app: "secret-value")

    def open_request(request: Any, timeout: int) -> Response:
        captured.update(request=request, timeout=timeout)
        return Response(b'{"ok": true, "ts": "1.0"}')

    monkeypatch.setattr(slack_api.urllib.request, "urlopen", open_request)
    assert slack_api.call("notify", "chat.postMessage", {"text": "hello"})["ok"] is True
    request = captured["request"]
    assert request.full_url == "https://slack.com/api/chat.postMessage"
    assert request.headers["Authorization"] == "Bearer secret-value"
    assert json.loads(request.data) == {"text": "hello"}
    assert captured["timeout"] == 30


def test_form_call_encodes_read_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(slack_api, "token", lambda app: "token")
    seen: list[bytes] = []

    def open_request(request: Any, timeout: int) -> Response:
        seen.append(request.data)
        return Response(b'{"ok": true}')

    monkeypatch.setattr(slack_api.urllib.request, "urlopen", open_request)
    slack_api.call(
        "notify", "conversations.replies", {"channel": "C1", "ts": "2"}, form=True
    )
    assert seen == [b"channel=C1&ts=2"]


def test_invalid_app_method_and_payload_fail_closed() -> None:
    with pytest.raises(ValueError):
        slack_api.token("unknown")
    with pytest.raises(ValueError):
        slack_api.call("notify", "../bad")
    with pytest.raises(slack_api.SlackResponseError):
        slack_api.decode_response(Response(b"[]"))


def test_transport_error_does_not_include_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(slack_api, "token", lambda app: "do-not-leak")

    def fail(request: Any, timeout: int) -> Response:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(slack_api.urllib.request, "urlopen", fail)
    with pytest.raises(urllib.error.URLError) as error:
        slack_api.call("notify", "chat.postMessage")
    assert "do-not-leak" not in str(error.value)


def test_cli_serializes_response(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        slack_api,
        "call",
        lambda app, method, args: {
            "ok": True,
            "app": app,
            "method": method,
            "args": args,
        },
    )
    assert slack_api.main(["notify", "chat.postMessage", '{"text":"ciao"}']) == 0
    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "app": "notify",
        "method": "chat.postMessage",
        "args": {"text": "ciao"},
    }
    assert slack_api.main([]) == 2
