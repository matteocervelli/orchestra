"""Bounded private metadata receipts with an explicit durable commit capability."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from contextlib import suppress
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from . import shadow_schema as S
from .shadow_graph import Graph, ShadowBlocked
from .shadow_prior import generation

REASONS = tuple(
    [
        "root_schema",
        "forbidden",
        "opaque_op",
        "callable_drift",
        "global_drift",
        "closure",
        "cold_probe",
        "callback_roster",
        "request_delta",
        "frame_delta",
        "post_delta",
        "prior_missing",
        "prior_invalid",
        "bounds",
        "baseline_exception",
        "candidate_exception",
        "publish_failed",
        "commit",
    ]
)
COVERAGE = tuple(
    ["roots", "roster", "opaque", "callables", "frame", "postgraph", "publish"]
)
COUNTS = tuple(["items", "nodes", "edges", "callbacks", "probes", "differences"])
_PHASES = tuple(
    ["prepare", "baseline", "preflight", "candidate", "compare", "publish", "commit"]
)
_ROLES = tuple(["canonical", "legacy", "callback", "class", "probe", "globals"])
_SCHEMA = S.record(
    {
        "schema": ("enum", ("shadow-observation/1",)),
        "nonce": "Nonce",
        "verdict": ("enum", ("PASS", "BLOCK", "PARTIAL")),
        "phase": ("enum", _PHASES),
        "profile_id": ("enum", ("m3s-full-boundary/1",)),
        "final_generated": "TS",
        "final_board_digest": "H64",
        "prior_generated": "TS",
        "prior_board_digest": "H64",
        "witness_sha": "H64",
        "code_pins": S.seq(
            S.record(
                {"role": ("enum", _ROLES), "file_sha": "H64", "loaded_code_sha": "H64"}
            )
        ),
        "coverage": S.record(dict.fromkeys(COVERAGE, "B")),
        "counts": S.record(dict.fromkeys(COUNTS, "I0")),
        "shape_sha": "H64",
        "alias_sha": "H64",
        "diffs": S.seq(
            S.record({"code": ("enum", REASONS), "path": "T500", "count": "I+"})
        ),
    }
)
# Nonce has its own exact bound, validated before the schema's ordinary string.
_SCHEMA[1]["nonce"] = "S64"
_PATH = re.compile(
    r"\$(?:roots(?:\.(?:asm|ctx|locals|original_notes|return_notes|tasks|globals))?(?:\.[A-Za-z_][A-Za-z_0-9]*|\[\*\]|\[\d{1,5}\])*|frame\.(?:calls|memo|anc|budget|dirty|requests)|code\[\*\]|prior\.(?:scope|generation|witness)|publish\.(?:generation|digest)|commit)"
)


_DURABLE = object()


class CommitState(Enum):
    NOT_COMMITTED = "NOT_COMMITTED"
    COMMITTED = "COMMITTED"
    COMMIT_UNKNOWN = "COMMIT_UNKNOWN"


@dataclass(frozen=True)
class CommittedReceipt:
    nonce: str
    final_name: str
    sha256: str
    byte_count: int
    device: int
    inode: int
    final_generated: str
    final_board_digest: str
    state: str = "COMMITTED"
    schema: str = "shadow-commit/1"
    _durable: object = field(default=None, init=False, repr=False, compare=False)


@dataclass(frozen=True)
class CommitResult:
    state: CommitState
    receipt: CommittedReceipt | None = None


def _tokens() -> set[str]:
    fields: set[str] = set()

    def walk(spec: Any) -> None:
        if type(spec) is tuple:
            if spec[0] == "record":
                for key, value in {**spec[1], **spec[2]}.items():
                    fields.add(key)
                    walk(value)
            else:
                for child in spec[1:]:
                    if type(child) is tuple:
                        walk(child)

    for spec in (
        S.ITEM,
        S.NOTE,
        S.record(S.ASSEMBLY),
        S.record(S.CTX),
        S.record(S.LOCALS),
        S.record(S.PROBE_FIELDS),
    ):
        walk(spec)
    return fields | set(
        ["asm", "ctx", "locals", "original_notes", "return_notes", "tasks", "globals"]
    )


_PATH_FIELDS = _tokens()


def _safe_path(value: str) -> bool:
    if _PATH.fullmatch(value) is None:
        return False
    if not value.startswith("$roots"):
        return True
    return all(
        token in _PATH_FIELDS
        for token in re.findall(r"\.([A-Za-z_][A-Za-z_0-9]*)", value)
    )


def _encode(payload: dict[str, Any]) -> bytes:
    Graph().clone(payload, _SCHEMA)
    if re.fullmatch(r"[0-9a-f]{32}", payload["nonce"]) is None:
        raise ValueError("metadata")
    generation(payload["final_generated"])
    generation(payload["prior_generated"])
    if len(payload["diffs"]) > 100 or len(payload["code_pins"]) > 200:
        raise ValueError("metadata")
    if any(not _safe_path(entry["path"]) for entry in payload["diffs"]):
        raise ValueError("metadata")
    data = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()
    if len(data) > 65536:
        raise ValueError("metadata")
    return data


def _open_dir(name: str | Path, *, parent: int | None = None) -> int:
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    mode = os.fstat(fd)
    if stat.S_IMODE(mode.st_mode) != 0o700 or mode.st_uid != os.getuid():
        os.close(fd)
        raise ValueError("directory")
    return fd


def _subdir(root: int, name: str) -> int:
    with suppress(FileExistsError):
        os.mkdir(name, 0o700, dir_fd=root)
    return _open_dir(name, parent=root)


def _same_root(path: Path, root: int) -> bool:
    a, b = os.stat(path, follow_symlinks=False), os.fstat(root)
    return stat.S_ISDIR(a.st_mode) and (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def _same_namespace(root: int, name: str, descriptor: int) -> bool:
    named = os.stat(name, dir_fd=root, follow_symlinks=False)
    opened = os.fstat(descriptor)
    return stat.S_ISDIR(named.st_mode) and (named.st_dev, named.st_ino) == (
        opened.st_dev,
        opened.st_ino,
    )


def _write_temp(pending: int, name: str, data: bytes) -> os.stat_result:
    fd = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=pending,
    )
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
        found = os.fstat(stream.fileno())
    os.fsync(pending)
    return found


def _namespace(root: Path, root_fd: int, pending: int, final: int) -> None:
    if (
        not _same_root(root, root_fd)
        or not _same_namespace(root_fd, ".pending", pending)
        or not _same_namespace(root_fd, "receipts", final)
    ):
        raise ValueError("directory")


def _commit(root: Path, payload: dict[str, Any], data: bytes) -> CommitResult:
    descriptors: list[int] = []
    linked = False
    try:
        root_fd = _open_dir(root)
        descriptors.append(root_fd)
        pending = _subdir(root_fd, ".pending")
        descriptors.append(pending)
        final = _subdir(root_fd, "receipts")
        descriptors.append(final)
        os.fsync(root_fd)
        nonce = payload["nonce"]
        temp_name, final_name = nonce + ".tmp", "shadow-" + nonce + ".json"
        original = _write_temp(pending, temp_name, data)
        _namespace(root, root_fd, pending, final)
        os.link(
            temp_name,
            final_name,
            src_dir_fd=pending,
            dst_dir_fd=final,
            follow_symlinks=False,
        )
        linked = True
        os.fsync(final)
        found = os.stat(final_name, dir_fd=final, follow_symlinks=False)
        _namespace(root, root_fd, pending, final)
        if (found.st_dev, found.st_ino) != (original.st_dev, original.st_ino):
            raise ValueError("directory")
        receipt = CommittedReceipt(
            nonce,
            final_name,
            hashlib.sha256(data).hexdigest(),
            len(data),
            found.st_dev,
            found.st_ino,
            payload["final_generated"],
            payload["final_board_digest"],
        )
        object.__setattr__(receipt, "_durable", _DURABLE)
        return CommitResult(CommitState.COMMITTED, receipt)
    except (OSError, ValueError):
        return CommitResult(
            CommitState.COMMIT_UNKNOWN if linked else CommitState.NOT_COMMITTED
        )
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def commit_receipt(root: Path, payload: dict[str, Any]) -> CommitResult:
    try:
        data = _encode(payload)
    except (ValueError, TypeError, OverflowError, ShadowBlocked):
        return CommitResult(CommitState.NOT_COMMITTED)
    return _commit(root, payload, data)


def _read(root: Path, receipt: CommittedReceipt) -> dict[str, Any]:
    root_fd = _open_dir(root)
    final_fd = file_fd = -1
    try:
        final_fd = _open_dir("receipts", parent=root_fd)
        file_fd = os.open(
            receipt.final_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=final_fd
        )
        found = os.fstat(file_fd)
        expected = (receipt.device, receipt.inode, receipt.byte_count, 0o600)
        actual = (
            found.st_dev,
            found.st_ino,
            found.st_size,
            stat.S_IMODE(found.st_mode),
        )
        if not stat.S_ISREG(found.st_mode) or actual != expected:
            raise ValueError("receipt")
        with os.fdopen(file_fd, "rb", closefd=False) as stream:
            data = stream.read(65537)
        if (
            hashlib.sha256(data).hexdigest() != receipt.sha256
            or not _same_root(root, root_fd)
            or not _same_namespace(root_fd, "receipts", final_fd)
        ):
            raise ValueError("receipt")
        payload: dict[str, Any] = json.loads(data)
        if _encode(payload) != data or (
            payload["nonce"],
            payload["final_generated"],
            payload["final_board_digest"],
        ) != (receipt.nonce, receipt.final_generated, receipt.final_board_digest):
            raise ValueError("receipt")
        return payload
    finally:
        for fd in (file_fd, final_fd, root_fd):
            if fd >= 0:
                os.close(fd)


def read_receipt(root: Path, receipt: CommittedReceipt | None) -> dict[str, Any]:
    if (
        type(receipt) is not CommittedReceipt
        or receipt._durable is not _DURABLE
        or receipt.state != "COMMITTED"
        or receipt.schema != "shadow-commit/1"
    ):
        raise ValueError("receipt")
    if (
        re.fullmatch(r"[0-9a-f]{32}", receipt.nonce) is None
        or receipt.final_name != "shadow-" + receipt.nonce + ".json"
    ):
        raise ValueError("receipt")
    return _read(root, receipt)
