"""Pinned trusted profile parsing; output grants no policy authority."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

CATALOG = {
    "gitleaks-json-8.30.1": ("gitleaks", "8.30.1"),
    "portable-patterns-v1": ("patterns", "1"),
    "bandit-json-1.9.4": ("bandit", "1.9.4"),
    "uv-pylock-0.13.5": ("python-export", "0.13.5"),
    "pip-audit-json-2.10.1": ("python-audit", "2.10.1"),
    "pnpm-json-10.34.8": ("javascript-audit", "10.34.8"),
    "npm-json-11.21.1": ("javascript-audit", "11.21.1"),
    "osv-json-2.7.0": ("osv", "2.7.0"),
    "trivy-json-0.76.1": ("trivy", "0.76.1"),
}
CEILINGS = {
    "request_bytes": 2097152,
    "envelope_bytes": 65536,
    "native_stdout_bytes": 65536,
    "native_stderr_bytes": 65536,
    "file_bytes": 65536,
    "probe_bytes": 4096,
    "file_count": 10000,
    "manifest_count": 256,
    "root_count": 64,
    "receipt_count": 128,
    "finding_count": 128,
    "gap_count": 128,
    "blob_bytes": 4194304,
    "aggregate_bytes": 67108864,
    "probe_seconds": 10,
    "export_seconds": 60,
    "native_seconds": 300,
    "scan_seconds": 3600,
    "yaml_depth": 32,
    "yaml_nodes": 100000,
}
FAMILY_ORDER = (
    "gitleaks",
    "patterns",
    "bandit",
    "python-export",
    "python-audit",
    "javascript-audit",
    "osv",
    "trivy",
)


SECURITY_ENV_KEYS = frozenset(
    {
        "HOME",
        "USER",
        "PATH",
        "LANG",
        "LC_ALL",
        "TZ",
        "TMPDIR",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
    }
)


class ProfileError(ValueError):
    """Fixed safe code only; never attach input or native diagnostics."""


def require(condition: bool, code: str = "invalid_request") -> None:
    if not condition:
        raise ProfileError(code)


def safe_text(value: object, bound: int = 100) -> str:
    require(type(value) is str)
    text = cast(str, value)
    try:
        require(0 < len(text.encode("utf-8")) <= bound)
    except UnicodeError:
        raise ProfileError("invalid_request") from None
    require(not any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in text))
    return text


def safe_path(value: object) -> str:
    path = safe_text(value, 512)
    require(not path.startswith("/") and "\\" not in path, "unsupported_path")
    require(all(p not in {"", ".", ".."} for p in path.split("/")), "unsupported_path")
    return path


def hex_digest(value: object, length: int = 64) -> str:
    require(
        type(value) is str and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None
    )
    return cast(str, value)


def canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError):
        raise ProfileError("invalid_request") from None


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def _number(value: str) -> None:
    raise ProfileError("invalid_request")


def _json_depth(text: str) -> None:
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
            require(depth <= 16)
        elif char in "]}":
            depth -= 1


def decode_json(raw: bytes, limit: int = 65536) -> dict[str, Any]:
    require(type(raw) is bytes and len(raw) <= limit, "scope_overflow")
    try:
        text = raw.decode("utf-8", errors="strict")
        _json_depth(text)
        result = json.loads(
            text, object_pairs_hook=_pairs, parse_float=_number, parse_constant=_number
        )
        require(type(result) is dict)
        return cast(dict[str, Any], result)
    except ProfileError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ProfileError("invalid_request") from None


def exact(data: object, keys: set[str]) -> dict[str, Any]:
    require(type(data) is dict and set(data) == keys)
    return cast(dict[str, Any], data)


def strings(value: object, *, paths: bool = False, bound: int = 128) -> tuple[str, ...]:
    require(type(value) is list and len(value) <= bound)
    values = tuple(
        safe_path(x) if paths else safe_text(x, 512) for x in cast(list[Any], value)
    )
    require(values == tuple(sorted(set(values), key=lambda x: x.encode())))
    return values


def validate_security_environment(environment: dict[str, str]) -> None:
    require(set(environment) == SECURITY_ENV_KEYS, "configuration_drift")
    require(
        environment["LANG"] == environment["LC_ALL"] == "C.UTF-8"
        and environment["TZ"] == "UTC",
        "configuration_drift",
    )
    for key in SECURITY_ENV_KEYS - {"LANG", "LC_ALL", "TZ", "USER", "PATH"}:
        require(Path(environment[key]).is_absolute(), "configuration_drift")
    require(
        all(
            Path(part).is_absolute() and ".." not in Path(part).parts
            for part in environment["PATH"].split(os.pathsep)
        ),
        "configuration_drift",
    )
    for value in environment.values():
        safe_text(value, 4096)


def security_environment(
    home: Path, scratch: Path, path_entries: tuple[Path, ...], user: str
) -> dict[str, str]:
    require(home.is_absolute() and scratch.is_absolute(), "configuration_drift")
    require(not home.is_symlink() and not scratch.is_symlink(), "configuration_drift")
    try:
        scratch.mkdir(mode=0o700, parents=False, exist_ok=False)
        for name in ("tmp", "cache", "config", "data"):
            (scratch / name).mkdir(mode=0o700)
    except OSError:
        raise ProfileError("configuration_drift") from None
    environment = {
        "HOME": str(home),
        "USER": safe_text(user),
        "PATH": os.pathsep.join(str(path) for path in path_entries),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "TMPDIR": str(scratch / "tmp"),
        "XDG_CACHE_HOME": str(scratch / "cache"),
        "XDG_CONFIG_HOME": str(scratch / "config"),
        "XDG_DATA_HOME": str(scratch / "data"),
    }
    validate_security_environment(environment)
    return environment


def _context_wire(value: object) -> dict[str, Any]:
    data = exact(value, {"schema", "runtime_digest", "ci_declaration", "trivy_db"})
    require(data["schema"] == "orchestra.security-context/v1")
    hex_digest(data["runtime_digest"])
    ci = exact(
        data["ci_declaration"],
        {"digest", "workflow_revisions", "requires_trivy", "trivy_scanners"},
    )
    hex_digest(ci["digest"])
    require(ci["digest"] == digest({k: v for k, v in ci.items() if k != "digest"}))
    require(type(ci["requires_trivy"]) is bool)
    scanners = strings(ci["trivy_scanners"])
    require(set(scanners) <= {"vuln", "secret", "misconfig", "license"})
    require(bool(scanners) == ci["requires_trivy"])
    revisions = ci["workflow_revisions"]
    require(type(revisions) is list and len(revisions) <= 128)
    keys = []
    for row in revisions:
        row = exact(row, {"repository", "path", "revision"})
        keys.append(
            (
                safe_text(row["repository"]),
                safe_path(row["path"]),
                hex_digest(row["revision"], 40),
            )
        )
    require(keys == sorted(set(keys)))
    require(len({key[:2] for key in keys}) == len(keys))
    if data["trivy_db"] is not None:
        db = exact(
            data["trivy_db"], {"digest", "updated_at_epoch", "verified_at_epoch"}
        )
        hex_digest(db["digest"])
        require(
            all(
                type(db[k]) is int and db[k] >= 0
                for k in ("updated_at_epoch", "verified_at_epoch")
            )
        )
    return data


def read_regular(root: Path, relative: str, limit: int) -> bytes:
    path = root
    try:
        for component in safe_path(relative).split("/"):
            path = path / component
            require(not path.is_symlink(), "configuration_drift")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode), "configuration_drift")
            require(info.st_size <= limit, "scope_overflow")
            content = stream.read(limit + 1)
            require(len(content) <= limit, "scope_overflow")
            return content
    except OSError:
        raise ProfileError("configuration_drift") from None


@dataclass(frozen=True)
class Asset:
    path: str = field(repr=False)
    sha256: str
    size: int


@dataclass(frozen=True)
class AdapterProfile:
    adapter_id: str
    family: str
    version: str
    native_schema: str
    recipe_id: str
    asset_paths: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True)
class TrustedProfile:
    profile_id: str
    adapters: tuple[AdapterProfile, ...] = field(repr=False)
    limits: tuple[tuple[str, int], ...]
    exclusions: tuple[str, ...]
    dependency_free_scopes: tuple[tuple[str | None, str], ...] = field(repr=False)
    source_bindings: bytes = field(repr=False)
    policy: str
    assets: tuple[Asset, ...] = field(repr=False)
    digest: str

    def limit(self, name: str) -> int:
        return dict(self.limits)[name]

    def bindings(self) -> dict[str, Any]:
        return decode_json(self.source_bindings)


def _asset(value: object, root: Path) -> Asset:
    data = exact(value, {"path", "sha256", "size"})
    path, sha = safe_path(data["path"]), hex_digest(data["sha256"])
    size = data["size"]
    require(type(size) is int and 0 <= size <= 4194304)
    content = read_regular(root, path, 4194304)
    require(
        len(content) == size and hashlib.sha256(content).hexdigest() == sha,
        "configuration_drift",
    )
    return Asset(path=path, sha256=sha, size=size)


def _adapter(value: object, assets: set[str]) -> AdapterProfile:
    data = exact(
        value,
        {
            "adapter_id",
            "family",
            "version",
            "native_schema",
            "recipe_id",
            "asset_paths",
        },
    )
    adapter = safe_text(data["adapter_id"])
    require(adapter in CATALOG, "unsupported_version")
    require(
        (data["family"], data["version"]) == CATALOG[adapter], "unsupported_version"
    )
    require(
        data["recipe_id"] == adapter and data["native_schema"] == adapter,
        "unsupported_version",
    )
    paths = strings(data["asset_paths"], paths=True)
    require(set(paths) <= assets, "configuration_drift")
    return AdapterProfile(
        adapter_id=adapter,
        family=data["family"],
        version=data["version"],
        native_schema=adapter,
        recipe_id=adapter,
        asset_paths=paths,
    )


def _url(value: object) -> str:
    url = safe_text(value, 512)
    parsed = urlsplit(url)
    require(
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )
    return url


def _bindings(value: object) -> bytes:
    data = exact(
        value,
        {
            "grammar",
            "public_index",
            "js_registry",
            "private_indexes",
            "python_ranges",
            "js_overrides",
        },
    )
    require(data["grammar"] == "uv1-r3/pnpm9/npm3-v1")
    _url(data["public_index"])
    _url(data["js_registry"])
    for url in strings(data["private_indexes"]):
        _url(url)
    for key, size in (("python_ranges", 3), ("js_overrides", 7)):
        rows = data[key]
        require(type(rows) is list and len(rows) <= 128)
        seen: set[bytes] = set()
        for row in rows:
            require(type(row) is list and len(row) == size)
            for item in row:
                safe_text(item, 512)
            encoded = canonical(row)
            require(encoded not in seen)
            seen.add(encoded)
        require(rows == sorted(rows))
    return canonical(data)


def _profile_catalog(
    data: dict[str, Any], assets_root: Path
) -> tuple[tuple[Asset, ...], tuple[AdapterProfile, ...]]:
    require(type(data["assets"]) is list and len(data["assets"]) <= 128)
    assets = tuple(_asset(x, assets_root) for x in data["assets"])
    require(tuple(x.path for x in assets) == tuple(sorted({x.path for x in assets})))
    require(type(data["adapters"]) is list and len(data["adapters"]) == len(CATALOG))
    adapters = tuple(_adapter(x, {a.path for a in assets}) for x in data["adapters"])
    require(tuple(x.adapter_id for x in adapters) == tuple(sorted(CATALOG)))
    return assets, adapters


def load_trusted_profile(
    profile_file: Path, expected_digest: str, assets_root: Path
) -> TrustedProfile:
    raw = read_regular(profile_file.parent, profile_file.name, 65536)
    data = decode_json(raw)
    require(digest(data) == hex_digest(expected_digest), "profile_mismatch")
    exact(
        data,
        {
            "schema",
            "profile_id",
            "adapters",
            "limits",
            "exclusions",
            "dependency_free_scopes",
            "source_bindings",
            "policy",
            "assets",
        },
    )
    require(data["schema"] == "orchestra.security-profile/v1")
    require(data["policy"] == "orchestra-high-block-v1", "profile_mismatch")
    limits = exact(data["limits"], set(CEILINGS))
    require(all(type(v) is int and 0 < v <= CEILINGS[k] for k, v in limits.items()))
    assets, adapters = _profile_catalog(data, assets_root)
    scopes = data["dependency_free_scopes"]
    require(type(scopes) is list and len(scopes) <= 64)
    scope_rows = []
    for scope in scopes:
        row = exact(scope, {"path", "inventory_digest"})
        path = safe_path(row["path"]) if row["path"] is not None else None
        scope_rows.append((path, hex_digest(row["inventory_digest"])))
    require(len(scope_rows) == len(set(scope_rows)))
    return TrustedProfile(
        profile_id=safe_text(data["profile_id"]),
        adapters=adapters,
        limits=tuple(sorted(limits.items())),
        exclusions=strings(data["exclusions"], paths=True),
        dependency_free_scopes=tuple(scope_rows),
        source_bindings=_bindings(data["source_bindings"]),
        policy="orchestra-high-block-v1",
        assets=assets,
        digest=expected_digest,
    )
