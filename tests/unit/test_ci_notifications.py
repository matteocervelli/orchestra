"""Offline contracts for the operational notification sources."""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
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


@pytest.mark.parametrize("kind", ["release", "deploy"])
def test_builtin_release_channel(kind, tmp_path, monkeypatch):
    mod = module("slack_sink")
    monkeypatch.delenv("RELEASE_CHANNEL_ID", raising=False)
    api = Mock(return_value={"ok": True})
    sink = mod.SlackSink(
        api, {"orchestra": "C_SYNTH_ORCH"}, tmp_path / "state", tmp_path / "log"
    )
    assert sink.notify(kind, "Titolo", "Corpo")
    assert api.call_args.args[1]["channel"] == "C0CAEALG03V"


@pytest.mark.parametrize("kind", ["release", "deploy"])
@pytest.mark.parametrize(
    "error", ["not_in_channel", "is_archived", "channel_not_found"]
)
def test_unavailable_release_retries_once_on_orchestra(
    kind, error, tmp_path, monkeypatch
):
    mod = module("slack_sink")
    monkeypatch.delenv("RELEASE_CHANNEL_ID", raising=False)
    api = Mock(side_effect=[{"ok": False, "error": error}, {"ok": True}])
    sink = mod.SlackSink(
        api,
        {"orchestra": "C_SYNTH_ORCH", "release": "C_SYNTH_REL"},
        tmp_path / "state",
        tmp_path / "log",
    )
    assert sink.notify(kind, "Titolo", "Corpo")
    assert [call.args[1]["channel"] for call in api.call_args_list] == [
        "C_SYNTH_REL",
        "C_SYNTH_ORCH",
    ]
    assert "ripiego su #orchestra" in api.call_args.args[1]["text"]
    assert error in (tmp_path / "log").read_text()


@pytest.mark.parametrize("error", ["invalid_auth", "not_in_channel"])
def test_release_failure_does_not_loop(error, tmp_path):
    mod = module("slack_sink")
    api = Mock(return_value={"ok": False, "error": error})
    sink = mod.SlackSink(
        api,
        {"orchestra": "C_SYNTH_ORCH", "release": "C_SYNTH_REL"},
        tmp_path / "state",
        tmp_path / "log",
        sleep=lambda _: None,
    )
    assert not sink.notify("release", "Titolo", "Corpo")
    assert api.call_count == (2 if error == "not_in_channel" else 1)


def test_nightly_start_from_other_directory(tmp_path):
    # No real CLI, network, relay or Slack call: the fixture fails closed on delivery.
    runtime = tmp_path / "runtime"
    (runtime / "bin").mkdir(parents=True)
    (runtime / "scratch").mkdir()
    (runtime / "bin/himalaia_nightly_alert.py").write_bytes(
        (ROOT / "bin/himalaia_nightly_alert.py").read_bytes()
    )
    (runtime / "bin/slack_sink.py").write_text(
        "class SlackError(Exception): pass\n"
        "class SlackSink:\n"
        " @classmethod\n"
        " def default(cls, root):\n"
        "  assert (root / 'scratch').is_dir()\n"
        "  return cls()\n"
        " def post(self, *args, **kwargs): return {'ok': True}\n"
    )
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    fj = fixture / "fj"
    fj.write_text(
        "#!/bin/sh\n"
        'if [ "$2" = tasks ]; then\n'
        " echo 'run#42 task#1 failure abc12345 Backend Nightly Suite'\n"
        "elif [ \"$2\" = log ]; then echo 'FAILED test_synthetic';\n"
        "else exit 99; fi\n"
    )
    fj.chmod(0o700)
    (fixture / "ssh").write_text("#!/bin/sh\nexit 99\n")
    (fixture / "ssh").chmod(0o700)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("ORCHESTRA_", "ALERT_SENDER_", "HIMALAIA_NIGHTLY_"))
    }
    env["PATH"] = str(fixture)
    script = runtime / "bin/himalaia_nightly_alert.py"
    for explicit in (False, True):
        if explicit:
            unit = (
                ROOT / "deploy/systemd/orchestra-himalaia-nightly-alert.service.in"
            ).read_text()
            for name, value in {
                "ORCHESTRA_DIR": str(runtime),
                "CLI_PATH": str(fixture),
                "ALERT_SENDER_HOST": "synthetic-host",
                "ALERT_SENDER_PATH": "/synthetic-sender",
            }.items():
                unit = unit.replace("@" + name + "@", value)
            for line in unit.splitlines():
                if line.startswith("Environment="):
                    key, value = shlex.split(line.removeprefix("Environment="))[
                        0
                    ].split("=", 1)
                    env[key] = value
            command = shlex.split(
                next(
                    line.removeprefix("ExecStart=")
                    for line in unit.splitlines()
                    if line.startswith("ExecStart=")
                )
            )
            assert command == ["/usr/bin/python3", str(script)]
        else:
            command = [sys.executable, str(script)]
        result = subprocess.run(
            [*command, "--pages", "1"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        state = runtime / "scratch/himalaia-nightly-alert.json"
        assert json.loads(state.read_text())["42"] == "abc12345"
        state.unlink()


def test_nightly_missing_adapter_is_reported(tmp_path, monkeypatch, capsys):
    mod = module("himalaia_nightly_alert")
    monkeypatch.setitem(sys.modules, "slack_sink", None)
    assert not mod.post_orchestra({})
    assert "ModuleNotFoundError" in capsys.readouterr().err


def test_failed_delivery_preserves_retry(tmp_path, monkeypatch):
    mod = module("himalaia_nightly_alert")
    state = tmp_path / "state.json"
    monkeypatch.setattr(mod, "STATE", state)
    monkeypatch.setattr(mod, "fetch", lambda _: [])
    monkeypatch.setattr(
        mod,
        "newest_finished",
        lambda _: {
            "run": 45,
            "sha": "abc12345",
            "jobs": ["Backend Nightly Suite"],
            "tasks": {"Backend Nightly Suite": 1},
        },
    )
    monkeypatch.setattr(mod, "fetch_first_failure", lambda _: "FAILED test_synthetic")
    post = Mock(side_effect=[False, True])
    monkeypatch.setattr(mod, "post", post)
    assert mod.main([]) == 1
    assert not state.exists()
    assert mod.main([]) == 0
    assert json.loads(state.read_text())["45"] == "abc12345"
