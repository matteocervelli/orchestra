"""Bounded uv v1/revision3 freshness by parser equality, never resolution."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any, cast

# packaging is pinned because Requirement/Marker equality must not be reimplemented.
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from orchestra.security.contracts import Package
from orchestra.security.inventory import WorkspaceInput
from orchestra.security.profile import (
    ProfileError,
    TrustedProfile,
    require,
    safe_path,
    safe_text,
)


def parse_toml(raw: bytes) -> dict[str, Any]:
    require(type(raw) is bytes and len(raw) <= 4194304, "scope_overflow")
    try:
        return tomllib.loads(raw.decode("utf-8", errors="strict"))
    except (ValueError, UnicodeError, RecursionError):
        raise ProfileError("unsupported_dependency_syntax") from None


def _requirements(values: object, *, locked: bool = False) -> tuple[Requirement, ...]:
    require(type(values) is list, "unsupported_dependency_syntax")
    result = []
    for value in cast(list[Any], values):
        if locked:
            require(type(value) is dict, "unsupported_dependency_syntax")
            require(
                set(value)
                <= {
                    "name",
                    "extras",
                    "specifier",
                    "marker",
                    "index",
                    "editable",
                    "virtual",
                },
                "unsupported_dependency_source",
            )
            name = safe_text(value.get("name"), 200)
            extras = value.get("extras", [])
            require(
                type(extras) is list and all(type(e) is str for e in extras),
                "unsupported_dependency_syntax",
            )
            text = name + ("[" + ",".join(extras) + "]" if extras else "")
            text += value.get("specifier", "")
            if value.get("marker"):
                text += "; " + value["marker"]
        else:
            require(type(value) is str, "unsupported_dependency_syntax")
            text = value
        requirement = Requirement(text)
        require(requirement.url is None, "unsupported_dependency_source")
        result.append(requirement)
    require(len(result) == len(set(result)), "stale_lock")
    return tuple(result)


def _same(declared: object, locked: object) -> None:
    require(
        set(_requirements(declared)) == set(_requirements(locked, locked=True)),
        "stale_lock",
    )


def _workspace_members(
    root: str, manifests: Mapping[str, bytes], members: list[str], excludes: list[str]
) -> set[str]:
    selected: set[str] = set()
    for path in manifests:
        if path.startswith(root) and path.endswith("pyproject.toml"):
            relative = path[len(root) :].removesuffix("/pyproject.toml")
            if any(PurePosixPath(relative).match(p) for p in members) and not any(
                PurePosixPath(relative).match(p) for p in excludes
            ):
                selected.add(path)
    return selected


def _workspace_paths(
    root: str, manifests: Mapping[str, bytes], config: dict[str, Any]
) -> tuple[str, ...]:
    selected = {root + "pyproject.toml"}
    workspace = config.get("workspace", {})
    require(
        type(workspace) is dict and set(workspace) <= {"members", "exclude"},
        "unsupported_dependency_syntax",
    )
    members, excludes = workspace.get("members", []), workspace.get("exclude", [])
    require(
        type(members) is list and type(excludes) is list,
        "unsupported_dependency_syntax",
    )
    for pattern in [*members, *excludes]:
        safe_path(pattern)
    selected.update(_workspace_members(root, manifests, members, excludes))
    for pattern in members:
        require(
            any(
                PurePosixPath(p[len(root) :].removesuffix("/pyproject.toml")).match(
                    pattern
                )
                for p in selected
            ),
            "stale_lock",
        )
    require(selected <= set(manifests), "missing_lockfile")
    return tuple(sorted(selected))


def _source_indexes(config: dict[str, Any], profile: TrustedProfile) -> dict[str, str]:
    indexes = config.get("index", [])
    sources = config.get("sources", {})
    require(
        type(indexes) is list and type(sources) is dict, "unsupported_dependency_syntax"
    )
    approved = {
        profile.bindings()["public_index"],
        *profile.bindings()["private_indexes"],
    }
    named: dict[str, str] = {}
    for item in indexes:
        require(
            type(item) is dict
            and set(item) == {"name", "url", "explicit"}
            and item["explicit"] is True
            and item["url"] in approved,
            "unsupported_dependency_source",
        )
        name = safe_text(item["name"])
        require(name not in named, "unsupported_dependency_source")
        named[name] = item["url"]
    result: dict[str, str] = {}
    for name, item in sources.items():
        require(
            type(item) is dict and set(item) == {"index"} and item["index"] in named,
            "unsupported_dependency_source",
        )
        result[canonicalize_name(name)] = named[item["index"]]
    return result


def _check_requirement_indexes(
    declared: object, locked: object, indexes: dict[str, str]
) -> None:
    _same(declared, locked)
    for item in cast(list[dict[str, Any]], locked):
        name = canonicalize_name(item["name"])
        require(item.get("index") == indexes.get(name), "stale_lock")


def _member_groups(
    manifest: dict[str, Any], metadata: dict[str, Any], indexes: dict[str, str]
) -> None:
    groups = manifest.get("dependency-groups", {})
    locked_groups = metadata.get("requires-dev", {})
    require(
        type(groups) is dict
        and type(locked_groups) is dict
        and set(groups) == set(locked_groups),
        "stale_lock",
    )
    for group, requirements in groups.items():
        _check_requirement_indexes(requirements, locked_groups[group], indexes)


def _member(
    path: str,
    raw: bytes,
    packages: list[dict[str, Any]],
    root: str,
    root_config: dict[str, Any],
    profile: TrustedProfile,
) -> tuple[dict[str, Any], str]:
    manifest = parse_toml(raw)
    project = manifest.get("project", {})
    require(
        type(project) is dict
        and "dynamic" not in project
        and "optional-dependencies" not in project,
        "unsupported_dependency_syntax",
    )
    name, version = (
        safe_text(project.get("name"), 200),
        safe_text(project.get("version")),
    )
    Version(version)
    relative = path[len(root) :].removesuffix("pyproject.toml").rstrip("/") or "."
    matches = [
        p
        for p in packages
        if canonicalize_name(p["name"]) == canonicalize_name(name)
        and p.get("source") in ({"editable": relative}, {"virtual": relative})
    ]
    require(len(matches) == 1 and matches[0].get("version") == version, "stale_lock")
    config = manifest.get("tool", {}).get("uv", {})
    require(
        type(config) is dict
        and set(config) <= {"workspace", "constraint-dependencies", "index", "sources"},
        "unsupported_dependency_syntax",
    )
    combined = dict(root_config)
    combined.update(config)
    indexes = _source_indexes(combined, profile)
    metadata = matches[0].get("metadata", {})
    _check_requirement_indexes(
        project.get("dependencies", []), metadata.get("requires-dist", []), indexes
    )
    _member_groups(manifest, metadata, indexes)
    return project, canonicalize_name(name)


def _python_range(
    project: dict[str, Any], locked: object, profile: TrustedProfile
) -> None:
    declared = project.get("requires-python")
    require(type(declared) is str and type(locked) is str, "stale_lock")
    equal = SpecifierSet(cast(str, declared)) == SpecifierSet(cast(str, locked))
    binding = [project["name"], declared, locked]
    require(equal or binding in profile.bindings()["python_ranges"], "stale_lock")


def _packages(
    raw: object, member_paths: dict[str, str], profile: TrustedProfile
) -> tuple[Package, ...]:
    require(type(raw) is list, "unsupported_dependency_syntax")
    approved = {
        profile.bindings()["public_index"],
        *profile.bindings()["private_indexes"],
    }
    result: dict[tuple[str, str, str], Package] = {}
    for item in cast(list[dict[str, Any]], raw):
        require(type(item) is dict, "unsupported_dependency_syntax")
        name, version = (
            canonicalize_name(safe_text(item.get("name"), 200)),
            safe_text(item.get("version")),
        )
        Version(version)
        source = item.get("source")
        require(type(source) is dict, "unsupported_dependency_source")
        source = cast(dict[str, Any], source)
        if set(source) == {"registry"}:
            require(source["registry"] in approved, "unsupported_dependency_source")
            key = ("PyPI", name, version)
            result[key] = Package(ecosystem=key[0], name=name, version=version)
        else:
            require(
                set(source) in ({"editable"}, {"virtual"}) and name in member_paths,
                "unsupported_dependency_source",
            )
            path = source.get("editable", source.get("virtual"))
            require(
                type(path) is str and path == member_paths[name],
                "unsupported_dependency_source",
            )
    return tuple(result[key] for key in sorted(result))


def _edge_identity(edge: dict[str, Any]) -> tuple[str, list[str]]:
    require(
        type(edge) is dict
        and set(edge) <= {"name", "version", "source", "marker", "extra"}
        and "name" in edge,
        "unsupported_dependency_syntax",
    )
    name = canonicalize_name(safe_text(edge["name"], 200))
    if "marker" in edge:
        Requirement(name + "; " + safe_text(edge["marker"], 4096))
    extras = edge.get("extra", [])
    require(
        type(extras) is list and all(type(e) is str for e in extras),
        "unsupported_dependency_syntax",
    )
    return name, cast(list[str], extras)


def _edge_targets(
    edges: object, packages: list[dict[str, Any]]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    require(type(edges) is list, "coverage_gap")
    result = []
    for edge in cast(list[dict[str, Any]], edges):
        name, extras = _edge_identity(edge)
        matches = [
            p
            for p in packages
            if canonicalize_name(p["name"]) == name
            and ("version" not in edge or p["version"] == edge["version"])
            and ("source" not in edge or p["source"] == edge["source"])
        ]
        require(len(matches) == 1, "coverage_gap")
        target = matches[0]
        require(
            set(extras) <= set(target.get("optional-dependencies", {})), "coverage_gap"
        )
        result.append((edge, target))
    return result


def _requirement_targets(
    requirement: Requirement,
    matches: list[tuple[dict[str, Any], dict[str, Any]]],
    declared: object,
) -> None:
    for edge, target in matches:
        require(
            requirement.specifier.contains(target["version"], prereleases=True)
            and set(requirement.extras) <= set(edge.get("extra", [])),
            "coverage_gap",
        )
        declared_item = next(
            d
            for d in cast(list[dict[str, Any]], declared)
            if canonicalize_name(d["name"]) == canonicalize_name(requirement.name)
        )
        if "index" in declared_item:
            require(
                target["source"] == {"registry": declared_item["index"]},
                "coverage_gap",
            )


def _declared_edges(
    declared: object, edges: object, packages: list[dict[str, Any]]
) -> None:
    resolved = _edge_targets(edges, packages)
    requirements = _requirements(declared, locked=True)
    require(
        {canonicalize_name(r.name) for r in requirements}
        == {canonicalize_name(e["name"]) for e, _ in resolved},
        "coverage_gap",
    )
    for requirement in requirements:
        matches = [
            (edge, target)
            for edge, target in resolved
            if canonicalize_name(edge["name"]) == canonicalize_name(requirement.name)
        ]
        require(bool(matches), "coverage_gap")
        _requirement_targets(requirement, matches, declared)


def _resolved_graph(packages: list[dict[str, Any]]) -> None:
    identities = [
        (canonicalize_name(p["name"]), p["version"], str(sorted(p["source"].items())))
        for p in packages
    ]
    require(len(identities) == len(set(identities)), "coverage_gap")
    for package in packages:
        _edge_targets(package.get("dependencies", []), packages)
        for section in ("dev-dependencies", "optional-dependencies"):
            groups = package.get(section, {})
            require(type(groups) is dict, "unsupported_dependency_syntax")
            for edges in groups.values():
                _edge_targets(edges, packages)
        metadata = package.get("metadata", {})
        if metadata:
            _declared_edges(
                metadata.get("requires-dist", []),
                package.get("dependencies", []),
                packages,
            )
            for group, declared in metadata.get("requires-dev", {}).items():
                _declared_edges(
                    declared,
                    package.get("dev-dependencies", {}).get(group, []),
                    packages,
                )


def validate_uv(
    manifests: Mapping[str, bytes], lock_path: str, raw: bytes, profile: TrustedProfile
) -> WorkspaceInput:
    try:
        return _validate_uv(manifests, safe_path(lock_path), raw, profile)
    except ProfileError:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        InvalidRequirement,
        InvalidVersion,
        InvalidSpecifier,
        RecursionError,
    ):
        raise ProfileError("unsupported_dependency_syntax") from None


def _validate_uv(
    manifests: Mapping[str, bytes], lock_path: str, raw: bytes, profile: TrustedProfile
) -> WorkspaceInput:
    require(lock_path.endswith("uv.lock"), "unsupported_stack_or_lock")
    root = lock_path.removesuffix("uv.lock")
    root_manifest = root + "pyproject.toml"
    require(root_manifest in manifests, "missing_lockfile")
    manifest, lock = parse_toml(manifests[root_manifest]), parse_toml(raw)
    require(
        type(lock.get("version")) is int
        and lock["version"] == 1
        and type(lock.get("revision")) is int
        and lock["revision"] == 3,
        "unsupported_stack_or_lock",
    )
    config = manifest.get("tool", {}).get("uv", {})
    require(
        type(config) is dict
        and set(config) <= {"workspace", "constraint-dependencies", "index", "sources"},
        "unsupported_dependency_syntax",
    )
    selected = _workspace_paths(root, manifests, config)
    require(len(selected) <= profile.limit("root_count"), "scope_overflow")
    packages = lock.get("package", [])
    require(type(packages) is list, "unsupported_dependency_syntax")
    names: dict[str, str] = {}
    for path in selected:
        project, name = _member(path, manifests[path], packages, root, config, profile)
        _python_range(project, lock.get("requires-python"), profile)
        require(name not in names, "stale_lock")
        names[name] = (
            path[len(root) :].removesuffix("pyproject.toml").rstrip("/") or "."
        )
    locked_manifest = lock.get("manifest", {})
    members = locked_manifest.get("members")
    if members is not None:
        require(
            type(members) is list
            and set(map(canonicalize_name, members)) == set(names),
            "stale_lock",
        )
    constraints = config.get("constraint-dependencies", [])
    _check_requirement_indexes(
        constraints,
        locked_manifest.get("constraints", []),
        _source_indexes(config, profile),
    )
    indexed = _packages(packages, names, profile)
    _resolved_graph(packages)
    return WorkspaceInput(
        lock_path=lock_path,
        kind="uv1-r3",
        members=selected,
        manifests=selected,
        governing_inputs=tuple(sorted((*selected, lock_path))),
        packages=indexed,
    )
