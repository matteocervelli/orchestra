"""Restricted lock input parsing; no dependency resolution or network."""

from pathlib import Path

import pytest
from test_profile import document, load

from orchestra.security.js_metadata import validate_js
from orchestra.security.lock_metadata import validate_uv
from orchestra.security.profile import ProfileError
from orchestra.security.yaml_loader import load_yaml


def test_plain_pnpm_mapping_uses_safe_python_loader() -> None:
    assert load_yaml(
        b"lockfileVersion: '9.0'\nimporters:\n  .:\n    dependencies: {}\n"
    ) == {"lockfileVersion": "9.0", "importers": {".": {"dependencies": {}}}}


@pytest.mark.parametrize(
    "raw",
    [
        b"a: 1\na: 2",
        b"a: &id value\nb: *id",
        b"a: !!str value",
        b"a: {<<: {x: 1}}",
        b"1: value",
        b"---\na: 1\n---\nb: 2",
        b"a: !!python/object:os.system {}",
        b"\xff",
        b"a: 1.5",
    ],
    ids=[
        "duplicate",
        "alias",
        "tag",
        "merge",
        "key",
        "multidoc",
        "unsafe",
        "encoding",
        "float",
    ],
)
def test_yaml_unsafe_structures_reject(raw: bytes) -> None:
    with pytest.raises(ProfileError, match="unsupported_dependency_syntax"):
        load_yaml(raw)


def test_yaml_resource_bounds_are_not_construct_then_check() -> None:
    with pytest.raises(ProfileError):
        load_yaml(("[" * 33 + "]" * 33).encode())
    with pytest.raises(ProfileError):
        load_yaml(b"[a,b,c]", node_limit=3)
    with pytest.raises(ProfileError):
        load_yaml(b"a: x", byte_limit=3)


PRIVATE_INDEX = "https://packages.example.invalid/simple/"

PYPROJECT = b"""
[project]
name = "example"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["harness[typesafe]==0.2.5; sys_platform == 'linux'"]
[dependency-groups]
dev = ["pytest>=8"]
[tool.uv]
constraint-dependencies = ["harness-core==0.2.5"]
[[tool.uv.index]]
name = "private"
url = "https://packages.example.invalid/simple/"
explicit = true
[tool.uv.sources]
harness = { index = "private" }
harness-core = { index = "private" }
"""

UVLOCK = (
    b"""
version = 1
revision = 3
requires-python = ">=3.12"
[manifest]
constraints = [{name="harness-core",specifier="==0.2.5",index="https://packages.example.invalid/simple/"}]
[[package]]
name = "example"
version = "0.1.0"
source = {editable="."}
dependencies = [{name="harness",extra=["typesafe"],marker="sys_platform == 'linux'"}]
[package.dev-dependencies]
dev = [{name="pytest"}]
[package.metadata]
requires-dist = ["""
    b'{name="harness",extras=["typesafe"],specifier="==0.2.5",'
    b'marker="sys_platform == \'linux\'",index="https://packages.example.invalid/simple/"}'
    b"""]
[package.metadata.requires-dev]
dev = [{name="pytest",specifier=">=8"}]
[[package]]
name = "harness"
version = "0.2.5"
source = {registry="https://packages.example.invalid/simple/"}
[package.optional-dependencies]
typesafe = [{name="harness-core"}]
[[package]]
name = "harness-core"
version = "0.2.5"
source = {registry="https://packages.example.invalid/simple/"}
[[package]]
name = "pytest"
version = "9.1.1"
source = {registry="https://pypi.org/simple"}
"""
)


@pytest.mark.parametrize(
    "kind",
    [
        "all-indexed",
        "direct",
        "dev",
        "transitive",
        "root-edge",
        "extra-edge",
        "version",
    ],
)
def test_uv_resolved_graph_cannot_omit_declared_or_recorded_targets(
    tmp_path: Path, kind: str
) -> None:
    raw = UVLOCK
    if kind == "all-indexed":
        raw = raw.split(b'[[package]]\nname = "harness"')[0]
    elif kind in {"direct", "dev", "transitive"}:
        name = {"direct": "harness", "dev": "pytest", "transitive": "harness-core"}[
            kind
        ]
        blocks = raw.split(b"[[package]]")
        raw = b"[[package]]".join(
            b
            for b in blocks
            if not b.lstrip().startswith(('name = "' + name + '"').encode())
        )
    elif kind == "root-edge":
        raw = raw.replace(
            b'dependencies = [{name="harness",extra=["typesafe"],'
            b"marker=\"sys_platform == 'linux'\"}]",
            b"dependencies = []",
        )
    elif kind == "extra-edge":
        raw = raw.replace(b'[{name="harness-core"}]', b'[{name="absent"}]')
    else:
        raw = raw.replace(b'version = "0.2.5"', b'version = "0.2.6"')
    with pytest.raises(ProfileError, match="coverage_gap"):
        validate_uv(
            {"pyproject.toml": PYPROJECT}, "uv.lock", raw, metadata_profile(tmp_path)
        )


def metadata_profile(tmp_path: Path):
    data = document()
    data["source_bindings"]["private_indexes"] = [PRIVATE_INDEX]
    data["source_bindings"]["js_overrides"] = [
        ["dashboard", "devDependencies", "vite", "^6", "vite@>=6 <7", "6.4.4", "6.4.4"]
    ]
    return load(tmp_path, data)


def test_uv_real_target_extras_markers_constraints_and_index_shape(
    tmp_path: Path,
) -> None:
    result = validate_uv(
        {"pyproject.toml": PYPROJECT}, "uv.lock", UVLOCK, metadata_profile(tmp_path)
    )
    assert result.manifests == ("pyproject.toml",)
    assert {(p.name, p.version) for p in result.packages} == {
        ("harness", "0.2.5"),
        ("harness-core", "0.2.5"),
        ("pytest", "9.1.1"),
    }
    assert result.lock_path == "uv.lock"


@pytest.mark.parametrize(
    "kind",
    [
        "marker",
        "extras",
        "constraint",
        "index",
        "revision",
        "source",
        "duplicate",
        "dynamic",
        "optional",
        "include",
    ],
)
def test_uv_stale_or_unsupported_never_resolves(tmp_path: Path, kind: str) -> None:
    project, lock = PYPROJECT, UVLOCK
    if kind == "marker":
        project = project.replace(b"linux", b"win32")
    elif kind == "extras":
        project = project.replace(b"[typesafe]", b"[different]")
    elif kind == "constraint":
        project = project.replace(b"harness-core==0.2.5", b"harness-core==0.2.6")
    elif kind == "index":
        lock = lock.replace(b"packages.example.invalid", b"other.example.invalid")
    elif kind == "revision":
        lock = lock.replace(b"revision = 3", b"revision = 4")
    elif kind == "source":
        lock = lock.replace(
            b'registry="https://pypi.org/simple"', b'git="https://example.invalid/code"'
        )
    elif kind == "duplicate":
        project = project.replace(
            b'dev = ["pytest>=8"]', b'dev = ["pytest>=8", "pytest>=8"]'
        )
    elif kind == "dynamic":
        project = project.replace(
            b'name = "example"', b'name = "example"\ndynamic = ["dependencies"]'
        )
    elif kind == "optional":
        project += b'\n[project.optional-dependencies]\nx = ["harness"]\n'
    else:
        project = project.replace(
            b'dev = ["pytest>=8"]', b'dev = [{include-group="other"}]'
        )
    with pytest.raises(ProfileError):
        validate_uv(
            {"pyproject.toml": project}, "uv.lock", lock, metadata_profile(tmp_path)
        )


def test_orchestra_python_range_pair_requires_exact_profile_binding(
    tmp_path: Path,
) -> None:
    project = PYPROJECT.replace(b">=3.12", b">=3.12,<3.13")
    lock = UVLOCK.replace(b">=3.12", b"==3.12.*")
    profile = metadata_profile(tmp_path)
    with pytest.raises(ProfileError, match="stale_lock"):
        validate_uv({"pyproject.toml": project}, "uv.lock", lock, profile)
    data = document()
    data["source_bindings"]["private_indexes"] = [PRIVATE_INDEX]
    data["source_bindings"]["python_ranges"] = [["example", ">=3.12,<3.13", "==3.12.*"]]
    bound = load(tmp_path, data)
    assert (
        validate_uv({"pyproject.toml": project}, "uv.lock", lock, bound).kind
        == "uv1-r3"
    )


def js_manifests() -> dict[str, bytes]:
    import json

    return {
        "dashboard/package.json": json.dumps(
            {
                "name": "root",
                "version": "0.1.0",
                "workspaces": ["packages/*"],
                "devDependencies": {"vite": "^6"},
                "pnpm": {"overrides": {"vite@>=6 <7": "6.4.4"}},
                "scripts": {"postinstall": "must-never-run"},
            }
        ).encode(),
        "dashboard/packages/a/package.json": json.dumps(
            {"name": "member-a", "version": "0.1.0", "dependencies": {"foo": "1.2.3"}}
        ).encode(),
    }


PNPMLOCK = b"""
lockfileVersion: '9.0'
overrides:
  vite@>=6 <7: 6.4.4
importers:
  .:
    devDependencies:
      vite: {specifier: 6.4.4, version: 6.4.4}
  packages/a:
    dependencies:
      foo: {specifier: 1.2.3, version: 1.2.3}
packages:
  vite@6.4.4: {resolution: {integrity: synthetic}}
  foo@1.2.3: {resolution: {integrity: synthetic}}
snapshots:
  vite@6.4.4: {}
  foo@1.2.3: {}
"""


def test_pnpm_workspace_and_exact_override_binding(tmp_path: Path) -> None:
    result = validate_js(
        js_manifests(), "dashboard/pnpm-lock.yaml", PNPMLOCK, metadata_profile(tmp_path)
    )
    assert len(result.manifests) == 2
    assert {(p.name, p.version) for p in result.packages} == {
        ("vite", "6.4.4"),
        ("foo", "1.2.3"),
    }


@pytest.mark.parametrize(
    "kind", ["missing-importer", "stale", "override", "external", "version"]
)
def test_js_stale_ambiguous_or_external_coverage_blocks(
    tmp_path: Path, kind: str
) -> None:
    manifests, lock = js_manifests(), PNPMLOCK
    if kind == "missing-importer":
        lock = lock.replace(b"packages/a:", b"packages/absent:")
    elif kind == "stale":
        lock = lock.replace(b"specifier: 1.2.3", b"specifier: 1.2.4")
    elif kind == "override":
        lock = lock.replace(b"vite@>=6 <7: 6.4.4", b"vite@>=6 <7: 6.4.5")
    elif kind == "external":
        lock = lock.replace(b"version: 1.2.3", b"version: link:../../../outside")
    else:
        lock = lock.replace(b"'9.0'", b"'10.0'")
    with pytest.raises(ProfileError):
        validate_js(
            manifests, "dashboard/pnpm-lock.yaml", lock, metadata_profile(tmp_path)
        )


def test_npm_v3_distinct_schema_not_pnpm_fallback(tmp_path: Path) -> None:
    import json

    manifests = {
        "package.json": json.dumps(
            {"name": "root", "version": "0.1.0", "dependencies": {"foo": "^1"}}
        ).encode()
    }
    lock = json.dumps(
        {
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "root", "version": "0.1.0", "dependencies": {"foo": "^1"}},
                "node_modules/foo": {
                    "version": "1.2.3",
                    "resolved": "https://registry.npmjs.org/foo/-/foo-1.2.3.tgz",
                },
            },
        }
    ).encode()
    result = validate_js(
        manifests, "package-lock.json", lock, metadata_profile(tmp_path)
    )
    assert result.kind == "npm3"
    assert [(p.name, p.version) for p in result.packages] == [("foo", "1.2.3")]


@pytest.mark.parametrize(
    "extra",
    [
        b'\n[[package]]\nname="example"\nversion="0.1.0"\nsource={editable="other"}\n',
        b'\n[[package]]\nname="example"\nversion="0.1.0"\nsource={virtual="other"}\n',
        b'\n[[package]]\nname="example"\nversion="0.1.0"\nsource={virtual="."}\n',
    ],
    ids=["other-editable", "other-virtual", "duplicate-source"],
)
def test_uv_extra_known_name_cannot_impersonate_selected_member(
    tmp_path: Path, extra: bytes
) -> None:
    with pytest.raises(ProfileError):
        validate_uv(
            {"pyproject.toml": PYPROJECT},
            "uv.lock",
            UVLOCK + extra,
            metadata_profile(tmp_path),
        )


def test_pnpm_importer_cannot_claim_packages_absent_from_inventory(
    tmp_path: Path,
) -> None:
    prefix = PNPMLOCK.split(b"packages:")[0]
    raw = prefix + b"packages: {}\nsnapshots: {}\n"
    with pytest.raises(ProfileError, match="coverage_gap"):
        validate_js(
            js_manifests(), "dashboard/pnpm-lock.yaml", raw, metadata_profile(tmp_path)
        )


def test_pnpm_missing_transitive_recorded_target_is_coverage_gap(
    tmp_path: Path,
) -> None:
    raw = PNPMLOCK.replace(
        b"  foo@1.2.3: {}", b"  foo@1.2.3:\n    dependencies: {missing: 9.8.7}"
    )
    with pytest.raises(ProfileError, match="coverage_gap"):
        validate_js(
            js_manifests(), "dashboard/pnpm-lock.yaml", raw, metadata_profile(tmp_path)
        )


@pytest.mark.parametrize("transitive", [False, True])
def test_npm_missing_direct_or_transitive_recorded_target_blocks(
    tmp_path: Path, transitive: bool
) -> None:
    import json

    manifests = {
        "package.json": json.dumps(
            {"name": "root", "version": "0.1.0", "dependencies": {"foo": "^1"}}
        ).encode()
    }
    packages = {"": {"name": "root", "version": "0.1.0", "dependencies": {"foo": "^1"}}}
    if transitive:
        packages["node_modules/foo"] = {
            "version": "1.2.3",
            "dependencies": {"missing": "^9"},
        }
    raw = json.dumps({"lockfileVersion": 3, "packages": packages}).encode()
    with pytest.raises(ProfileError, match="coverage_gap"):
        validate_js(manifests, "package-lock.json", raw, metadata_profile(tmp_path))
