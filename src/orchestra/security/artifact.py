"""Complete pure-Python producer artifact verification, never editable imports."""

from __future__ import annotations

import hashlib
import sys
import sysconfig
from dataclasses import dataclass, field
from pathlib import Path

from orchestra.security.profile import (
    ProfileError,
    canonical,
    decode_json,
    exact,
    hex_digest,
    read_regular,
    require,
    safe_path,
)

MANIFEST = "producer-manifest.json"
_FORBIDDEN = {".pth", ".pyc", ".pyo", ".so", ".pyd", ".dll", ".dylib"}


@dataclass(frozen=True)
class ArtifactFile:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class ProducerArtifact:
    root: Path = field(repr=False)
    digest: str
    revision: str
    files: tuple[ArtifactFile, ...] = field(repr=False)


def _tree(root: Path) -> set[str]:
    require(root.is_absolute() and not root.is_symlink(), "configuration_drift")
    require(all(not p.is_symlink() for p in root.parents), "configuration_drift")
    result = set()
    for count, path in enumerate(root.rglob("*"), start=1):
        require(count <= 10000, "scope_overflow")
        relative = safe_path(path.relative_to(root).as_posix())
        require(
            not path.is_symlink()
            and "__pycache__" not in path.parts
            and path.suffix not in _FORBIDDEN,
            "configuration_drift",
        )
        if path.is_file():
            result.add(relative)
        else:
            require(path.is_dir(), "configuration_drift")
    return result


def verify_artifact(
    root: Path, expected_digest: str, revision: str
) -> ProducerArtifact:
    hex_digest(expected_digest)
    hex_digest(revision, 40)
    try:
        actual_files = _tree(root)
        raw = read_regular(root, MANIFEST, 2097152)
        manifest = exact(decode_json(raw, 2097152), {"format", "revision", "files"})
        require(
            manifest["format"] == "orchestra.producer-artifact/v1"
            and manifest["revision"] == revision,
            "configuration_drift",
        )
        require(
            raw == canonical(manifest)
            and hashlib.sha256(raw).hexdigest() == expected_digest,
            "configuration_drift",
        )
        require(
            type(manifest["files"]) is list and len(manifest["files"]) <= 10000,
            "scope_overflow",
        )
        files = tuple(_file(root, item) for item in manifest["files"])
        paths = [f.path for f in files]
        require(
            paths == sorted(set(paths), key=lambda p: p.encode())
            and set(paths) == actual_files - {MANIFEST},
            "configuration_drift",
        )
        required = {
            "bootstrap.py",
            "orchestra/__init__.py",
            "orchestra/security/__init__.py",
            "orchestra/security/runtime.py",
            "packaging/__init__.py",
            "yaml/__init__.py",
            "licenses/packaging.txt",
            "licenses/yaml.txt",
            "source-provenance.json",
        }
        require(required <= set(paths), "configuration_drift")
        provenance = decode_json(read_regular(root, "source-provenance.json", 65536))
        require(
            provenance
            == {
                "schema": "orchestra.parser-provenance/v1",
                "packaging": "26.3",
                "PyYAML": "6.0.3",
            },
            "configuration_drift",
        )
        return ProducerArtifact(
            root=root, digest=expected_digest, revision=revision, files=files
        )
    except OSError:
        raise ProfileError("configuration_drift") from None


def _file(root: Path, value: object) -> ArtifactFile:
    item = exact(value, {"path", "sha256", "size"})
    path, sha, size = safe_path(item["path"]), hex_digest(item["sha256"]), item["size"]
    require(
        path != MANIFEST and type(size) is int and 0 <= size <= 4194304,
        "configuration_drift",
    )
    raw = read_regular(root, path, 4194304)
    require(
        len(raw) == size and hashlib.sha256(raw).hexdigest() == sha,
        "configuration_drift",
    )
    return ArtifactFile(path=path, sha256=sha, size=size)


def _stdlib_origin(path: Path, stdlib: Path) -> bool:
    return path.is_relative_to(stdlib) and not {
        "site-packages",
        "dist-packages",
    }.intersection(path.parts)


def _verify_origin(
    name: str, module: object, root: Path, allowed: set[Path], stdlib: Path
) -> None:
    origin = getattr(getattr(module, "__spec__", None), "origin", None)
    if origin is None:
        require(
            name == "__main__" or name.split(".")[0] in sys.stdlib_module_names,
            "configuration_drift",
        )
        return
    if origin in {"built-in", "frozen"}:
        return
    if not isinstance(origin, str):
        raise ProfileError("configuration_drift")
    origin_path = Path(origin)
    if _stdlib_origin(origin_path, stdlib):
        require(not origin_path.is_relative_to(root), "configuration_drift")
        return
    require(
        name.split(".")[0] in {"orchestra", "packaging", "yaml"}
        and Path(origin) in allowed
        and Path(origin).suffix == ".py",
        "configuration_drift",
    )


def verify_loaded_origins(artifact: ProducerArtifact) -> None:
    """Every non-stdlib origin must be an exact digest-listed parser/producer file."""
    allowed = {artifact.root / f.path for f in artifact.files}
    stdlib = Path(sysconfig.get_path("stdlib"))
    for name, module in tuple(sys.modules.items()):
        if module is None:
            continue
        _verify_origin(name, module, artifact.root, allowed, stdlib)
    import packaging
    import yaml  # type: ignore[import-untyped]

    require(
        packaging.__version__ == "26.3"
        and yaml.__version__ == "6.0.3"
        and yaml.__with_libyaml__ is False,
        "configuration_drift",
    )
