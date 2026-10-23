"""Trusted profile corpus: the branch/report cannot choose policy or versions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from orchestra.security.profile import ProfileError, load_trusted_profile

ADAPTERS = {
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


def document() -> dict:
    return {
        "schema": "orchestra.security-profile/v1",
        "profile_id": "test-profile",
        "adapters": [
            {
                "adapter_id": name,
                "family": family,
                "version": version,
                "native_schema": name,
                "recipe_id": name,
                "asset_paths": ["rules.toml"],
            }
            for name, (family, version) in sorted(ADAPTERS.items())
        ],
        "limits": {
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
        },
        "exclusions": [".git", ".worktrees"],
        "dependency_free_scopes": [],
        "source_bindings": {
            "grammar": "uv1-r3/pnpm9/npm3-v1",
            "public_index": "https://pypi.org/simple",
            "js_registry": "https://registry.npmjs.org",
            "private_indexes": [],
            "python_ranges": [],
            "js_overrides": [],
        },
        "policy": "orchestra-high-block-v1",
        "assets": [
            {"path": "rules.toml", "sha256": hashlib.sha256(b"").hexdigest(), "size": 0}
        ],
    }


def encoded(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def load(tmp_path: Path, value: dict):
    (tmp_path / "rules.toml").write_bytes(b"")
    raw = encoded(value)
    source = tmp_path / "profile.json"
    source.write_bytes(raw)
    return load_trusted_profile(source, hashlib.sha256(raw).hexdigest(), tmp_path)


def test_full_catalog_strict_digest_and_immutable_profile(tmp_path: Path) -> None:
    profile = load(tmp_path, document())
    assert profile.profile_id == "test-profile"
    assert profile.limit("native_stdout_bytes") == 65536
    assert len(profile.adapters) == 9
    with pytest.raises((AttributeError, TypeError, ValueError)):
        profile.profile_id = "branch-selected"
    assert "rules.toml" not in repr(profile)  # no private asset/runtime paths


@pytest.mark.parametrize(
    "kind", ["policy", "tool", "extra", "limit", "bool", "source", "missing"]
)
def test_invalid_profile_contract_blocks(tmp_path: Path, kind: str) -> None:
    value = document()
    if kind == "policy":
        value["policy"] = "critical-only"
    elif kind == "tool":
        value["adapters"][0]["version"] = "future"
    elif kind == "extra":
        value["command"] = "arbitrary executable"
    elif kind == "limit":
        value["limits"]["envelope_bytes"] = 65537
    elif kind == "bool":
        value["limits"]["file_count"] = True
    elif kind == "source":
        value["source_bindings"]["public_index"] = (
            "https://user:synthetic-token@example.invalid/"
        )
    else:
        value["adapters"].pop()
    with pytest.raises(ProfileError):
        load(tmp_path, value)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema":0,"schema":1}',
        b"{} {}",
        b"\xef\xbb\xbf{}",
        b'{"x":1.2}',
        b'{"x":NaN}',
        b"\xff",
        b"[" * 17 + b"]" * 17,
        b" " * 65537,
    ],
    ids=[
        "duplicate",
        "trailing",
        "bom",
        "float",
        "constant",
        "utf8",
        "depth",
        "overflow",
    ],
)
def test_wire_profile_rejects_before_diagnostics(tmp_path: Path, raw: bytes) -> None:
    source = tmp_path / "profile.json"
    source.write_bytes(raw)
    with pytest.raises(ProfileError) as caught:
        load_trusted_profile(source, "0" * 64, tmp_path)
    assert str(caught.value) in {
        "invalid_request",
        "profile_mismatch",
        "scope_overflow",
    }
    assert str(source) not in str(caught.value)


def test_asset_drift_and_profile_digest_cannot_be_self_asserted(tmp_path: Path) -> None:
    value = document()
    profile = load(tmp_path, value)
    (tmp_path / "rules.toml").write_bytes(b"tampered")
    with pytest.raises(ProfileError, match="configuration_drift"):
        load_trusted_profile(tmp_path / "profile.json", profile.digest, tmp_path)
    with pytest.raises(ProfileError, match="profile_mismatch"):
        load_trusted_profile(tmp_path / "profile.json", "f" * 64, tmp_path)


def test_checked_in_a_catalog_cannot_activate_before_b_assets() -> None:
    source = Path(__file__).parents[3] / "src/orchestra/security/profiles/pilot-v1.json"
    from orchestra.security.profile import decode_json, digest

    value = decode_json(source.read_bytes())
    assert value["policy"] == "orchestra-high-block-v1"
    with pytest.raises(ProfileError, match="configuration_drift"):
        load_trusted_profile(source, digest(value), source.parent)


def test_asset_symlink_or_unknown_reference_blocks(tmp_path: Path) -> None:
    value = document()
    value["adapters"][0]["asset_paths"] = ["absent"]
    with pytest.raises(ProfileError, match="configuration_drift"):
        load(tmp_path, value)
    value = document()
    load(tmp_path, value)
    target = tmp_path / "target"
    target.write_bytes(b"")
    (tmp_path / "rules.toml").unlink()
    (tmp_path / "rules.toml").symlink_to(target)
    with pytest.raises(ProfileError, match="configuration_drift"):
        load_trusted_profile(
            tmp_path / "profile.json",
            hashlib.sha256(encoded(value)).hexdigest(),
            tmp_path,
        )
