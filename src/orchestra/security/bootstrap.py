"""Stdlib-only isolated entry: verify every artifact byte before package imports."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import stat
import sys
import sysconfig
from pathlib import Path
from typing import Any, cast


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("configuration_drift")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _number(value: str) -> None:
    raise ValueError("invalid_request")


def _json(raw: bytes) -> dict[str, Any]:
    _require(len(raw) <= 2097152)
    text = raw.decode("utf-8", errors="strict")
    # Pre-import bound is intentionally independent of the package JSON loader.
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            _require(depth <= 16)
        elif char in "]}":
            depth -= 1
    value = json.loads(
        text, object_pairs_hook=_pairs, parse_float=_number, parse_constant=_number
    )
    _require(type(value) is dict)
    return cast(dict[str, Any], value)


def _read(root: Path, relative: str, cap: int) -> bytes:
    _require(
        type(relative) is str and not relative.startswith("/") and "\\" not in relative
    )
    _require(all(p not in {"", ".", ".."} for p in relative.split("/")))
    path = root
    for part in relative.split("/"):
        path /= part
        _require(not path.is_symlink())
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        _require(stat.S_ISREG(info.st_mode) and info.st_size <= cap)
        raw = stream.read(cap + 1)
        _require(len(raw) <= cap)
        return raw


def _manifest_expected(root: Path, manifest: dict[str, Any]) -> list[str]:
    _require(type(manifest["files"]) is list and len(manifest["files"]) <= 10000)
    expected = []
    for item in manifest["files"]:
        _require(type(item) is dict and set(item) == {"path", "sha256", "size"})
        content = _read(root, item["path"], 4194304)
        _require(
            type(item["size"]) is int
            and len(content) == item["size"]
            and hashlib.sha256(content).hexdigest() == item["sha256"]
        )
        expected.append(item["path"])
    return expected


def _manifest_actual(root: Path) -> list[str]:
    actual = []
    for count, path in enumerate(root.rglob("*"), start=1):
        _require(count <= 10000)
        _require(
            not path.is_symlink()
            and "__pycache__" not in path.parts
            and path.suffix
            not in {".pyc", ".pyo", ".pth", ".so", ".pyd", ".dll", ".dylib"}
        )
        _require(path.is_file() or path.is_dir())
        if (
            path.is_file()
            and path.relative_to(root).as_posix() != "producer-manifest.json"
        ):
            actual.append(path.relative_to(root).as_posix())
    return actual


def _preimport(root: Path, request: dict[str, Any]) -> None:
    _require(all(not p.is_symlink() for p in (root, *root.parents)))
    raw = _read(root, "producer-manifest.json", 2097152)
    manifest = _json(raw)
    _require(
        set(manifest) == {"format", "revision", "files"}
        and manifest["format"] == "orchestra.producer-artifact/v1"
        and manifest["revision"] == request["producer_revision"]
        and hashlib.sha256(raw).hexdigest() == request["producer_digest"]
    )
    _require(
        raw
        == json.dumps(
            manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    )
    expected = _manifest_expected(root, manifest)
    actual = _manifest_actual(root)
    _require(
        expected == sorted(set(expected), key=lambda p: p.encode())
        and set(expected) == set(actual)
    )


def main() -> int:
    try:
        _require(
            sys.argv[1:] == ["--request-stdin"]
            and bool(sys.flags.isolated)
            and bool(sys.flags.no_site)
            and bool(sys.flags.dont_write_bytecode)
        )
        raw = sys.stdin.buffer.read(2097153)
        request = _json(raw)
        root = Path(__file__).absolute().parent
        _preimport(root, request)
        stdlib = Path(sysconfig.get_path("stdlib"))
        sys.path[:] = [str(root), str(stdlib), str(stdlib / "lib-dynload")]
        from orchestra.security.artifact import verify_artifact, verify_loaded_origins
        from orchestra.security.profile import load_trusted_profile
        from orchestra.security.request import verify_request

        artifact = verify_artifact(
            root, request["producer_digest"], request["producer_revision"]
        )
        profile = load_trusted_profile(
            root / "orchestra/security/profiles/pilot-v1.json",
            request["profile_digest"],
            root / "orchestra/security/profiles",
        )
        admitted = verify_request(raw, profile)
        verify_loaded_origins(artifact)
        # B supplies the real producer; no fake-success implementation exists in A.
        try:
            run_scan = importlib.import_module("orchestra.security.producer").run_scan
        except ModuleNotFoundError as error:
            if error.name != "orchestra.security.producer":
                raise
            sys.stderr.write("security_producer_not_available\n")
            return 2
        return int(run_scan(admitted, profile, artifact))
    except Exception:
        sys.stderr.write("security_bootstrap_failed\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
