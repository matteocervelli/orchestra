"""Pinned pnpm9/npm3 input freshness; no semver solver or lifecycle execution."""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any, cast

from orchestra.security.contracts import Package
from orchestra.security.inventory import WorkspaceInput
from orchestra.security.profile import (
    ProfileError,
    TrustedProfile,
    decode_json,
    require,
    safe_path,
    safe_text,
)
from orchestra.security.yaml_loader import load_yaml

_GROUPS = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
)


def _declared(value: object) -> dict[str, str]:
    require(type(value) is dict, "unsupported_dependency_syntax")
    result = {}
    for name, specifier in cast(dict[str, Any], value).items():
        name, specifier = safe_text(name, 200), safe_text(specifier, 512)
        require(
            not specifier.startswith(
                ("file:", "link:", "git", "http:", "https:", "patch:", "portal:")
            ),
            "unsupported_dependency_source",
        )
        result[name] = specifier
    return result


def _workspace_patterns(
    manifests: Mapping[str, bytes], root: str, root_manifest: dict[str, Any]
) -> list[str]:
    patterns = root_manifest.get("workspaces", [])
    if root + "pnpm-workspace.yaml" in manifests:
        workspace = load_yaml(manifests[root + "pnpm-workspace.yaml"])
        require(set(workspace) == {"packages"}, "unsupported_dependency_syntax")
        require(not patterns or patterns == workspace["packages"], "stale_lock")
        patterns = workspace["packages"]
    require(type(patterns) is list, "unsupported_dependency_syntax")
    for pattern in patterns:
        safe_path(pattern)
    return cast(list[str], patterns)


def _member_configuration(manifest: dict[str, Any]) -> None:
    require(
        not any(key in manifest for key in ("auditConfig", "audit", "audit-ignore")),
        "configuration_drift",
    )
    pnpm = manifest.get("pnpm", {})
    require(
        type(pnpm) is dict and not any("audit" in key.lower() for key in pnpm),
        "configuration_drift",
    )
    for group in _GROUPS:
        _declared(manifest.get(group, {}))


def _workspace_matches(patterns: list[str], result: dict[str, Any]) -> None:
    for pattern in patterns:
        require(
            any(
                PurePosixPath(directory).match(pattern)
                for directory in result
                if directory != "."
            ),
            "stale_lock",
        )


def _member_map(manifests: Mapping[str, bytes], root: str) -> dict[str, dict[str, Any]]:
    root_path = root + "package.json"
    require(root_path in manifests, "missing_lockfile")
    root_manifest = decode_json(manifests[root_path], 4194304)
    patterns = _workspace_patterns(manifests, root, root_manifest)
    result = {".": root_manifest}
    for path, raw in manifests.items():
        if (
            path.startswith(root)
            and path.endswith("/package.json")
            and path != root_path
        ):
            directory = path[len(root) :].removesuffix("/package.json")
            if any(PurePosixPath(directory).match(pattern) for pattern in patterns):
                result[directory] = decode_json(raw, 4194304)
    _workspace_matches(patterns, result)
    for manifest in result.values():
        _member_configuration(manifest)
    return result


def _overrides(
    root: dict[str, Any], lock: dict[str, Any], pnpm: bool
) -> dict[str, str]:
    overrides = (
        root.get("pnpm", {}).get("overrides", {}) if pnpm else root.get("overrides", {})
    )
    require(
        type(overrides) is dict
        and all(type(k) is str and type(v) is str for k, v in overrides.items()),
        "unsupported_dependency_syntax",
    )
    recorded = lock.get("overrides", {})
    require(recorded == overrides, "stale_lock")
    return cast(dict[str, str], overrides)


def _specifier(
    root: str,
    member: str,
    group: str,
    name: str,
    declared: str,
    locked: object,
    overrides: dict[str, str],
    profile: TrustedProfile,
) -> None:
    require(type(locked) is str, "stale_lock")
    if declared == locked:
        return
    workspace = (root + member).rstrip("/") if member != "." else root.rstrip("/")
    for binding in profile.bindings()["js_overrides"]:
        owner, category, dependency, source, selector, value, specifier = binding
        if (owner, category, dependency, source, specifier) == (
            workspace,
            group,
            name,
            declared,
            locked,
        ):
            require(overrides.get(selector) == value, "stale_lock")
            return
    raise ProfileError("stale_lock")


def _version(value: object) -> str:
    version = safe_text(value)
    require(
        re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.+-]+)?", version)
        is not None,
        "unsupported_dependency_source",
    )
    return version


def _link(member: str, value: str, members: set[str]) -> None:
    relative = posixpath.normpath(
        posixpath.join("" if member == "." else member, value[5:])
    )
    require(
        relative in members and not relative.startswith("../"),
        "unsupported_dependency_source",
    )


def _pnpm_target(name: str, resolved: str, lock: dict[str, Any]) -> None:
    base = resolved.split("(", 1)[0]
    if "@" in base:
        package_name, separator, version = base.rpartition("@")
        require(bool(separator) and bool(package_name), "unsupported_dependency_source")
        _version(version)
        target = resolved
    else:
        _version(base)
        target = name + "@" + resolved
    packages, snapshots = lock.get("packages", {}), lock.get("snapshots", {})
    require(
        type(packages) is dict
        and type(snapshots) is dict
        and target.split("(", 1)[0] in packages
        and target in snapshots,
        "coverage_gap",
    )


def _pnpm_importers(
    root: str,
    members: dict[str, dict[str, Any]],
    lock: dict[str, Any],
    overrides: dict[str, str],
    profile: TrustedProfile,
) -> None:
    importers = lock.get("importers")
    require(type(importers) is dict, "unsupported_dependency_syntax")
    importers = cast(dict[str, Any], importers)
    require(type(importers) is dict and set(importers) == set(members), "stale_lock")
    for member, manifest in members.items():
        importer = importers[member]
        require(
            type(importer) is dict and set(importer) <= set(_GROUPS),
            "unsupported_dependency_syntax",
        )
        for group in _GROUPS:
            declared, locked = (
                _declared(manifest.get(group, {})),
                importer.get(group, {}),
            )
            require(type(locked) is dict and set(declared) == set(locked), "stale_lock")
            for name, specifier in declared.items():
                item = locked[name]
                require(
                    type(item) is dict and set(item) == {"specifier", "version"},
                    "stale_lock",
                )
                _specifier(
                    root,
                    member,
                    group,
                    name,
                    specifier,
                    item["specifier"],
                    overrides,
                    profile,
                )
                resolved = safe_text(item["version"], 512)
                if resolved.startswith("link:"):
                    _link(member, resolved, set(members))
                else:
                    _pnpm_target(name, resolved, lock)


def _registry_url(value: str) -> None:
    from urllib.parse import urlsplit

    url = urlsplit(value)
    require(
        url.scheme == "https"
        and bool(url.hostname)
        and url.username is None
        and url.password is None
        and not url.query
        and not url.fragment,
        "unsupported_dependency_source",
    )


def _pnpm_snapshots(
    lock: dict[str, Any], packages: dict[str, Any], snapshots: dict[str, Any]
) -> None:
    for key in snapshots:
        require(key.split("(", 1)[0] in packages, "coverage_gap")
        row = snapshots[key]
        require(type(row) is dict, "unsupported_dependency_syntax")
        for group in ("dependencies", "optionalDependencies"):
            edges = row.get(group, {})
            require(type(edges) is dict, "unsupported_dependency_syntax")
            for name, resolved in edges.items():
                _pnpm_target(safe_text(name, 200), safe_text(resolved, 512), lock)


def _pnpm_packages(lock: dict[str, Any]) -> tuple[Package, ...]:
    packages, snapshots = lock.get("packages", {}), lock.get("snapshots", {})
    require(
        type(packages) is dict and type(snapshots) is dict,
        "unsupported_dependency_syntax",
    )
    result = {}
    for key, item in packages.items():
        name, separator, version = safe_text(key, 512).rpartition("@")
        require(bool(separator) and bool(name), "unsupported_dependency_source")
        name, version = safe_text(name, 200), _version(version)
        require(
            type(item) is dict and type(item.get("resolution")) is dict, "coverage_gap"
        )
        resolution = item["resolution"]
        require(
            not any(k in resolution for k in ("directory", "repo", "commit", "type")),
            "unsupported_dependency_source",
        )
        if "tarball" in resolution:
            _registry_url(resolution["tarball"])
        result[(name, version)] = Package(ecosystem="npm", name=name, version=version)
    _pnpm_snapshots(lock, packages, snapshots)
    return tuple(result[key] for key in sorted(result))


def _npm_target(packages: dict[str, Any], origin: str, name: str) -> str:
    cursor = origin
    while True:
        candidate = (cursor + "/" if cursor else "") + "node_modules/" + name
        if candidate in packages:
            return candidate
        if not cursor:
            raise ProfileError("coverage_gap")
        cursor = posixpath.dirname(cursor)


def _npm_edges(packages: dict[str, Any]) -> None:
    for path, item in packages.items():
        require(type(item) is dict, "unsupported_dependency_syntax")
        if item.get("link") is True:
            continue
        for group in _GROUPS:
            edges = item.get(group, {})
            require(type(edges) is dict, "unsupported_dependency_syntax")
            for name in edges:
                name = safe_text(name, 200)
                optional_peer = (
                    group == "peerDependencies"
                    and item.get("peerDependenciesMeta", {})
                    .get(name, {})
                    .get("optional")
                    is True
                )
                if not optional_peer:
                    _npm_target(packages, path, name)


def _npm_members(
    root: str,
    members: dict[str, dict[str, Any]],
    packages: dict[str, Any],
    overrides: dict[str, str],
    profile: TrustedProfile,
) -> None:
    for member, manifest in members.items():
        item = packages["" if member == "." else member]
        require(
            item.get("name", manifest.get("name")) == manifest.get("name")
            and item.get("version") == manifest.get("version"),
            "stale_lock",
        )
        for group in _GROUPS:
            declared, recorded = _declared(manifest.get(group, {})), item.get(group, {})
            require(
                type(recorded) is dict and set(declared) == set(recorded), "stale_lock"
            )
            for name, specifier in declared.items():
                _specifier(
                    root,
                    member,
                    group,
                    name,
                    specifier,
                    recorded[name],
                    overrides,
                    profile,
                )


def _npm_packages(
    root: str,
    members: dict[str, dict[str, Any]],
    lock: dict[str, Any],
    overrides: dict[str, str],
    profile: TrustedProfile,
) -> tuple[Package, ...]:
    require(
        type(lock.get("lockfileVersion")) is int and lock["lockfileVersion"] == 3,
        "unsupported_stack_or_lock",
    )
    packages = lock.get("packages")
    require(type(packages) is dict, "unsupported_dependency_syntax")
    packages = cast(dict[str, Any], packages)
    expected = {"" if member == "." else member for member in members}
    require(expected <= set(packages), "stale_lock")
    _npm_edges(packages)
    _npm_members(root, members, packages, overrides, profile)
    result = {}
    for path, item in packages.items():
        if path in expected:
            continue
        safe_path(path)
        require(type(item) is dict, "unsupported_dependency_syntax")
        if item.get("link") is True:
            require(item.get("resolved") in expected, "unsupported_dependency_source")
            continue
        require("/node_modules/" in "/" + path, "coverage_gap")
        name = item.get("name", path.rsplit("node_modules/", 1)[-1])
        name, version = safe_text(name, 200), _version(item.get("version"))
        resolved = item.get("resolved")
        if resolved is not None:
            _registry_url(resolved)
        result[(name, version)] = Package(ecosystem="npm", name=name, version=version)
    return tuple(result[key] for key in sorted(result))


def validate_js(
    manifests: Mapping[str, bytes], lock_path: str, raw: bytes, profile: TrustedProfile
) -> WorkspaceInput:
    try:
        return _validate_js(manifests, safe_path(lock_path), raw, profile)
    except ProfileError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise ProfileError("unsupported_dependency_syntax") from None


def _validate_js(
    manifests: Mapping[str, bytes], lock_path: str, raw: bytes, profile: TrustedProfile
) -> WorkspaceInput:
    pnpm = lock_path.endswith("pnpm-lock.yaml")
    require(
        pnpm or lock_path.endswith("package-lock.json"), "unsupported_stack_or_lock"
    )
    root = lock_path.removesuffix("pnpm-lock.yaml" if pnpm else "package-lock.json")
    members = _member_map(manifests, root)
    require(len(members) <= profile.limit("root_count"), "scope_overflow")
    lock = load_yaml(raw) if pnpm else decode_json(raw, 4194304)
    overrides = _overrides(members["."], lock, pnpm)
    if pnpm:
        require(lock.get("lockfileVersion") == "9.0", "unsupported_stack_or_lock")
        _pnpm_importers(root, members, lock, overrides, profile)
        packages = _pnpm_packages(lock)
    else:
        packages = _npm_packages(root, members, lock, overrides, profile)
    paths = tuple(
        sorted(
            root + (member + "/" if member != "." else "") + "package.json"
            for member in members
        )
    )
    governing = [*paths, lock_path]
    if root + "pnpm-workspace.yaml" in manifests:
        governing.append(root + "pnpm-workspace.yaml")
    return WorkspaceInput(
        lock_path=lock_path,
        kind="pnpm9" if pnpm else "npm3",
        members=paths,
        manifests=paths,
        governing_inputs=tuple(sorted(governing)),
        packages=packages,
    )
