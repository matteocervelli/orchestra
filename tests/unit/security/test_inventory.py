"""Actual pinned-tree inventory, never display-name or mutable-ref authority."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
from test_profile import document, load

from orchestra.security.inventory import capture_inventory
from orchestra.security.profile import ProfileError
from orchestra.security.request import verify_request

GIT = Path(shutil.which("git") or "/usr/bin/git").resolve()


@pytest.mark.parametrize(
    "manifest",
    [
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
        "requirements-dev.txt",
        "requirements-prod.txt",
        "pylock.toml",
        "pylock.dev.toml",
        "Cargo.toml",
        "Cargo.lock",
        "go.mod",
        "go.sum",
        "Gemfile",
        "Gemfile.lock",
        "composer.json",
        "composer.lock",
        "yarn.lock",
        "bun.lock",
        "bun.lockb",
        "poetry.lock",
        "Pipfile",
        "Pipfile.lock",
        "requirements.txt",
        "setup.py",
        "setup.cfg",
    ],
)
def test_unsupported_manifest_cannot_be_dependency_na(
    tmp_path: Path, manifest: str
) -> None:
    from orchestra.security.inventory import _workspaces

    repo, base = repository(tmp_path)
    (repo / manifest).write_text("synthetic unsupported input\n")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "unsupported")
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    folder = tmp_path / "profile"
    folder.mkdir()
    profile = load(folder, document())
    inventory = capture_inventory(repo, head, base, profile, GIT)
    with pytest.raises(ProfileError, match="unsupported_stack_or_lock"):
        _workspaces(inventory, profile)


def test_excluded_literal_env_change_is_a_coverage_gap(tmp_path: Path) -> None:
    repo, base = repository(tmp_path)
    (repo / "excluded").mkdir()
    (repo / "excluded/.env").write_text("SYNTHETIC_CANARY=value\n")
    git(repo, "add", "--force", "excluded/.env")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "dotfile")
    folder = tmp_path / "profile"
    folder.mkdir()
    data = document()
    data["exclusions"] = [".git", ".worktrees", "excluded"]
    with pytest.raises(ProfileError, match="coverage_gap"):
        capture_inventory(
            repo,
            git(repo, "rev-parse", "HEAD").decode().strip(),
            base,
            load(folder, data),
            GIT,
        )


@pytest.mark.parametrize(
    "kind",
    [
        "replace",
        "promisor",
        "partial",
        "alternates",
        "missing-history",
        "promisor-pack",
        "include",
        "grafts",
        "filter",
    ],
)
def test_git_must_be_local_complete_and_unreplaced(tmp_path: Path, kind: str) -> None:
    repo, base = repository(tmp_path)
    (repo / "unchanged.py").write_text("value = 2\n")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "intermediate")
    middle = git(repo, "rev-parse", "HEAD").decode().strip()
    historical = git(repo, "rev-parse", "HEAD:unchanged.py").decode().strip()
    (repo / "unchanged.py").write_text("value = 3\n")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "head")
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    if kind == "replace":
        git(repo, "replace", middle, base)
    elif kind == "promisor":
        git(repo, "config", "remote.synthetic.promisor", "true")
        git(
            repo,
            "config",
            "remote.synthetic.url",
            "https://invalid.example.invalid/no-network",
        )
    elif kind == "partial":
        git(repo, "config", "extensions.partialClone", "synthetic")
    elif kind == "alternates":
        (repo / ".git/objects/info/alternates").write_text(
            str(repo / ".git/objects") + "\n"
        )
    elif kind == "promisor-pack":
        (repo / ".git/objects/pack/synthetic.promisor").write_bytes(b"")
    elif kind == "include":
        git(repo, "config", "include.path", "/synthetic/not-read")
    elif kind == "grafts":
        (repo / ".git/info").mkdir(exist_ok=True)
        (repo / ".git/info/grafts").write_text(head + "\n")
    elif kind == "filter":
        git(repo, "config", "filter.synthetic.clean", "synthetic-must-not-execute")
    else:
        (repo / ".git/objects" / historical[:2] / historical[2:]).unlink()
    profile_root = tmp_path / "profile"
    profile_root.mkdir()
    with pytest.raises(ProfileError, match="coverage_gap"):
        capture_inventory(repo, head, base, load(profile_root, document()), GIT)


def test_git_protocol_denial_overrides_local_allow_without_running_helper(
    tmp_path: Path,
) -> None:
    import sys

    from orchestra.security.inventory import git_bytes

    repo, _ = repository(tmp_path)
    marker = tmp_path / "transport-executed"
    helper = tmp_path / "helper.py"
    helper.write_text(
        "from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n"
    )
    url = "ext::" + str(Path(sys.executable).resolve()) + " " + str(helper)
    with pytest.raises(ProfileError, match="scope_drift"):
        git_bytes(repo, GIT, ("-c", "protocol.ext.allow=always", "ls-remote", url))
    assert not marker.exists()


def test_private_request_rejects_unknown_fields_before_git(tmp_path: Path) -> None:
    profile_root = tmp_path / "profile"
    profile_root.mkdir()
    with pytest.raises(ProfileError):
        verify_request(
            b'{"schema":"orchestra.security-request/v1","unexpected":true}',
            load(profile_root, document()),
        )


def git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        [
            str(GIT),
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return result.stdout


def repository(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "--quiet")
    (repo / "unchanged.py").write_text("value = 1\n")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "base")
    return repo, git(repo, "rev-parse", "HEAD").decode().strip()


def test_inventory_uses_blob_hashes_and_nul_change_records(tmp_path: Path) -> None:
    repo, base = repository(tmp_path)
    (repo / "unchanged.py").rename(repo / "renamed with spaces:ok.py")
    (repo / "nested").mkdir()
    (repo / "nested/new.py").write_text("value = 2\n")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "result")
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    profile_root = tmp_path / "profile"
    profile_root.mkdir()
    inventory = capture_inventory(repo, head, base, load(profile_root, document()), GIT)
    assert inventory.head_sha == head and inventory.base_sha == base
    assert inventory.changed == (
        "nested/new.py",
        "renamed with spaces:ok.py",
        "unchanged.py",
    )
    assert tuple(f.path for f in inventory.files) == (
        "nested/new.py",
        "renamed with spaces:ok.py",
    )
    assert inventory.files[0].sha256 == hashlib.sha256(b"value = 2\n").hexdigest()
    assert inventory.content("nested/new.py") == b"value = 2\n"
    assert str(repo) not in repr(inventory)


@pytest.mark.parametrize(
    "kind",
    ["dirty", "untracked", "symlink", "gitlink", "control", "excluded", "file-limit"],
)
def test_inventory_unsafe_or_omitted_scope_blocks(tmp_path: Path, kind: str) -> None:
    repo, base = repository(tmp_path)
    data = document()
    if kind == "dirty":
        (repo / "unchanged.py").write_text("dirty\n")
    elif kind == "untracked":
        (repo / "unknown").write_text("untracked")
    elif kind == "symlink":
        (repo / "alias.py").symlink_to("unchanged.py")
    elif kind == "gitlink":
        git(repo, "update-index", "--add", "--cacheinfo", f"160000,{base},child")
    elif kind == "control":
        (repo / "bad\nname.py").write_text("bad")
    elif kind == "excluded":
        data["exclusions"] = [".git", ".worktrees", "excluded"]
        (repo / "excluded").mkdir()
        (repo / "excluded/file.py").write_text("changed")
    else:
        data["limits"]["file_count"] = 1
        (repo / "second.py").write_text("second")
    if kind not in {"dirty", "untracked"}:
        if kind != "gitlink":
            git(repo, "add", "-A")
        git(repo, "commit", "--quiet", "-m", "unsafe")
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    profile_root = tmp_path / "profile"
    profile_root.mkdir()
    with pytest.raises(ProfileError):
        capture_inventory(repo, head, base, load(profile_root, data), GIT)


def test_replay_wrong_head_and_worktree_hash_drift_block(tmp_path: Path) -> None:
    repo, base = repository(tmp_path)
    profile_root = tmp_path / "profile"
    profile_root.mkdir()
    profile = load(profile_root, document())
    with pytest.raises(ProfileError, match="scope_drift"):
        capture_inventory(repo, "f" * 40, base, profile, GIT)
    before = capture_inventory(repo, base, base, profile, GIT)
    (repo / "unchanged.py").write_text("drift\n")
    with pytest.raises(ProfileError, match="scope_drift"):
        before.verify_worktree(repo)
