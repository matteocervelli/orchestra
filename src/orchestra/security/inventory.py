"""Bounded immutable Git inventory; no text filename splitting or mutable refs."""

from __future__ import annotations

import hashlib
import stat
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from orchestra.security.contracts import Package
from orchestra.security.process import _local_git_state
from orchestra.security.process import git_bytes as git_bytes
from orchestra.security.profile import (
    ProfileError,
    TrustedProfile,
    hex_digest,
    read_regular,
    require,
    safe_path,
)

_SOURCE_SUFFIXES = frozenset(
    [
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        ".mts",
        ".cts",
        ".sh",
        ".sql",
        ".html",
        ".jinja",
        ".j2",
        ".yaml",
        ".yml",
        ".toml",
        ".md",
    ]
)
_MANIFEST_NAMES = frozenset(
    ["pyproject.toml", "uv.lock", "package.json", "pnpm-lock.yaml", "package-lock.json"]
)
_UNSUPPORTED_NAMES = frozenset(
    [
        "Cargo.toml",
        "Cargo.lock",
        "go.mod",
        "go.sum",
        "Gemfile",
        "Gemfile.lock",
        "composer.json",
        "composer.lock",
        "yarn.lock",
        "bun.lock",
        "bun.lockb",
        "poetry.lock",
        "Pipfile",
        "Pipfile.lock",
        "setup.py",
        "setup.cfg",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
    ]
)


def excluded(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in prefixes)


def relevant(path: str) -> bool:
    return (
        pattern_source(path)
        or Path(path).name in _MANIFEST_NAMES
        or unsupported_manifest(path)
    )


def pattern_source(path: str) -> bool:
    return Path(path).name == ".env" or Path(path).suffix in _SOURCE_SUFFIXES


def unsupported_manifest(path: str) -> bool:
    name = Path(path).name
    return (
        name in _UNSUPPORTED_NAMES
        or (name.startswith("requirements") and name.endswith(".txt"))
        or name == "pylock.toml"
        or (name.startswith("pylock.") and name.endswith(".toml"))
    )


@dataclass(frozen=True)
class FileInput:
    path: str
    mode: str
    blob_id: str
    sha256: str
    size: int

    def wire(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceInput:
    lock_path: str
    kind: str
    members: tuple[str, ...]
    manifests: tuple[str, ...]
    governing_inputs: tuple[str, ...]
    packages: tuple[Package, ...]

    def wire(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Inventory:
    head_sha: str
    base_sha: str
    merge_base_sha: str
    files: tuple[FileInput, ...] = field(repr=False)
    changed: tuple[str, ...] = field(repr=False)
    content_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    def content(self, path: str) -> bytes:
        return dict(self.content_items)[path]

    def verify_worktree(self, root: Path) -> None:
        for item in self.files:
            try:
                current = read_regular(root, item.path, item.size)
                require(
                    hashlib.sha256(current).hexdigest() == item.sha256, "scope_drift"
                )
                info = (root / item.path).lstat()
                require(
                    bool(info.st_mode & stat.S_IXUSR) == (item.mode == "100755"),
                    "scope_drift",
                )
            except ProfileError:
                raise ProfileError("scope_drift") from None


def _source_coverage(contents: dict[str, bytes], result: list[WorkspaceInput]) -> None:
    for suffixes, kinds in [
        ({".py"}, {"uv1-r3"}),
        (
            {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"},
            {"pnpm9", "npm3"},
        ),
    ]:
        roots = [str(Path(w.lock_path).parent) for w in result if w.kind in kinds]
        for path in contents:
            if Path(path).suffix in suffixes:
                require(
                    any(root == "." or path.startswith(root + "/") for root in roots),
                    "missing_lockfile",
                )


def _manifest_coverage(
    manifests: dict[str, bytes], owners: set[str], js_roots: set[str]
) -> None:
    require(
        set(manifests)
        <= owners.union(
            {
                p
                for p in manifests
                if p.endswith("pnpm-workspace.yaml") and str(Path(p).parent) in js_roots
            }
        ),
        "missing_lockfile",
    )


def _workspaces(
    inventory: Inventory, profile: TrustedProfile
) -> tuple[WorkspaceInput, ...]:
    from orchestra.security.js_metadata import validate_js
    from orchestra.security.lock_metadata import validate_uv

    contents = dict(inventory.content_items)
    require(
        not any(unsupported_manifest(p) for p in contents),
        "unsupported_stack_or_lock",
    )
    manifests = {
        p: data
        for p, data in contents.items()
        if Path(p).name in {"pyproject.toml", "package.json", "pnpm-workspace.yaml"}
    }
    locks = sorted(
        p
        for p in contents
        if Path(p).name in {"uv.lock", "pnpm-lock.yaml", "package-lock.json"}
    )
    require(
        len(manifests) + len(locks) <= profile.limit("manifest_count"), "scope_overflow"
    )
    require(len(locks) <= profile.limit("root_count"), "scope_overflow")
    result: list[WorkspaceInput] = []
    owners: set[str] = set()
    js_roots: set[str] = set()
    for path in locks:
        if path.endswith("uv.lock"):
            workspace = validate_uv(manifests, path, contents[path], profile)
        else:
            root = str(Path(path).parent)
            require(root not in js_roots, "ambiguous_lock")
            js_roots.add(root)
            workspace = validate_js(manifests, path, contents[path], profile)
        require(not owners.intersection(workspace.manifests), "ambiguous_lock")
        owners.update(workspace.manifests)
        result.append(workspace)
    _manifest_coverage(manifests, owners, js_roots)
    _source_coverage(contents, result)
    return tuple(result)


def verify_ci_snapshot(
    repo: Path,
    repository: str,
    inventory: Inventory,
    declaration: dict[str, Any],
    git: Path,
    cap: int,
) -> None:
    workflows = {
        f.path
        for f in inventory.files
        if f.path.startswith((".forgejo/workflows/", ".github/workflows/"))
        and Path(f.path).suffix in {".yaml", ".yml"}
    }
    retained = {
        row["path"]: row["revision"]
        for row in declaration["workflow_revisions"]
        if row["repository"] == repository
    }
    require(set(retained) == workflows, "configuration_drift")
    for path, revision in retained.items():
        require(
            git_bytes(repo, git, ("cat-file", "blob", revision + ":" + path), cap)
            == inventory.content(path),
            "configuration_drift",
        )


def _decode_path(raw: bytes) -> str:
    try:
        return safe_path(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, ProfileError):
        raise ProfileError("unsupported_path") from None


def _clean(repo: Path, git: Path, prefixes: tuple[str, ...]) -> None:
    status = git_bytes(
        repo,
        git,
        (
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--ignored=matching",
        ),
    )
    for record in status.split(b"\0"):
        if not record:
            continue
        require(
            record.startswith(b"!! ")
            and excluded(_decode_path(record[3:].rstrip(b"/")), prefixes),
            "scope_drift",
        )


def _tree_files(
    repo: Path, git: Path, head: str, profile: TrustedProfile
) -> tuple[tuple[FileInput, ...], tuple[tuple[str, bytes], ...]]:
    records, contents, aggregate = [], [], 0
    tree = git_bytes(repo, git, ("ls-tree", "-r", "-z", head))
    for record in tree.split(b"\0"):
        if not record:
            continue
        fields, separator, raw_path = record.partition(b"\t")
        require(bool(separator), "scope_drift")
        mode, kind, blob = fields.split(b" ")
        path = _decode_path(raw_path)
        require(mode != b"160000" and kind != b"commit", "unsupported_nested_repo")
        require(mode in {b"100644", b"100755"} and kind == b"blob", "unsupported_path")
        if excluded(path, profile.exclusions):
            continue
        blob_id = hex_digest(blob.decode("ascii"), 40)
        content = git_bytes(
            repo, git, ("cat-file", "blob", blob_id), profile.limit("blob_bytes")
        )
        aggregate += len(content)
        require(aggregate <= profile.limit("aggregate_bytes"), "scope_overflow")
        records.append(
            FileInput(
                path=path,
                mode=mode.decode(),
                blob_id=blob_id,
                sha256=hashlib.sha256(content).hexdigest(),
                size=len(content),
            )
        )
        contents.append((path, content))
        require(len(records) <= profile.limit("file_count"), "scope_overflow")
    return tuple(sorted(records, key=lambda row: row.path.encode())), tuple(
        sorted(contents)
    )


def capture_inventory(
    repo: Path, head: str, base: str, profile: TrustedProfile, git: Path
) -> Inventory:
    hex_digest(head, 40)
    hex_digest(base, 40)
    _local_git_state(repo, git)
    _clean(repo, git, profile.exclusions)
    actual = (
        git_bytes(repo, git, ("rev-parse", "--verify", "HEAD"), 4096).decode().strip()
    )
    require(actual == head, "scope_drift")
    require(
        git_bytes(repo, git, ("rev-parse", "--is-shallow-repository"), 4096).strip()
        == b"false",
        "coverage_gap",
    )
    merge_base = git_bytes(repo, git, ("merge-base", head, base), 4096).decode().strip()
    hex_digest(merge_base, 40)
    try:
        git_bytes(
            repo,
            git,
            (
                "rev-list",
                "--objects",
                "--no-object-names",
                "--missing=error",
                head,
                base,
            ),
        )
    except ProfileError:
        raise ProfileError("coverage_gap") from None
    changed_raw = git_bytes(
        repo,
        git,
        (
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            "--name-only",
            "-z",
            merge_base,
            head,
        ),
    )
    changed = tuple(
        sorted(
            {_decode_path(x) for x in changed_raw.split(b"\0") if x},
            key=lambda x: x.encode(),
        )
    )
    require(
        not any(
            excluded(path, profile.exclusions) and relevant(path) for path in changed
        ),
        "coverage_gap",
    )
    files, contents = _tree_files(repo, git, head, profile)
    result = Inventory(
        head_sha=head,
        base_sha=base,
        merge_base_sha=merge_base,
        files=files,
        changed=changed,
        content_items=contents,
    )
    result.verify_worktree(repo)
    return result
