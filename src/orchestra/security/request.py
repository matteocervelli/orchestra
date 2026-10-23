"""Private request verification independently recomputes candidate scope and plan."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import time
from typing import Any, Self
from uuid import UUID

from orchestra.security.contracts import Package, ReceiptKey
from orchestra.security.inventory import (
    Inventory,
    WorkspaceInput,
    _workspaces,
    capture_inventory,
    pattern_source,
    verify_ci_snapshot,
)
from orchestra.security.process import observe_executable, verify_identity
from orchestra.security.profile import (
    CATALOG,
    FAMILY_ORDER,
    ProfileError,
    TrustedProfile,
    _context_wire,
    canonical,
    decode_json,
    digest,
    exact,
    hex_digest,
    require,
    safe_text,
)

_NA = {
    "bandit": "no_python_sources",
    "python-export": "no_python_dependency_scope",
    "python-audit": "no_python_dependency_scope",
    "javascript-audit": "no_js_dependency_scope",
    "osv": "no_supported_dependency_scope",
    "trivy": "ci_does_not_require_trivy",
}


def _batches(paths: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    result: list[tuple[str, ...]] = []
    batch: list[str] = []
    size = 0
    for path in paths:
        count = len(path.encode()) + 1
        require(count <= 24576, "scope_overflow")
        if size + count > 24576:
            result.append(tuple(batch))
            batch, size = [], 0
        batch.append(path)
        size += count
    if batch:
        result.append(tuple(batch))
    require(len(result) <= 128, "scope_overflow")
    return tuple(result)


def _absolute(value: object) -> str:
    text = safe_text(value, 4096)
    path = Path(text)
    require(
        path.is_absolute() and str(path) == text and ".." not in path.parts,
        "configuration_drift",
    )
    return text


def _runtime_wire(data: object) -> dict[str, Any]:
    data = exact(
        data,
        {
            "python",
            "producer",
            "tools",
            "git",
            "scratch_root",
            "runner_capability_revision",
            "capability_digest",
            "registry_capability_digest",
        },
    )
    for name, keys, path_key in (
        ("python", {"absolute_path", "provisioning_digest"}, "absolute_path"),
        ("producer", {"absolute_root", "revision", "manifest_digest"}, "absolute_root"),
        ("git", {"absolute_path", "sha256", "provisioning_digest"}, "absolute_path"),
    ):
        item = exact(data[name], keys)
        _absolute(item[path_key])
        for key in keys - {path_key}:
            hex_digest(item[key], 40 if key == "revision" else 64)
    tools = data["tools"]
    require(type(tools) is list)
    ids = []
    bindings: dict[str, tuple[str, str]] = {}
    for tool in tools:
        tool = exact(
            tool, {"adapter_id", "absolute_path", "sha256", "provisioning_digest"}
        )
        ids.append(tool["adapter_id"])
        path = _absolute(tool["absolute_path"])
        identity = (hex_digest(tool["sha256"]), hex_digest(tool["provisioning_digest"]))
        require(
            path not in bindings or bindings[path] == identity, "configuration_drift"
        )
        bindings[path] = identity
    require(ids == sorted(set(CATALOG) - {"portable-patterns-v1"}))
    _absolute(data["scratch_root"])
    safe_text(data["runner_capability_revision"])
    hex_digest(data["capability_digest"])
    if data["registry_capability_digest"] is not None:
        hex_digest(data["registry_capability_digest"])
    return data


@dataclass(frozen=True)
class RuntimeBindings:
    """Retained logical pins, not evidence that these paths are admitted."""

    payload: bytes = field(repr=False)

    def __post_init__(self) -> None:
        _runtime_wire(decode_json(self.payload))

    @classmethod
    def from_wire(cls, value: object) -> Self:
        return cls(payload=canonical(_runtime_wire(value)))

    def wire(self) -> dict[str, Any]:
        return decode_json(self.payload)

    @property
    def digest(self) -> str:
        data = self.wire()
        data.pop("scratch_root")
        for name in ("python", "producer", "git"):
            data[name] = {
                k: v for k, v in data[name].items() if not k.startswith("absolute_")
            }
        data["tools"] = [
            {k: v for k, v in tool.items() if k != "absolute_path"}
            for tool in data["tools"]
        ]
        return digest(data)


@dataclass(frozen=True)
class ScanContext:
    payload: bytes = field(repr=False)

    def __post_init__(self) -> None:
        _context_wire(decode_json(self.payload))

    @classmethod
    def from_wire(cls, value: object) -> Self:
        return cls(payload=canonical(_context_wire(value)))

    def wire(self) -> dict[str, Any]:
        return decode_json(self.payload)

    @property
    def digest(self) -> str:
        return digest(self.wire())

    def validate_now(self, runtime: RuntimeBindings, now_epoch: int) -> None:
        data = self.wire()
        require(data["runtime_digest"] == runtime.digest, "configuration_drift")
        if data["ci_declaration"]["requires_trivy"]:
            db = data["trivy_db"]
            require(db is not None, "db_unavailable")
            require(
                type(now_epoch) is int
                and db["updated_at_epoch"] <= db["verified_at_epoch"] <= now_epoch
                and now_epoch - db["updated_at_epoch"] <= 86400,
                "db_stale",
            )


@dataclass(frozen=True)
class PlannedUnit:
    key: ReceiptKey
    adapter_id: str | None
    applicability: str
    applicability_reason: str | None
    input_paths: tuple[str, ...] = field(repr=False)
    input_digest: str
    expected_packages: tuple[Package, ...] = field(repr=False)
    depends_on: tuple[ReceiptKey, ...]

    def wire(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScanRequest:
    payload: bytes = field(repr=False)
    inventory: Inventory = field(repr=False)
    units: tuple[PlannedUnit, ...] = field(repr=False)

    def wire(self) -> dict[str, Any]:
        return decode_json(self.payload, 2097152)


def _unit(
    family: str,
    adapter: str | None,
    paths: tuple[str, ...],
    packages: tuple[Package, ...],
    inventory: Inventory,
    profile: TrustedProfile,
    context: ScanContext,
    *,
    scope: str | None = None,
    batch: int = 0,
    depends: tuple[ReceiptKey, ...] = (),
) -> PlannedUnit:
    key = ReceiptKey(family=family, scope=scope, batch=batch)
    by_path = {f.path: f.wire() for f in inventory.files}
    inputs = {
        "key": asdict(key),
        "adapter_id": adapter,
        "profile_digest": profile.digest,
        "context_digest": context.digest,
        "inputs": [by_path[p] for p in paths],
        "expected_packages": [asdict(p) for p in packages],
        "depends_on": [asdict(d) for d in depends],
    }
    if family == "gitleaks":
        inputs.update(
            head_sha=inventory.head_sha,
            base_sha=inventory.base_sha,
            merge_base_sha=inventory.merge_base_sha,
        )
    return PlannedUnit(
        key=key,
        adapter_id=adapter,
        applicability="required" if adapter else "not_applicable",
        applicability_reason=None if adapter else _NA[family],
        input_paths=paths,
        input_digest=digest(inputs),
        expected_packages=packages,
        depends_on=depends,
    )


def _dependency_units(
    workspaces: tuple[WorkspaceInput, ...], make: Callable[..., PlannedUnit]
) -> list[PlannedUnit]:
    result: list[PlannedUnit] = []
    for workspace in workspaces:
        paths, packages, scope = (
            workspace.governing_inputs,
            workspace.packages,
            workspace.lock_path,
        )
        if workspace.kind == "uv1-r3":
            export = make(
                "python-export", "uv-pylock-0.13.5", paths, packages, scope=scope
            )
            result += [
                export,
                make(
                    "python-audit",
                    "pip-audit-json-2.10.1",
                    paths,
                    packages,
                    scope=scope,
                    depends=(export.key,),
                ),
            ]
        else:
            adapter = (
                "pnpm-json-10.34.8" if workspace.kind == "pnpm9" else "npm-json-11.21.1"
            )
            result.append(
                make("javascript-audit", adapter, paths, packages, scope=scope)
            )
        result.append(make("osv", "osv-json-2.7.0", paths, packages, scope=scope))
    return result


def _complete_units(
    result: list[PlannedUnit], make: Callable[..., PlannedUnit], profile: TrustedProfile
) -> tuple[PlannedUnit, ...]:
    for family in FAMILY_ORDER:
        if not any(u.key.family == family for u in result):
            result.append(make(family, None))
    result.sort(
        key=lambda u: (
            FAMILY_ORDER.index(u.key.family),
            (u.key.scope or "").encode(),
            u.key.batch,
        )
    )
    require(len(result) <= profile.limit("receipt_count"), "scope_overflow")
    return tuple(result)


def _units(
    inventory: Inventory,
    workspaces: tuple[WorkspaceInput, ...],
    profile: TrustedProfile,
    context: ScanContext,
) -> tuple[PlannedUnit, ...]:
    all_paths = tuple(f.path for f in inventory.files)

    def make(
        family: str,
        adapter: str | None,
        paths: tuple[str, ...] = all_paths,
        packages: tuple[Package, ...] = (),
        **kwargs: Any,
    ) -> PlannedUnit:
        return _unit(
            family, adapter, paths, packages, inventory, profile, context, **kwargs
        )

    result = [
        make("gitleaks", "gitleaks-json-8.30.1"),
        make(
            "patterns",
            "portable-patterns-v1",
            tuple(p for p in all_paths if pattern_source(p)),
        ),
    ]
    python = tuple(p for p in all_paths if p.endswith(".py"))
    result.extend(
        make("bandit", "bandit-json-1.9.4", batch, batch=i)
        for i, batch in enumerate(_batches(python))
    )
    result.extend(_dependency_units(workspaces, make))
    required_trivy = context.wire()["ci_declaration"]["requires_trivy"]
    result.append(make("trivy", "trivy-json-0.76.1" if required_trivy else None))
    return _complete_units(result, make, profile)


def _request_shape(data: dict[str, Any]) -> None:
    identity = {
        "scan_id",
        "work_unit_id",
        "attempt_id",
        "repository",
        "producer_revision",
        "producer_digest",
        "profile_id",
        "profile_digest",
        "context_digest",
        "head_sha",
        "base_sha",
        "merge_base_sha",
        "scope_digest",
        "changed_digest",
        "plan_digest",
    }
    exact(
        data,
        identity
        | {
            "schema",
            "repo_root",
            "scratch_root",
            "runtime",
            "context",
            "files",
            "changed",
            "workspaces",
            "units",
            "gaps",
        },
    )
    require(data["schema"] == "orchestra.security-request/v1")


def _request_ids(data: dict[str, Any], profile: TrustedProfile) -> None:
    for name in ("scan_id", "work_unit_id", "attempt_id"):
        try:
            require(str(UUID(data[name])) == data[name])
        except (ValueError, TypeError, AttributeError):
            raise ProfileError("invalid_request") from None
    safe_text(data["repository"])
    for name in ("producer_revision", "head_sha", "base_sha", "merge_base_sha"):
        hex_digest(data[name], 40)
    for name in (
        "producer_digest",
        "profile_digest",
        "context_digest",
        "scope_digest",
        "changed_digest",
        "plan_digest",
    ):
        hex_digest(data[name])
    require(
        data["profile_id"] == profile.profile_id
        and data["profile_digest"] == profile.digest,
        "profile_mismatch",
    )


def _request_bindings(
    data: dict[str, Any], now_epoch: int | None
) -> tuple[RuntimeBindings, ScanContext, Path, Path]:
    runtime, context = (
        RuntimeBindings.from_wire(data["runtime"]),
        ScanContext.from_wire(data["context"]),
    )
    context.validate_now(runtime, int(time()) if now_epoch is None else now_epoch)
    require(context.digest == data["context_digest"], "identity_mismatch")
    binding = runtime.wire()
    require(
        data["scratch_root"] == binding["scratch_root"]
        and data["producer_revision"] == binding["producer"]["revision"]
        and data["producer_digest"] == binding["producer"]["manifest_digest"],
        "identity_mismatch",
    )
    repo, git = (
        Path(_absolute(data["repo_root"])),
        Path(binding["git"]["absolute_path"]),
    )
    return runtime, context, repo, git


def _verify_records(
    data: dict[str, Any],
    inventory: Inventory,
    workspaces: tuple[WorkspaceInput, ...],
    units: tuple[PlannedUnit, ...],
    context: ScanContext,
) -> None:
    records = {
        "files": [f.wire() for f in inventory.files],
        "changed": [{"path": p} for p in inventory.changed],
        "workspaces": [w.wire() for w in workspaces],
        "units": [u.wire() for u in units],
        "gaps": [],
    }
    require(
        all(canonical(data[k]) == canonical(v) for k, v in records.items()),
        "scope_drift",
    )
    scope = {
        k: data[k]
        for k in (
            "repository",
            "head_sha",
            "base_sha",
            "merge_base_sha",
            "profile_digest",
        )
    }
    scope.update({k: records[k] for k in ("files", "changed", "workspaces", "units")})
    require(
        inventory.merge_base_sha == data["merge_base_sha"]
        and digest(scope) == data["scope_digest"]
        and digest(records["changed"]) == data["changed_digest"],
        "scope_drift",
    )
    plan = {
        "schema": "orchestra.security-plan/v1",
        "scope_digest": data["scope_digest"],
        "changed_digest": data["changed_digest"],
        "context_digest": context.digest,
        "units": records["units"],
        "gaps": [],
    }
    require(digest(plan) == data["plan_digest"], "scope_drift")


def verify_request(
    raw: bytes, profile: TrustedProfile, *, now_epoch: int | None = None
) -> ScanRequest:
    data = decode_json(raw, profile.limit("request_bytes"))
    _request_shape(data)
    _request_ids(data, profile)
    runtime, context, repo, git = _request_bindings(data, now_epoch)
    git_identity = observe_executable(git, runtime.wire()["git"]["sha256"])
    inventory = capture_inventory(
        repo, data["head_sha"], data["base_sha"], profile, git
    )
    workspaces = _workspaces(inventory, profile)
    verify_ci_snapshot(
        repo,
        data["repository"],
        inventory,
        context.wire()["ci_declaration"],
        git,
        profile.limit("blob_bytes"),
    )
    units = _units(inventory, workspaces, profile, context)
    _verify_records(data, inventory, workspaces, units, context)
    inventory.verify_worktree(repo)
    verify_identity(git_identity)
    return ScanRequest(payload=canonical(data), inventory=inventory, units=units)
