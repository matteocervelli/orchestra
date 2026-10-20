from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def ignored_tracked_paths(repository: Path) -> list[str]:
    tracked = subprocess.run(
        ["git", "-C", str(repository), "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=True,
    )
    ignored = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "check-ignore",
            "--no-index",
            "-z",
            "--stdin",
        ],
        input=tracked.stdout,
        check=False,
        capture_output=True,
        text=True,
    )
    if ignored.returncode not in {0, 1}:
        ignored.check_returncode()
    return [path for path in ignored.stdout.split("\0") if path]


def test_runtime_and_secret_paths_are_ignored() -> None:
    paths = [
        "STATE.md",
        "continuation.md",
        "ledger.jsonl",
        "queue.json",
        "logs/child.err",
        "answers/reply.json",
        "scratch/spawn-queue.txt",
        "pages/report.html",
        "sessions/native.json",
        "credentials/slack.json",
        ".env",
        "local-token.txt",
    ]
    result = git("check-ignore", "--no-index", "--stdin")
    # Invoke again with explicit input because CompletedProcess is intentionally
    # small and reusable above.
    result = subprocess.run(
        ["git", "-C", str(ROOT), "check-ignore", "--no-index", "--stdin"],
        input="\n".join(paths) + "\n",
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert set(result.stdout.splitlines()) == set(paths)


def test_no_runtime_artifact_is_tracked() -> None:
    assert ignored_tracked_paths(ROOT) == []


def test_ignore_policy_detects_force_tracked_secret(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "-C", str(repository), "init", "-q"], check=True)
    (repository / ".gitignore").write_text("*token*\n", encoding="utf-8")
    (repository / "local-token.txt").write_text("synthetic\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repository), "add", ".gitignore"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "add", "--force", "local-token.txt"],
        check=True,
    )

    assert ignored_tracked_paths(repository) == ["local-token.txt"]


def test_no_deploy_or_release_workflow_exists() -> None:
    workflow_root = ROOT / ".forgejo" / "workflows"
    names = {path.name for path in workflow_root.glob("*.yml")}
    assert names <= {"ci.yml"}
    github_workflows = ROOT / ".github" / "workflows"
    assert not github_workflows.exists() or not list(github_workflows.glob("*.yml"))


def test_forgejo_ci_is_single_and_pinned_to_approved_release() -> None:
    workflow = ROOT / ".forgejo" / "workflows" / "ci.yml"
    source = workflow.read_text(encoding="utf-8")
    pins = [line.strip() for line in source.splitlines() if "uses:" in line]
    assert len(pins) == 2
    assert all(
        "matteocervelli/adlimen-cicd/.forgejo/workflows/" in pin
        and pin.endswith("@v3.6.0")
        for pin in pins
    )
    assert "pull_request:" in source and "auto/integration" in source
    assert all(
        word not in source.lower()
        for word in ("deploy.yml", "release.yml", "publish.yml")
    )
