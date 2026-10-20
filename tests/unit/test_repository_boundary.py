from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_TRACKED = {
    "STATE.md",
    "continuation.md",
    "ledger.jsonl",
    "queue.json",
}
FORBIDDEN_PARTS = {"answers", "credentials", "logs", "pages", "scratch", "sessions"}


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=False,
        capture_output=True,
        text=True,
    )


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
    result = git("ls-files", "-z")
    assert result.returncode == 0
    tracked = [Path(path) for path in result.stdout.split("\0") if path]
    violations = [
        str(path)
        for path in tracked
        if path.name in FORBIDDEN_TRACKED or FORBIDDEN_PARTS.intersection(path.parts)
    ]
    assert violations == []


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
