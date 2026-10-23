"""Installed-style artifact integrity and actual isolated bootstrap subprocesses."""

from __future__ import annotations

import hashlib
import importlib.metadata
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from orchestra.security.artifact import verify_artifact
from orchestra.security.profile import ProfileError, canonical, digest


def fixture_artifact(
    tmp_path: Path, profile_document: dict | None = None
) -> tuple[Path, str]:
    import packaging
    import yaml

    import orchestra.security

    root = tmp_path / "artifact"
    root.mkdir()
    for name, module in (("packaging", packaging), ("yaml", yaml)):
        shutil.copytree(
            Path(module.__file__).parent,
            root / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.so", "*.pyc"),
        )
        distribution = importlib.metadata.distribution(
            "PyYAML" if name == "yaml" else name
        )
        license_file = next(
            f for f in distribution.files if str(f).endswith("licenses/LICENSE")
        )
        (root / "licenses").mkdir(exist_ok=True)
        shutil.copyfile(
            distribution.locate_file(license_file), root / "licenses" / (name + ".txt")
        )
    (root / "orchestra").mkdir()
    (root / "orchestra/__init__.py").write_bytes(b"")
    source = Path(orchestra.security.__file__).parent
    shutil.copytree(
        source,
        root / "orchestra/security",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copyfile(source / "bootstrap.py", root / "bootstrap.py")
    if profile_document is not None:
        profiles = root / "orchestra/security/profiles"
        profiles.mkdir(exist_ok=True)
        (profiles / "pilot-v1.json").write_bytes(canonical(profile_document))
        (profiles / "rules.toml").write_bytes(b"")
    (root / "source-provenance.json").write_bytes(
        canonical(
            {
                "schema": "orchestra.parser-provenance/v1",
                "packaging": "26.3",
                "PyYAML": "6.0.3",
            }
        )
    )
    return root, write_manifest(root)


@pytest.mark.parametrize("kind", ["nested-manifest", "missing-bytecode-flag"])
def test_bootstrap_rejects_before_any_package_import(tmp_path: Path, kind: str) -> None:
    root, _ = fixture_artifact(tmp_path)
    marker = tmp_path / "package-imported"
    (root / "orchestra/__init__.py").write_text(
        "from pathlib import Path\nPath("
        + repr(str(marker))
        + ").write_text('loaded')\n"
    )
    expected = write_manifest(root)
    flags = ["-I", "-S", "-B"]
    if kind == "nested-manifest":
        nested = root / "nested"
        nested.mkdir()
        (nested / "producer-manifest.json").write_bytes(b"unlisted")
    else:
        flags.remove("-B")
    request = canonical({"producer_digest": expected, "producer_revision": "a" * 40})
    child = subprocess.run(
        [
            str(Path(sys.executable).resolve()),
            *flags,
            str(root / "bootstrap.py"),
            "--request-stdin",
        ],
        input=request,
        capture_output=True,
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin"},
        timeout=10,
    )
    assert child.returncode == 2 and child.stdout == b""
    assert child.stderr == b"security_bootstrap_failed\n"
    assert not marker.exists(), "package imported before complete preflight"


def write_manifest(root: Path) -> str:
    files = [
        {
            "path": p.relative_to(root).as_posix(),
            "size": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.relative_to(root).as_posix() != "producer-manifest.json"
    ]
    value = {
        "format": "orchestra.producer-artifact/v1",
        "revision": "a" * 40,
        "files": files,
    }
    (root / "producer-manifest.json").write_bytes(canonical(value))
    return digest(value)


def test_full_installed_tree_manifest_includes_real_parser_sources(
    tmp_path: Path,
) -> None:
    root, expected = fixture_artifact(tmp_path)
    artifact = verify_artifact(root, expected, "a" * 40)
    assert artifact.digest == expected
    assert any(p.path == "packaging/requirements.py" for p in artifact.files)
    assert any(p.path == "yaml/loader.py" for p in artifact.files)
    assert any(p.path == "orchestra/security/runtime.py" for p in artifact.files)
    assert str(root) not in repr(artifact)


@pytest.mark.parametrize(
    "kind",
    [
        "tamper",
        "missing",
        "extra",
        "symlink",
        "pth",
        "bytecode",
        "extension",
        "revision",
        "runtime-tamper",
        "runtime-missing",
    ],
)
def test_artifact_rejects_incomplete_or_unsafe_runtime_tree(
    tmp_path: Path, kind: str
) -> None:
    root, expected = fixture_artifact(tmp_path)
    target = root / "orchestra/security/profile.py"
    revision = "a" * 40
    if kind.startswith("runtime-"):
        target = root / "orchestra/security/runtime.py"
        if kind == "runtime-tamper":
            target.write_bytes(target.read_bytes() + b"\n# drift\n")
        else:
            target.unlink()
    elif kind == "tamper":
        target.write_bytes(target.read_bytes() + b"\n# drift\n")
    elif kind == "missing":
        target.unlink()
    elif kind == "symlink":
        target.unlink()
        target.symlink_to(root / "packaging/__init__.py")
    elif kind == "revision":
        revision = "b" * 40
    else:
        name = {
            "extra": "unlisted.json",
            "pth": "injected.pth",
            "bytecode": "injected.pyc",
            "extension": "yaml/_yaml.so",
        }[kind]
        (root / name).write_bytes(b"synthetic-canary")
        if kind != "extra":
            expected = write_manifest(root)
    with pytest.raises(ProfileError) as caught:
        verify_artifact(root, expected, revision)
    assert "synthetic-canary" not in str(caught.value) and str(root) not in str(
        caught.value
    )


def test_isolated_bootstrap_missing_b_entrypoint_is_exit2_never_success(
    tmp_path: Path,
) -> None:
    root, expected = fixture_artifact(tmp_path)
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "sitecustomize.py").write_text(
        "raise RuntimeError('candidate-loaded')"
    )
    (candidate / "orchestra.py").write_text("raise RuntimeError('candidate-loaded')")
    request = canonical({"producer_digest": expected, "producer_revision": "a" * 40})
    result = subprocess.run(
        [
            str(Path(sys.executable).resolve()),
            "-I",
            "-S",
            "-B",
            str(root / "bootstrap.py"),
            "--request-stdin",
        ],
        cwd=candidate,
        input=request,
        capture_output=True,
        env={"PYTHONPATH": str(candidate), "PATH": "/usr/bin:/bin"},
        timeout=10,
    )
    assert result.returncode == 2 and result.stdout == b""
    assert b"candidate-loaded" not in result.stderr
    assert b"Traceback" not in result.stderr and str(root).encode() not in result.stderr
