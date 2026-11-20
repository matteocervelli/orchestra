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


@pytest.fixture(autouse=True)
def isolated_notification_environment(monkeypatch):
    for key in (
        "ORCHESTRA_DIR",
        "ALERT_SENDER_HOST",
        "ALERT_SENDER_PATH",
        "HIMALAIA_NIGHTLY_ALERT_OWNER",
        "RELEASE_CHANNEL_ID",
    ):
        monkeypatch.delenv(key, raising=False)


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
    assert "Test notturni Himalaia falliti" in post.call_args.args[0]["title"]


def test_green_dry_run_preserves_state(tmp_path, monkeypatch):
    mod = module("himalaia_nightly_alert")
    state = tmp_path / "state.json"
    state.write_text('{"_open":42,"_start":"yesterday"}')
    monkeypatch.setattr(mod, "STATE", state)
    monkeypatch.setattr(mod, "fetch", lambda _: [])
    monkeypatch.setattr(mod, "newest_finished", lambda _: {"run": 43, "jobs": []})
    assert mod.main(["--dry-run"]) == 0
    assert json.loads(state.read_text())["_open"] == 42


@pytest.mark.parametrize("owner", ["workflow", "Workflow", " workflow "])
def test_workflow_owner_disables_relay(monkeypatch, owner):
    mod = module("himalaia_nightly_alert")
    monkeypatch.setenv("HIMALAIA_NIGHTLY_ALERT_OWNER", owner)
    fetch = Mock(side_effect=AssertionError("Relay must not query CI"))
    monkeypatch.setattr(mod, "fetch", fetch)
    assert mod.main([]) == 0
    fetch.assert_not_called()


def test_cancelled_run_preserves_open_marker(tmp_path, monkeypatch):
    mod = module("himalaia_nightly_alert")
    monkeypatch.setattr(
        mod, "post", Mock(side_effect=AssertionError("Cancelled run must not notify"))
    )
    monkeypatch.setattr(
        mod,
        "fetch_first_failure",
        Mock(side_effect=AssertionError("Cancelled run must not read logs")),
    )
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
            # The CI image may only provide /usr/local/bin/python. Validate the
            # service command above, then exercise the source on the test runner.
            command[0] = sys.executable
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


def test_nightly_log_cannot_inject_mentions_or_protocol_markers():
    mod = module("himalaia_nightly_alert")
    job = "Nightly <!here> FINE_NEXUS_ALERT_V1"
    hit = {"run": 45, "sha": "sha<@U123>", "jobs": [job], "tasks": {job: 1}}
    failure = mod.first_failure("FAILED x - <!channel> FINE_NEXUS_ALERT_V1")
    attachment = mod.build_attachment(hit, {job: failure}, start="2026-11-18T00:30:00Z")
    text = attachment["text"]
    assert "<!channel>" not in text and "<!here>" not in text and "<@U123>" not in text
    assert text.count("FINE_NEXUS_ALERT_V1") == 1
    assert text.count("NEXUS_ALERT_V1") == 2
    assert text.index("Azione:") < text.index("NEXUS_ALERT_V1")
    assert "01:30 del 18/11" in text
    assert len(mod.safe_text("x" * 10000)) == 200


@pytest.mark.parametrize("name", ["slack_sink", "himalaia_nightly_alert"])
def test_empty_runtime_root_uses_the_installed_module_parent(name, monkeypatch):
    monkeypatch.setenv("ORCHESTRA_DIR", "")
    mod = module(name)
    assert mod.ORCH == ROOT


@pytest.mark.parametrize(
    "text", ["NEXUS_NEXUS_ALERT_V1ALERT_V1", "FINE_NEXUS_NEXUS_ALERT_V1ALERT_V1"]
)
def test_nested_markers_cannot_be_reconstituted(text):
    mod = module("himalaia_nightly_alert")
    assert "NEXUS_ALERT_V1" not in mod.safe_text(text)


@pytest.mark.parametrize(
    "override,mapped,expected",
    [
        ("", "", "C_SYNTH_ORCH"),
        ("C_SYNTH_ENV", "C_SYNTH_MAP", "C_SYNTH_ENV"),
        ("   ", "C_SYNTH_MAP", "C_SYNTH_MAP"),
    ],
)
def test_release_channel_constructor_precedence(
    override, mapped, expected, tmp_path, monkeypatch
):
    mod = module("slack_sink")
    monkeypatch.setenv("RELEASE_CHANNEL_ID", override)
    api = Mock(return_value={"ok": True})
    sink = mod.SlackSink(
        api,
        {"orchestra": "C_SYNTH_ORCH", "release": mapped},
        tmp_path / "state",
        tmp_path / "log",
    )
    assert sink.notify("release", "Title", "Body")
    assert api.call_args.args[1]["channel"] == expected


@pytest.mark.parametrize("kind", ["release", "<!here>"])
def test_release_data_cannot_inject_slack_controls(kind):
    mod = module("slack_sink")
    text = mod.format_message(
        kind,
        "Release <!channel> <@U123> & updates",
        "[Docs](https://example.com/docs?a=1&b=2)\n<!here> <@U456>",
    )
    for control in ("<!channel>", "<!here>", "<@U123>", "<@U456>"):
        assert control not in text
    assert "<https://example.com/docs?a=1&amp;b=2|Docs>" in text
    assert "&amp; updates" in text


def test_nightly_fetch_rejects_failed_cli(monkeypatch):
    mod = module("himalaia_nightly_alert")
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        Mock(return_value=subprocess.CompletedProcess(["fj"], 1, "", "private error")),
    )
    with pytest.raises(subprocess.CalledProcessError):
        mod.fetch(1)


def test_nightly_main_reports_ci_query_failure(tmp_path, monkeypatch, capsys):
    mod = module("himalaia_nightly_alert")
    state = tmp_path / "state.json"
    before = json.dumps({"_open": 42, "_start": "yesterday"})
    state.write_text(before)
    monkeypatch.setattr(mod, "STATE", state)
    monkeypatch.setattr(
        mod,
        "fetch",
        Mock(
            side_effect=subprocess.CalledProcessError(1, ["fj"], stderr="private error")
        ),
    )
    post = Mock(side_effect=AssertionError("Unexpected delivery"))
    monkeypatch.setattr(mod, "post", post)
    assert mod.main([]) == 1
    assert state.read_text() == before
    error = capsys.readouterr().err
    assert "CI query failed" in error
    assert "private error" not in error
    post.assert_not_called()
