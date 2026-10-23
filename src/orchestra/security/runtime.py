"""Executable admission and retained runtime authority; no provisioning provider."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from orchestra.security.profile import (
    ProfileError,
    canonical,
    decode_json,
    exact,
    hex_digest,
    read_regular,
    require,
    safe_text,
)

if TYPE_CHECKING:
    from orchestra.security.request import RuntimeBindings


class RuntimeCapability(Protocol):
    """Injected verified runner authority, never a request-supplied boolean.

    No production provider is implemented here: activation requires #170's
    immutable runtime/snapshot, execution and egress capability verification.
    """

    revision: str
    digest: str

    def assert_immutable(self, path: Path) -> object:
        """Return None only after verified immutable proof; any other value blocks."""
        ...

    def candidate_can_write(self, path: Path) -> bool: ...

    def provisioning_digest(self, path: Path) -> str:
        """Verified complete runtime tree, or verified producer artifact manifest.

        Includes interpreter/stdlib/modules, not just launcher or manifest bytes.
        This trusted authority must reject unknown paths and any incomplete tree.
        """
        ...


@dataclass(frozen=True)
class FileIdentity:
    path: Path = field(repr=False)
    sha256: str
    stat_key: tuple[int, ...] = field(repr=False)
    interpreters: tuple[FileIdentity, ...] = field(default=(), repr=False)
    admission: Callable[[], None] | None = field(default=None, repr=False)


def _chain(path: Path) -> tuple[Path, ...]:
    require(path.is_absolute() and ".." not in path.parts, "configuration_drift")
    return (*reversed(path.parents), path)


def _stat_key(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_uid,
        info.st_gid,
        info.st_mode,
    )


def _read_identity(path: Path) -> FileIdentity:
    try:
        require(
            all(not part.is_symlink() for part in _chain(path)), "configuration_drift"
        )
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            require(
                stat.S_ISREG(before.st_mode) and before.st_mode & 0o111 != 0,
                "configuration_drift",
            )
            require(before.st_mode & 0o022 == 0, "configuration_drift")
            sha = hashlib.file_digest(stream, "sha256").hexdigest()
            after = os.fstat(stream.fileno())
        require(
            _stat_key(before) == _stat_key(after) == _stat_key(path.lstat()),
            "configuration_drift",
        )
        return FileIdentity(path=path, sha256=sha, stat_key=_stat_key(after))
    except OSError:
        raise ProfileError("configuration_drift") from None


def _admit_runtime(
    path: Path,
    candidate_root: Path,
    scratch_root: Path,
    runtime: RuntimeBindings | None,
    capability: RuntimeCapability | None,
    interpreters: tuple[FileIdentity, ...],
) -> Callable[[], None]:
    require(runtime is not None and capability is not None, "configuration_drift")
    if runtime is None or capability is None:
        raise ProfileError("configuration_drift")
    data = runtime.wire()
    bound_paths = {
        Path(row["absolute_path"])
        for row in (data["python"], data["git"], *data["tools"])
    }
    require(
        all(interpreter.path in bound_paths for interpreter in interpreters),
        "configuration_drift",
    )
    require(data["scratch_root"] == str(scratch_root), "configuration_drift")
    require(path in bound_paths, "configuration_drift")
    for root in (
        data["python"]["absolute_path"],
        data["producer"]["absolute_root"],
        data["git"]["absolute_path"],
        *(row["absolute_path"] for row in data["tools"]),
    ):
        require(
            not Path(root).is_relative_to(candidate_root)
            and not Path(root).is_relative_to(scratch_root),
            "configuration_drift",
        )
    _verify_runtime(runtime, capability)
    for interpreter in interpreters:
        _admit_live(interpreter.path, capability)
    return partial(_verify_runtime, runtime, capability)


def admit_executable(
    path: Path,
    expected_sha: str,
    candidate_root: Path,
    scratch_root: Path,
    *,
    live: bool = True,
    capability: RuntimeCapability | None = None,
    runtime: RuntimeBindings | None = None,
    interpreters: tuple[FileIdentity, ...] = (),
) -> FileIdentity:
    """Synthetic admission is not live admission; D must explicitly require live.

    Synthetic test executables may live under writable temporary parents. Live
    admission additionally rejects writable ancestors and requires external
    capability authority; no JSON/profile flag can supply that authority.
    """
    hex_digest(expected_sha)
    require(
        path.is_absolute() and path == Path(os.path.abspath(path)),
        "configuration_drift",
    )
    require(
        not path.is_relative_to(candidate_root)
        and not path.is_relative_to(scratch_root),
        "configuration_drift",
    )
    identity = _read_identity(path)
    require(identity.sha256 == expected_sha, "configuration_drift")
    _admit_header(path, interpreters)
    verify_identity(identity)
    admission = (
        _admit_runtime(
            path, candidate_root, scratch_root, runtime, capability, interpreters
        )
        if live
        else None
    )
    return FileIdentity(
        path=identity.path,
        sha256=identity.sha256,
        stat_key=identity.stat_key,
        interpreters=interpreters,
        admission=admission,
    )


def _admit_header(path: Path, interpreters: tuple[FileIdentity, ...]) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            header = stream.readline(4097)
        if header.startswith(b"\x7fELF"):
            require(not interpreters, "configuration_drift")
            return
        require(
            header.startswith(b"#!") and header.endswith(b"\n") and len(header) <= 256,
            "configuration_drift",
        )
        text = header[2:-1].decode("utf-8", errors="strict")
        require(
            len(interpreters) == 1
            and text == str(interpreters[0].path)
            and Path(text).name not in {"env", "sh", "bash", "dash", "zsh"},
            "configuration_drift",
        )
        verify_identity(interpreters[0])
    except (OSError, UnicodeError):
        raise ProfileError("configuration_drift") from None


def _admit_live(path: Path, capability: RuntimeCapability | None) -> None:
    require(capability is not None, "configuration_drift")
    if capability is None:  # narrows the Protocol for strict typing
        raise ProfileError("configuration_drift")
    try:
        safe_text(capability.revision)
        hex_digest(capability.digest)
        for component in _chain(path):
            require(component.lstat().st_mode & 0o022 == 0, "configuration_drift")
            require(
                capability.candidate_can_write(component) is False,
                "configuration_drift",
            )
            require(
                capability.assert_immutable(component) is None, "configuration_drift"
            )
    except Exception:
        raise ProfileError("configuration_drift") from None


def _verify_runtime(runtime: RuntimeBindings, capability: RuntimeCapability) -> None:
    try:
        data = runtime.wire()
        require(
            capability.revision == data["runner_capability_revision"]
            and capability.digest == data["capability_digest"],
            "configuration_drift",
        )
        for row in (data["python"], data["git"], *data["tools"]):
            path = Path(row["absolute_path"])
            _admit_live(path, capability)
            require(
                hex_digest(capability.provisioning_digest(path))
                == row["provisioning_digest"],
                "configuration_drift",
            )
            if "sha256" in row:
                require(
                    _read_identity(path).sha256 == row["sha256"], "configuration_drift"
                )
        producer = data["producer"]
        path = Path(producer["absolute_root"])
        _admit_live(path, capability)
        raw = read_regular(path, "producer-manifest.json", 2097152)
        manifest = exact(decode_json(raw, 2097152), {"format", "revision", "files"})
        require(
            raw == canonical(manifest)
            and hashlib.sha256(raw).hexdigest() == producer["manifest_digest"]
            and manifest["format"] == "orchestra.producer-artifact/v1"
            and manifest["revision"] == producer["revision"],
            "configuration_drift",
        )
        require(
            hex_digest(capability.provisioning_digest(path))
            == producer["manifest_digest"],
            "configuration_drift",
        )
    except Exception:
        raise ProfileError("configuration_drift") from None


def observe_executable(path: Path, expected_sha: str) -> FileIdentity:
    """Detect pinned Git drift; this observation grants no live runtime capability."""
    identity = _read_identity(path)
    require(identity.sha256 == hex_digest(expected_sha), "configuration_drift")
    _admit_header(path, ())
    verify_identity(identity)
    return identity


def verify_identity(expected: FileIdentity) -> None:
    if expected.admission is not None:
        expected.admission()
    actual = _read_identity(expected.path)
    require(
        actual.path == expected.path
        and actual.sha256 == expected.sha256
        and actual.stat_key == expected.stat_key,
        "configuration_drift",
    )
    for interpreter in expected.interpreters:
        verify_identity(interpreter)
