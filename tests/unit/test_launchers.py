from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPAWN = ROOT / "scripts" / "spawn.sh"
AUTOSPAWN = ROOT / "scripts" / "autospawn.sh"


def run(
    script: Path, *args: str, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *args],
        env={**os.environ, **env},
        check=False,
        capture_output=True,
        text=True,
    )


def test_spawn_rejects_unknown_tool_without_side_effects(tmp_path: Path) -> None:
    result = run(
        SPAWN,
        "slug",
        "unknown",
        "model",
        "high",
        str(tmp_path),
        str(tmp_path / "task.md"),
        env={"ORCHESTRA_ROOT": str(tmp_path)},
    )
    assert result.returncode == 2
    assert "unsupported tool" in result.stderr
    assert not (tmp_path / "logs").exists()


def test_spawn_preserves_metadata_with_fake_tmux(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    (fake_bin / "timeout").write_text('#!/bin/sh\nshift\nexec "$@"\n')
    (fake_bin / "tmux").write_text(
        "#!/bin/sh\n"
        'if [ "$1" = list-windows ]; then echo 7; exit 0; fi\n'
        'printf \'%s\\n\' "$*" >> "$TMUX_CAPTURE"\n'
    )
    for path in fake_bin.iterdir():
        path.chmod(0o755)
    task = tmp_path / "task with spaces.md"
    task.write_text("task")
    capture = tmp_path / "tmux.txt"
    result = run(
        SPAWN,
        "safe-slug",
        "codex",
        "gpt-test",
        "high",
        str(tmp_path),
        str(task),
        env={
            "ORCHESTRA_ROOT": str(tmp_path),
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "TMUX_CAPTURE": str(capture),
        },
    )
    assert result.returncode == 0, result.stderr
    [row] = [
        json.loads(line)
        for line in (tmp_path / "logs" / "spawns.jsonl").read_text().splitlines()
    ]
    assert row | {"start": row["start"]} == {
        "slug": "safe-slug",
        "tool": "codex",
        "model": "gpt-test",
        "effort": "high",
        "workdir": str(tmp_path),
        "task": str(task),
        "start": row["start"],
    }
    assert "new-window" in capture.read_text()


def test_autospawn_one_cycle_consumes_queue_and_tracks_child(tmp_path: Path) -> None:
    (tmp_path / "scratch").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scratch" / "running.txt").write_text("")
    (tmp_path / "scratch" / "spawn-cap").write_text("2\n")
    (tmp_path / "scratch" / "spawn-queue.txt").write_text(
        "child codex gpt-test high /tmp task.md\n"
    )
    (tmp_path / "scripts" / "spawn.sh").write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$*" > "$ORCHESTRA_ROOT/spawn.args"\n'
    )
    (tmp_path / "scripts" / "spawn.sh").chmod(0o755)

    result = run(
        AUTOSPAWN,
        env={
            "ORCHESTRA_ROOT": str(tmp_path),
            "ORCHESTRA_ONCE": "1",
            "ORCHESTRA_POLL_SECONDS": "0",
        },
    )
    assert result.returncode == 0, result.stderr
    assert (
        (tmp_path / "spawn.args")
        .read_text()
        .strip()
        .endswith(f"/tmp {tmp_path}/task.md")
    )
    assert (tmp_path / "scratch" / "running.txt").read_text().split() == ["child"]
    assert (tmp_path / "scratch" / "spawn-queue.txt").read_text() == ""
