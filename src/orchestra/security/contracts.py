"""Bounded immutable producer records, not evidence of scanner execution or trust."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, fields
from typing import cast
from uuid import UUID

LIMIT = 65_536
FAMILIES = frozenset(
    [
        "gitleaks",
        "patterns",
        "bandit",
        "python-export",
        "python-audit",
        "javascript-audit",
        "osv",
        "trivy",
    ]
)
ADAPTERS = {
    "gitleaks-json-8.30.1": ("gitleaks", "8.30.1", 10),
    "portable-patterns-v1": ("patterns", "1", 0),
    "bandit-json-1.9.4": ("bandit", "1.9.4", 1),
    "uv-pylock-0.13.5": ("python-export", "0.13.5", 0),
    "pip-audit-json-2.10.1": ("python-audit", "2.10.1", 1),
    "pnpm-json-10.34.8": ("javascript-audit", "10.34.8", 1),
    "npm-json-11.21.1": ("javascript-audit", "11.21.1", 1),
    "osv-json-2.7.0": ("osv", "2.7.0", 1),
    "trivy-json-0.76.1": ("trivy", "0.76.1", 10),
}
NA_REASONS = {
    "bandit": "no_python_sources",
    "python-export": "no_python_dependency_scope",
    "python-audit": "no_python_dependency_scope",
    "javascript-audit": "no_js_dependency_scope",
    "osv": "no_supported_dependency_scope",
    "trivy": "ci_does_not_require_trivy",
}
ERROR_CODES = frozenset(
    [
        "invalid_request",
        "identity_mismatch",
        "profile_mismatch",
        "scope_drift",
        "scope_overflow",
        "unsupported_path",
        "unsupported_nested_repo",
        "unsupported_stack_or_lock",
        "ambiguous_lock",
        "missing_lockfile",
        "stale_lock",
        "unsupported_dependency_syntax",
        "unsupported_dependency_source",
        "configuration_drift",
        "missing_binary",
        "unsupported_version",
        "native_error",
        "native_timeout",
        "native_overflow",
        "invalid_native_report",
        "coverage_gap",
        "evidence_overflow",
        "deadline_exceeded",
        "cancelled",
        "db_unavailable",
        "db_stale",
        "not_run",
    ]
)
STATES = frozenset(
    [
        "complete",
        "not_applicable",
        "missing_binary",
        "unsupported_version",
        "error",
        "timeout",
        "invalid_report",
        "overflow",
        "not_run",
    ]
)


class SecurityContractError(ValueError):
    """A fixed safe code, never native output, paths, or Pydantic diagnostics."""


def _require(condition: bool) -> None:
    if not condition:
        raise SecurityContractError("invalid_envelope")


def _text(value: object, bound: int) -> None:
    _require(isinstance(value, str) and bool(value))
    text = cast(str, value)
    _require(len(text.encode("utf-8")) <= bound)
    _require(not any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in text))


def _integer(value: object, low: int = 0, high: int | None = None) -> None:
    _require(type(value) is int)
    number = cast(int, value)
    _require(number >= low and (high is None or number <= high))


def _hex(value: object, length: int) -> None:
    _require(
        isinstance(value, str)
        and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None
    )


def _path(value: object) -> None:
    _text(value, 512)
    path = cast(str, value)
    _require("\\" not in path and not path.startswith("/"))
    _require(all(part not in {"", ".", ".."} for part in path.split("/")))


def _tuple(value: object, item_type: type[object]) -> None:
    _require(type(value) is tuple)
    items = cast(tuple[object, ...], value)
    _require(len(items) <= 128 and all(type(item) is item_type for item in items))


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ReceiptKey:
    family: str
    scope: str | None
    batch: int

    def __post_init__(self) -> None:
        _require(self.family in FAMILIES)
        _integer(self.batch, 0, 127)
        if self.scope is not None:
            _path(self.scope)


@dataclass(frozen=True, slots=True)
class Package:
    ecosystem: str
    name: str
    version: str

    def __post_init__(self) -> None:
        for value, limit in (
            (self.ecosystem, 32),
            (self.name, 200),
            (self.version, 100),
        ):
            _text(value, limit)


@dataclass(frozen=True, slots=True)
class Finding:
    rule_id: str
    advisory_id: str | None
    severity: str
    path: str | None
    line: int | None
    package: Package | None
    attribution: str
    attribution_basis: str

    def __post_init__(self) -> None:
        _text(self.rule_id, 100)
        if self.advisory_id is not None:
            _text(self.advisory_id, 100)
        _require(
            self.severity in {"UNKNOWN", "INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
        )
        _require(self.attribution in {"changed", "unchanged", "unknown"})
        _require(self.attribution_basis in {"source_path", "dependency_lock", "none"})
        if self.path is not None:
            _path(self.path)
        if self.line is not None:
            _integer(self.line, 1)
        _require(self.package is None or type(self.package) is Package)


@dataclass(frozen=True, slots=True)
class Gap:
    code: str
    key: ReceiptKey | None
    path: str | None

    def __post_init__(self) -> None:
        _require(self.code in ERROR_CODES)
        _require(self.key is None or type(self.key) is ReceiptKey)
        if self.path is not None:
            _path(self.path)


@dataclass(frozen=True, slots=True)
class Receipt:
    key: ReceiptKey
    adapter_id: str | None
    tool_version: str | None
    input_digest: str
    applicability: str
    applicability_reason: str | None
    state: str
    exit_code: int | None
    timed_out: bool
    stdout_bytes: int
    stderr_bytes: int
    stdout_truncated: bool
    stderr_truncated: bool
    native_digest: str | None
    scanned_count: int | None
    finding_count: int | None
    findings: tuple[Finding, ...]
    omitted_count: int
    error_code: str | None

    def __post_init__(self) -> None:
        _validate_receipt_fields(self)
        if self.applicability == "not_applicable":
            _validate_na(self)
        else:
            _validate_required(self)


def _validate_receipt_fields(item: Receipt) -> None:
    _require(type(item.key) is ReceiptKey and item.state in STATES)
    _require(item.applicability in {"required", "not_applicable"})
    _hex(item.input_digest, 64)
    if item.native_digest is not None:
        _hex(item.native_digest, 64)
    if item.exit_code is not None:
        _integer(item.exit_code, -255, 255)
    _validate_receipt_counts(item)
    _tuple(item.findings, Finding)
    _require(
        all(
            type(value) is bool
            for value in (
                item.timed_out,
                item.stdout_truncated,
                item.stderr_truncated,
            )
        )
    )
    _require(item.error_code is None or item.error_code in ERROR_CODES)
    if item.finding_count is not None:
        _require(item.finding_count == len(item.findings) + item.omitted_count)


def _validate_receipt_counts(item: Receipt) -> None:
    for value in (item.stdout_bytes, item.stderr_bytes, item.omitted_count):
        _integer(value)
    for count in (item.scanned_count, item.finding_count):
        if count is not None:
            _integer(count)


def _validate_na(item: Receipt) -> None:
    _require(item.key.family in NA_REASONS)
    _require(item.applicability_reason == NA_REASONS[item.key.family])
    _require(
        item.state == "not_applicable"
        and item.key.scope is None
        and item.key.batch == 0
    )
    _require(
        all(
            value is None
            for value in (
                item.adapter_id,
                item.tool_version,
                item.exit_code,
                item.native_digest,
                item.scanned_count,
                item.finding_count,
                item.error_code,
            )
        )
    )
    _require(
        not any(
            (
                item.timed_out,
                item.stdout_truncated,
                item.stderr_truncated,
                item.stdout_bytes,
                item.stderr_bytes,
                item.findings,
                item.omitted_count,
            )
        )
    )


def _validate_required(item: Receipt) -> None:
    _require(item.adapter_id in ADAPTERS and item.applicability_reason is None)
    family, version, findings_exit = ADAPTERS[cast(str, item.adapter_id)]
    _require(item.key.family == family and item.state != "not_applicable")
    dependency = family in {"python-export", "python-audit", "javascript-audit", "osv"}
    _require((item.key.scope is not None) == dependency)
    _require(item.key.batch == 0 or family == "bandit")
    _validate_tool_version(item.tool_version)
    _require(item.timed_out == (item.state == "timeout"))
    _validate_truncation(item.stdout_bytes, item.stdout_truncated)
    _validate_truncation(item.stderr_bytes, item.stderr_truncated)
    if item.state == "complete":
        _validate_complete_receipt(item, family, version, findings_exit)
    else:
        _require(item.error_code is not None)


def _validate_tool_version(tool_version: str | None) -> None:
    if tool_version is not None:
        _require(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}", tool_version) is not None
        )


def _validate_truncation(byte_count: int, truncated: bool) -> None:
    if byte_count > LIMIT:
        _require(truncated)


def _validate_complete_receipt(
    item: Receipt, family: str, version: str, findings_exit: int
) -> None:
    _require(item.tool_version == version and item.native_digest is not None)
    _require(item.scanned_count is not None and item.finding_count is not None)
    _require(item.error_code is None and not item.omitted_count)
    _require(not item.stdout_truncated and not item.stderr_truncated)
    _require(item.exit_code == (findings_exit if item.findings else 0))
    if family == "patterns":
        _validate_patterns(item)


def _validate_patterns(item: Receipt) -> None:
    expected = tuple(
        sorted(
            item.findings,
            key=lambda f: (
                f.path or "",
                f.line or 0,
                f.rule_id,
                f.severity,
                _canonical(asdict(f)),
            ),
        )
    )
    _require(item.findings == expected)
    digest = hashlib.sha256(
        _canonical(
            {
                "adapter_id": item.adapter_id,
                "input_digest": item.input_digest,
                "scanned_count": item.scanned_count,
                "findings": [asdict(f) for f in item.findings],
            }
        )
    ).hexdigest()
    _require(item.native_digest == digest)


@dataclass(frozen=True, slots=True)
class SecurityEnvelope:
    schema: str
    scan_id: str
    work_unit_id: str
    attempt_id: str
    repository: str
    producer_revision: str
    producer_digest: str
    profile_id: str
    profile_digest: str
    context_digest: str
    head_sha: str
    base_sha: str
    merge_base_sha: str
    scope_digest: str
    changed_digest: str
    plan_digest: str
    complete: bool
    receipts: tuple[Receipt, ...]
    gaps: tuple[Gap, ...]

    def __post_init__(self) -> None:
        _validate_envelope_fields(self)
        _validate_envelope_receipts(self)
        if self.complete:
            _validate_complete_envelope(self)


def _validate_envelope_fields(item: SecurityEnvelope) -> None:
    _require(item.schema == "orchestra.security-envelope/v1")
    for value in (item.scan_id, item.work_unit_id, item.attempt_id):
        _require(isinstance(value, str) and str(UUID(value)) == value)
    for value in (item.repository, item.profile_id):
        _text(value, 100)
    for value in (
        item.producer_revision,
        item.head_sha,
        item.base_sha,
        item.merge_base_sha,
    ):
        _hex(value, 40)
    for value in (
        item.producer_digest,
        item.profile_digest,
        item.context_digest,
        item.scope_digest,
        item.changed_digest,
        item.plan_digest,
    ):
        _hex(value, 64)
    _require(type(item.complete) is bool)
    _tuple(item.receipts, Receipt)
    _tuple(item.gaps, Gap)


def _validate_envelope_receipts(item: SecurityEnvelope) -> None:
    keys = [receipt.key for receipt in item.receipts]
    _require(len(set(keys)) == len(keys))
    for family in FAMILIES:
        family_receipts = [r for r in item.receipts if r.key.family == family]
        if any(r.applicability == "not_applicable" for r in family_receipts):
            _require(len(family_receipts) == 1)
        batches = sorted(r.key.batch for r in family_receipts if family == "bandit")
        _require(not batches or batches == list(range(len(batches))))


def _validate_complete_envelope(item: SecurityEnvelope) -> None:
    _require(not item.gaps and {r.key.family for r in item.receipts} == FAMILIES)
    _require(all(r.state in {"complete", "not_applicable"} for r in item.receipts))


def _record[T](cls: type[T], value: object, **converted: object) -> T:
    _require(type(value) is dict)
    data = cast(dict[str, object], value)
    _require(data.keys() == {field.name for field in fields(cls)})  # type: ignore[arg-type]
    return cls(**(data | converted))


def _array[T](value: object, convert: Callable[[object], T]) -> tuple[T, ...]:
    _require(type(value) is list)
    values = cast(list[object], value)
    _require(len(values) <= 128)
    return tuple(convert(v) for v in values)


def _object(value: object) -> Mapping[str, object]:
    _require(type(value) is dict)
    return cast(dict[str, object], value)


def _finding(value: object) -> Finding:
    data = _object(value)
    package = data.get("package")
    return _record(
        Finding, data, package=None if package is None else _record(Package, package)
    )


def _receipt(value: object) -> Receipt:
    data = _object(value)
    return _record(
        Receipt,
        data,
        key=_record(ReceiptKey, data["key"]),
        findings=_array(data["findings"], _finding),
    )


def _gap(value: object) -> Gap:
    data = _object(value)
    key = data.get("key")
    return _record(Gap, data, key=None if key is None else _record(ReceiptKey, key))


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _invalid_number(value: str) -> object:
    raise SecurityContractError("invalid_json")


def _check_depth(text: str) -> None:
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
            if depth > 16:
                raise SecurityContractError("depth_limit")
        elif char in "]}":
            depth -= 1


def parse_envelope(raw: bytes) -> SecurityEnvelope:
    """Validate structure only; expected plan, process and policy remain unverified."""
    if type(raw) is not bytes or len(raw) > LIMIT:
        raise SecurityContractError("report_size")
    try:
        text = raw.decode("utf-8", errors="strict")
        _check_depth(text)
        data = _object(
            json.loads(
                text,
                object_pairs_hook=_unique,
                parse_float=_invalid_number,
                parse_constant=_invalid_number,
            )
        )
        return _record(
            SecurityEnvelope,
            data,
            receipts=_array(data["receipts"], _receipt),
            gaps=_array(data["gaps"], _gap),
        )
    except SecurityContractError:
        raise
    except (ValueError, TypeError, KeyError, RecursionError):
        raise SecurityContractError("invalid_envelope") from None


def serialize_envelope(envelope: SecurityEnvelope) -> bytes:
    """Serialize the entire record or reject; never trim findings to fit."""
    if type(envelope) is not SecurityEnvelope:
        raise SecurityContractError("invalid_envelope")
    raw = _canonical(asdict(envelope))
    parse_envelope(raw)
    return raw
