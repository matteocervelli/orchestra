"""Offline contracts for the operational notification sources."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.mark.parametrize("kind", ["release", "deploy"])
def test_release_routes_and_fallback(kind, tmp_path, monkeypatch):
    mod = module("slack_sink")
    monkeypatch.delenv("RELEASE_CHANNEL_ID", raising=False)
    api = Mock(return_value={"ok": True})
    sink = mod.SlackSink(
        api,
        {"orchestra": "C_SYNTH_ORCH", "release": "C_SYNTH_REL"},
        tmp_path / "state",
        tmp_path / "log",
    )
    assert mod.route(kind) == "release"
    assert sink.notify(kind, "Titolo", "Corpo")
    assert api.call_args.args[1]["channel"] == "C_SYNTH_REL"
    sink.channels.pop("release")
    assert sink.notify(kind, "Titolo", "Corpo")
    assert api.call_args.args[1]["channel"] == "C_SYNTH_ORCH"
    assert "RELEASE_CHANNEL_ID" in (tmp_path / "log").read_text()
    assert "#orchestra" in api.call_args.args[1]["text"]


def test_release_channel_environment(tmp_path, monkeypatch):
    mod = module("slack_sink")
    monkeypatch.setenv("RELEASE_CHANNEL_ID", "C_SYNTH_ENV")
    api = Mock(return_value={"ok": True})
    sink = mod.SlackSink(
        api, {"orchestra": "C_SYNTH_ORCH"}, tmp_path / "state", tmp_path / "log"
    )
    assert sink.notify("deploy", "Titolo", "Corpo")
    assert api.call_args.args[1]["channel"] == "C_SYNTH_ENV"


def test_nightly_green_clears_open_without_post(tmp_path, monkeypatch):
    mod = module("himalaia_nightly_alert")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"42": "abc12345", "_open": 42, "_start": "yesterday"}))
    monkeypatch.setattr(mod, "STATE", state)
    monkeypatch.setattr(mod, "fetch", lambda _: [])
    monkeypatch.setattr(
        mod,
        "newest_finished",
        lambda _: {"run": 43, "sha": "abc12345", "jobs": [], "tasks": {}},
    )
    post = Mock(side_effect=AssertionError("Unexpected delivery"))
    monkeypatch.setattr(mod, "post", post)
    assert mod.main([]) == 0
    assert json.loads(state.read_text()) == {"42": "abc12345"}
    post.assert_not_called()


def test_cancelled_nightly_is_silent():
    mod = module("himalaia_nightly_alert")
    assert not mod.failed_nightly(
        [
            {
                "run": 44,
                "task": 1,
                "status": "cancelled",
                "sha": "abc12345",
                "job": "Backend Nightly Suite",
            }
        ]
    )


def test_failed_nightly_sent_once(tmp_path, monkeypatch):
    mod = module("himalaia_nightly_alert")
    monkeypatch.setattr(mod, "STATE", tmp_path / "state.json")
    hit = {
        "run": 45,
        "sha": "abc12345",
        "jobs": ["Backend Nightly Suite"],
        "tasks": {"Backend Nightly Suite": 1},
    }
    monkeypatch.setattr(mod, "fetch", lambda _: [])
    monkeypatch.setattr(mod, "newest_finished", lambda _: hit)
    monkeypatch.setattr(mod, "fetch_first_failure", lambda _: "FAILED test_synthetic")
    post = Mock(return_value=True)
    monkeypatch.setattr(mod, "post", post)
    assert mod.main([]) == mod.main([]) == 0
    assert post.call_count == 1
    assert "FIRING" in post.call_args.args[0]["title"]


def test_green_dry_run_preserves_state(tmp_path, monkeypatch):
    mod = module("himalaia_nightly_alert")
    state = tmp_path / "state.json"
    state.write_text('{"_open":42,"_start":"yesterday"}')
    monkeypatch.setattr(mod, "STATE", state)
    monkeypatch.setattr(mod, "fetch", lambda _: [])
    monkeypatch.setattr(mod, "newest_finished", lambda _: {"run": 43, "jobs": []})
    assert mod.main(["--dry-run"]) == 0
    assert json.loads(state.read_text())["_open"] == 42


def test_workflow_owner_disables_relay(monkeypatch):
    mod = module("himalaia_nightly_alert")
    monkeypatch.setenv("HIMALAIA_NIGHTLY_ALERT_OWNER", "workflow")
    fetch = Mock(side_effect=AssertionError("Relay must not query CI"))
    monkeypatch.setattr(mod, "fetch", fetch)
    assert mod.main([]) == 0
    fetch.assert_not_called()


def test_cancelled_run_preserves_open_marker(tmp_path, monkeypatch):
    mod = module("himalaia_nightly_alert")
    state = tmp_path / "state.json"
    state.write_text('{"_open":42}')
    monkeypatch.setattr(mod, "STATE", state)
    rows = [
        {
            "run": 44,
            "task": 1,
            "status": "cancelled",
            "sha": "abc12345",
            "job": "Backend Nightly Suite",
        }
    ]
    monkeypatch.setattr(mod, "fetch", lambda _: rows)
    assert mod.main([]) == 0
    assert json.loads(state.read_text()) == {"_open": 42}
