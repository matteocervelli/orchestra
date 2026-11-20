"""Regression cases from the promotion security review."""

import asyncio
import json
from pathlib import Path

import pytest
from test_lock_metadata import PNPMLOCK, js_manifests, metadata_profile
from test_process import protocol_launch
from test_profile import document, load

from orchestra.security.js_metadata import validate_js
from orchestra.security.profile import ProfileError


@pytest.mark.parametrize(
    "url",
    [
        "https://unapproved.invalid/foo.tgz",
        "https://registry.npmjs.org.evil.invalid/foo.tgz",
        "https://registry.npmjs.org:444/foo.tgz",
    ],
)
def test_pnpm_tarball_must_use_profile_registry(tmp_path: Path, url: str) -> None:
    raw = PNPMLOCK.replace(b"integrity: synthetic", f"tarball: {url}".encode())
    with pytest.raises(ProfileError, match="unsupported_dependency_source"):
        validate_js(
            js_manifests(), "dashboard/pnpm-lock.yaml", raw, metadata_profile(tmp_path)
        )


@pytest.mark.parametrize(
    "limit,value", [("yaml_depth", 1), ("yaml_nodes", 3), ("blob_bytes", 64)]
)
def test_js_parser_honors_smaller_profile_limits(
    tmp_path: Path, limit: str, value: int
) -> None:
    data = document()
    data["source_bindings"]["js_overrides"] = [
        ["dashboard", "devDependencies", "vite", "^6", "vite@>=6 <7", "6.4.4", "6.4.4"]
    ]
    data["limits"][limit] = value
    with pytest.raises(ProfileError):
        validate_js(
            js_manifests(), "dashboard/pnpm-lock.yaml", PNPMLOCK, load(tmp_path, data)
        )


def test_npm_resolved_url_must_use_profile_registry(tmp_path: Path) -> None:
    manifests = {
        "package.json": (
            b'{"name":"root","version":"1.0.0","dependencies":{"foo":"1.2.3"}}'
        )
    }
    lock = {
        "lockfileVersion": 3,
        "packages": {
            "": json.loads(manifests["package.json"]),
            "node_modules/foo": {
                "version": "1.2.3",
                "resolved": "https://unapproved.invalid/foo.tgz",
            },
        },
    }
    with pytest.raises(ProfileError, match="unsupported_dependency_source"):
        validate_js(
            manifests,
            "package-lock.json",
            json.dumps(lock).encode(),
            metadata_profile(tmp_path),
        )


def test_protocol_io_value_error_reaps_child_and_closes_pipes(
    tmp_path: Path, monkeypatch
) -> None:
    import orchestra.security.process as target

    processes = []
    popen = target.subprocess.Popen

    def spawn(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    def fail(*args):
        raise ValueError("protocol_io_failed")

    monkeypatch.setattr(target.subprocess, "Popen", spawn)
    monkeypatch.setattr(target, "_ProtocolIO", fail)
    try:
        with pytest.raises(ValueError, match="protocol_io_failed"):
            asyncio.run(
                target.run_protocol(
                    protocol_launch(tmp_path, "import time;time.sleep(30)")
                )
            )
        assert len(processes) == 1
        process = processes[0]
        assert process.poll() is not None
        assert all(
            stream.closed for stream in (process.stdin, process.stdout, process.stderr)
        )
    finally:
        for process in processes:
            target._terminate(process)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()


@pytest.mark.parametrize("name", [".env.local", ".env.production"])
def test_dotenv_variants_in_excluded_scope_block(tmp_path: Path, name: str) -> None:
    from test_inventory import GIT, git, repository

    from orchestra.security.inventory import capture_inventory

    repo, base = repository(tmp_path)
    (repo / "excluded").mkdir()
    (repo / "excluded" / name).write_text("SYNTHETIC=value\n")
    git(repo, "-c", "core.excludesFile=/dev/null", "add", "-A")
    git(repo, "commit", "--quiet", "-m", "dotenv variant")
    data = document()
    data["exclusions"] = [".git", ".worktrees", "excluded"]
    folder = tmp_path / "profile"
    folder.mkdir()
    with pytest.raises(ProfileError, match="coverage_gap"):
        capture_inventory(
            repo,
            git(repo, "rev-parse", "HEAD").decode().strip(),
            base,
            load(folder, data),
            GIT,
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://registry.npmjs.org:abc/foo.tgz",
        "https://registry.npmjs.org:99999/foo.tgz",
        "https://[invalid/foo.tgz",
        42,
        None,
    ],
)
def test_malformed_registry_values_never_escape_as_native_errors(
    tmp_path: Path, url: object
) -> None:
    import yaml

    lock = yaml.safe_load(PNPMLOCK)
    lock["packages"]["foo@1.2.3"]["resolution"]["tarball"] = url
    with pytest.raises(ProfileError):
        validate_js(
            js_manifests(),
            "dashboard/pnpm-lock.yaml",
            yaml.safe_dump(lock).encode(),
            metadata_profile(tmp_path),
        )


def test_inventory_accepts_history_larger_than_old_capture_limit(
    tmp_path: Path,
) -> None:
    import subprocess

    from test_inventory import GIT, git, repository

    from orchestra.security.inventory import capture_inventory

    repo, base = repository(tmp_path)
    branch = git(repo, "symbolic-ref", "HEAD").decode().strip()
    original = git(repo, "rev-parse", "HEAD:unchanged.py").decode().strip()
    stream = bytearray()
    count = 52000
    for index in range(1, count + 1):
        content = f"unique-{index}".encode()
        stream.extend(
            f"blob\nmark :{index}\ndata {len(content)}\n".encode() + content + b"\n"
        )
    stream.extend(
        (
            f"commit {branch}\n"
            "committer Fixture <fixture@example.invalid> 1 +0000\n"
            f"data 4\nwide\nfrom {base}\n"
        ).encode()
    )
    for index in range(1, count + 1):
        stream.extend(f"M 100644 :{index} historical-{index}.md\n".encode())
    stream.extend(
        (
            f"\ncommit {branch}\n"
            "committer Fixture <fixture@example.invalid> 2 +0000\n"
            f"data 6\nnarrow\ndeleteall\nM 100644 {original} unchanged.py\n\ndone\n"
        ).encode()
    )
    subprocess.run(
        [
            str(GIT),
            "-c",
            "core.hooksPath=/dev/null",
            "fast-import",
            "--quiet",
            "--done",
        ],
        cwd=repo,
        input=stream,
        check=True,
        capture_output=True,
    )
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    assert len(git(repo, "rev-list", "--objects", "--no-object-names", head)) > 2097152
    folder = tmp_path / "profile"
    folder.mkdir()
    inventory = capture_inventory(repo, head, head, load(folder, document()), GIT)
    assert [item.path for item in inventory.files] == ["unchanged.py"]


def test_inventory_accepts_maximum_path_in_tree_and_nul_diff(tmp_path: Path) -> None:
    from test_inventory import GIT, git, repository

    from orchestra.security.inventory import capture_inventory

    repo, base = repository(tmp_path)
    name = "a" * 250 + "/" + "b" * 250 + "/" + "c" * 7 + ".md"
    assert len(name.encode()) == 512
    target = repo / name
    target.parent.mkdir(parents=True)
    target.write_text("bounded input\n")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "maximum path")
    folder = tmp_path / "profile"
    folder.mkdir()
    data = document()
    data["limits"]["file_count"] = 2
    inventory = capture_inventory(
        repo,
        git(repo, "rev-parse", "HEAD").decode().strip(),
        base,
        load(folder, data),
        GIT,
    )
    assert name in inventory.changed
    assert name in {item.path for item in inventory.files}
