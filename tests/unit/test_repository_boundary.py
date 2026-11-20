from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

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
    names = {path.name for path in workflow_root.glob("*.y*ml")}
    assert names == {"ci.yml", "ci-test.yml", "ci-test-push.yml"}
    github_workflows = ROOT / ".github" / "workflows"
    assert not github_workflows.exists() or not list(github_workflows.glob("*.y*ml"))


@pytest.mark.parametrize(
    ("filename", "job", "library", "events"),
    [
        ("ci.yml", "quality", "lib-py-ci.yml", {"push", "pull_request"}),
        ("ci-test.yml", "tests", "lib-py-ci-test.yml", {"pull_request"}),
        ("ci-test-push.yml", "tests", "lib-py-ci-test.yml", {"push"}),
    ],
)
def test_forgejo_ci_callers_are_bounded_and_pinned(
    filename: str, job: str, library: str, events: set[str]
) -> None:
    workflow = ROOT / ".forgejo" / "workflows" / filename
    source = workflow.read_text(encoding="utf-8")
    triggers, jobs = source.split("\njobs:\n")
    assert set(re.findall(r"(?m)^  (\w+):$", triggers)) == events
    branch_mapping = dict(
        re.findall(r"(?m)^  (\w+):\n    branches: \[(.+)\]$", triggers)
    )
    assert branch_mapping == {
        event: "main" if event == "push" else "main, auto/integration"
        for event in events
    }
    assert re.findall(r"(?m)^  (\w+):$", jobs) == [job]
    pins = [line.strip() for line in source.splitlines() if "uses:" in line]
    assert pins == [
        f"uses: matteocervelli/adlimen-cicd/.forgejo/workflows/{library}@v3.6.0"
    ]
    assert not re.search(r"(?m)^\s*(?:run|steps):", jobs)
    if job == "tests":
        assert re.findall(r"caller_event_name: (\w+)", jobs) == sorted(events)
