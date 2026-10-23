"""Synthetic wire tests; parsing a report is never publication authorization."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any

import pytest

from orchestra.security.contracts import (
    SecurityContractError,
    parse_envelope,
    serialize_envelope,
)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def receipt(family: str) -> dict[str, Any]:
    required = family in {"gitleaks", "patterns"}
    reasons = {
        "bandit": "no_python_sources",
        "python-export": "no_python_dependency_scope",
        "python-audit": "no_python_dependency_scope",
        "javascript-audit": "no_js_dependency_scope",
        "osv": "no_supported_dependency_scope",
        "trivy": "ci_does_not_require_trivy",
    }
    value: dict[str, Any] = {
        "key": {"family": family, "scope": None, "batch": 0},
        "adapter_id": (
            f"{family}-json-8.30.1" if family == "gitleaks" else "portable-patterns-v1"
        )
        if required
        else None,
        "tool_version": ("8.30.1" if family == "gitleaks" else "1")
        if required
        else None,
        "input_digest": "a" * 64,
        "applicability": "required" if required else "not_applicable",
        "applicability_reason": None if required else reasons[family],
        "state": "complete" if required else "not_applicable",
        "exit_code": 0 if required else None,
        "timed_out": False,
        "stdout_bytes": 0,
        "stderr_bytes": 0,
        "stdout_truncated": False,
        "stderr_truncated": False,
        "native_digest": "b" * 64 if required else None,
        "scanned_count": 1 if required else None,
        "finding_count": 0 if required else None,
        "findings": [],
        "omitted_count": 0,
        "error_code": None,
    }
    if family == "patterns":
        seal_patterns(value)
    return value


def seal_patterns(value: dict[str, Any]) -> None:
    content = {
        key: value[key]
        for key in ("adapter_id", "input_digest", "scanned_count", "findings")
    }
    value["native_digest"] = hashlib.sha256(canonical(content)).hexdigest()


def fixture() -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": "orchestra.security-envelope/v1",
        "scan_id": "11111111-1111-4111-8111-111111111111",
        "work_unit_id": "22222222-2222-4222-8222-222222222222",
        "attempt_id": "33333333-3333-4333-8333-333333333333",
        "repository": "synthetic",
        "producer_revision": "a" * 40,
        "profile_id": "pilot-v1",
        "complete": True,
        "receipts": [
            receipt(name)
            for name in (
                "gitleaks",
                "patterns",
                "bandit",
                "python-export",
                "python-audit",
                "javascript-audit",
                "osv",
                "trivy",
            )
        ],
        "gaps": [],
    }
    for name in (
        "producer_digest",
        "profile_digest",
        "context_digest",
        "scope_digest",
        "changed_digest",
        "plan_digest",
    ):
        value[name] = "c" * 64
    for name in ("head_sha", "base_sha", "merge_base_sha"):
        value[name] = "d" * 40
    return value


def finding() -> dict[str, Any]:
    return {
        "rule_id": "SYN-01",
        "advisory_id": None,
        "severity": "HIGH",
        "path": "src/example.py",
        "line": 2,
        "package": None,
        "attribution": "changed",
        "attribution_basis": "source_path",
    }


def workspace_fixture() -> dict[str, Any]:
    value = fixture()
    value["receipts"] = [
        r
        for r in value["receipts"]
        if r["key"]["family"] not in {"bandit", "python-export", "python-audit", "osv"}
    ]
    definitions = [
        ("bandit", "bandit-json-1.9.4", "1.9.4", None, batch) for batch in (0, 1)
    ]
    definitions += [
        (family, adapter, version, scope, 0)
        for scope in ("uv.lock", "backend/uv.lock")
        for family, adapter, version in (
            ("python-export", "uv-pylock-0.13.5", "0.13.5"),
            ("python-audit", "pip-audit-json-2.10.1", "2.10.1"),
            ("osv", "osv-json-2.7.0", "2.7.0"),
        )
    ]
    for family, adapter, version, scope, batch in definitions:
        item = receipt("gitleaks")
        item.update(
            key={"family": family, "scope": scope, "batch": batch},
            adapter_id=adapter,
            tool_version=version,
        )
        value["receipts"].append(item)
    return value


def wire_cases() -> list[tuple[str, bytes, bool]]:
    """The same raw corpus is executed by each real boundary in its own package."""
    cases = [
        ("minimal", canonical(fixture()), True),
        ("nested-workspaces-batches", canonical(workspace_fixture()), True),
    ]
    mixed = workspace_fixture()
    mixed["receipts"].append(receipt("osv"))
    cases.append(("mixed-na-required", canonical(mixed), False))
    gap = workspace_fixture()
    next(
        r
        for r in gap["receipts"]
        if r["key"] == {"family": "bandit", "scope": None, "batch": 1}
    )["key"]["batch"] = 2
    cases.append(("noncontiguous-batches", canonical(gap), False))
    for field, value in (
        ("exit_code", True),
        ("tool_version", "unknown"),
        ("adapter_id", "unknown"),
        ("finding_count", 21),
        ("omitted_count", 1),
        ("timed_out", True),
        ("stdout_truncated", True),
        ("error_code", "native_error"),
    ):
        malformed = fixture()
        malformed["receipts"][0][field] = value
        cases.append(("receipt-" + field, canonical(malformed), False))
    for name, value in (
        ("unknown-schema", b'{"schema":"unknown"}'),
        ("duplicate-object-key", b'{"x":{"y":0,"y":1}}'),
        ("nonfinite", b'{"x":NaN}'),
        ("float", b'{"x":1.0}'),
        ("invalid-utf8", b"\xff"),
        ("depth", b"[" * 17 + b"0" + b"]" * 17),
    ):
        cases.append((name, value, False))
    return cases


@pytest.mark.parametrize(
    "label,payload,accepted",
    wire_cases(),
    ids=lambda value: (value if isinstance(value, str) else None),
)
def test_common_wire_corpus(label: str, payload: bytes, accepted: bool) -> None:
    del label
    if accepted:
        assert serialize_envelope(parse_envelope(payload))
    else:
        with pytest.raises(SecurityContractError):
            parse_envelope(payload)


def test_complete_fixture_roundtrips_immutably() -> None:
    envelope = parse_envelope(canonical(fixture()))
    assert parse_envelope(serialize_envelope(envelope)) == envelope
    assert isinstance(envelope.receipts, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        envelope.complete = False  # type: ignore[misc]


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\xff",
        b"\xef\xbb\xbf{}",
        b"{}{}",
        b"[]",
        b"null",
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":1.2}',
        b'{"schema":"private-value","schema":"duplicate"}',
        b'{"x":{"hidden":1,"hidden":2}}',
        b'"' + b"\\ud800" + b'"',
    ],
)
def test_malformed_wire_has_safe_error(raw: bytes) -> None:
    with pytest.raises(SecurityContractError) as error:
        parse_envelope(raw)
    assert "private-value" not in str(error.value)
    assert len(str(error.value)) < 100


def test_capture_byte_limit_includes_whitespace() -> None:
    raw = canonical(fixture())
    assert parse_envelope(raw + b" " * (65536 - len(raw))).complete
    with pytest.raises(SecurityContractError):
        parse_envelope(raw + b" " * (65537 - len(raw)))


def test_depth_limit_precedes_model_validation() -> None:
    with pytest.raises(SecurityContractError, match="depth_limit"):
        parse_envelope(b"[" * 17 + b"0" + b"]" * 17)


def test_delimiters_inside_strings_are_not_depth() -> None:
    value = fixture()
    value["repository"] = "{" * 90
    assert parse_envelope(canonical(value)).repository == "{" * 90


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "orchestra.security-envelope/v2"),
        ("scan_id", 1),
        ("attempt_id", "not-a-uuid"),
        ("repository", ""),
        ("producer_revision", "A" * 40),
        ("profile_digest", "z" * 64),
        ("complete", 1),
        ("complete", "true"),
        ("receipts", {}),
        ("gaps", None),
        ("private_message", "private-value"),
    ],
)
def test_top_level_strict_fields(field: str, value: object) -> None:
    payload = fixture()
    payload[field] = value
    with pytest.raises(SecurityContractError):
        parse_envelope(canonical(payload))


@pytest.mark.parametrize(
    "field,value",
    [
        ("adapter_id", "unknown"),
        ("tool_version", "9.0"),
        ("tool_version", "x" * 65),
        ("tool_version", "8.30.1\n"),
        ("exit_code", True),
        ("exit_code", 256),
        ("exit_code", 1),
        ("scanned_count", True),
        ("finding_count", False),
        ("finding_count", 1),
        ("omitted_count", 1),
        ("stdout_bytes", -1),
        ("stderr_bytes", 1.0),
        ("stdout_truncated", True),
        ("timed_out", True),
        ("applicability_reason", "no_python_sources"),
        ("state", "skipped"),
        ("error_code", "native_error"),
        ("raw_stderr", "private-value"),
    ],
)
def test_required_receipt_contradictions(field: str, value: object) -> None:
    payload = fixture()
    payload["receipts"][0][field] = value
    with pytest.raises(SecurityContractError):
        parse_envelope(canonical(payload))


@pytest.mark.parametrize(
    "field,value",
    [
        ("adapter_id", "bandit-json-1.9.4"),
        ("exit_code", 0),
        ("applicability_reason", None),
        ("applicability_reason", "no_js_dependency_scope"),
        ("state", "complete"),
        ("native_digest", "a" * 64),
        ("stdout_bytes", 1),
        ("scanned_count", 0),
        ("error_code", "native_error"),
    ],
)
def test_na_receipt_cannot_claim_execution(field: str, value: object) -> None:
    payload = fixture()
    payload["receipts"][2][field] = value
    with pytest.raises(SecurityContractError):
        parse_envelope(canonical(payload))


@pytest.mark.parametrize(
    "scope",
    [".", "", "../a", "a/../b", "/a", "a//b", "a\\b", "a/./b", "a\n", "a" * 513],
)
def test_unsafe_path_rejected(scope: str) -> None:
    payload = fixture()
    item = finding()
    item["path"] = scope
    payload["receipts"][0].update(findings=[item], finding_count=1, exit_code=10)
    with pytest.raises(SecurityContractError):
        parse_envelope(canonical(payload))


def test_key_family_scope_and_batches_are_strict() -> None:
    for key in (
        {"family": "other", "scope": None, "batch": 0},
        {"family": "gitleaks", "scope": ".", "batch": 0},
        {"family": "gitleaks", "scope": None, "batch": True},
        {"family": "gitleaks", "scope": None, "batch": 128},
    ):
        payload = fixture()
        payload["receipts"][0]["key"] = key
        with pytest.raises(SecurityContractError):
            parse_envelope(canonical(payload))


def test_duplicate_receipts_and_incomplete_complete_claim_rejected() -> None:
    payload = fixture()
    payload["receipts"].append(payload["receipts"][0])
    with pytest.raises(SecurityContractError):
        parse_envelope(canonical(payload))
    payload = fixture()
    payload["receipts"].pop()
    with pytest.raises(SecurityContractError):
        parse_envelope(canonical(payload))


def test_patterns_digest_is_full_canonical_result_not_subprocess_success() -> None:
    payload = fixture()
    patterns = payload["receipts"][1]
    patterns.update(findings=[finding()], finding_count=1)
    seal_patterns(patterns)
    envelope = parse_envelope(canonical(payload))
    assert envelope.receipts[1].exit_code == 0
    assert envelope.receipts[1].findings[0].severity == "HIGH"
    patterns["native_digest"] = "f" * 64
    with pytest.raises(SecurityContractError):
        parse_envelope(canonical(payload))


@pytest.mark.parametrize("change", ["severity", "line", "package", "snippet"])
def test_finding_shape_is_strict_and_bounded(change: str) -> None:
    payload = fixture()
    item = finding()
    item[change] = {
        "severity": "URGENT",
        "line": True,
        "package": {"ecosystem": "npm", "name": "n" * 201, "version": "1"},
        "snippet": "private-value",
    }[change]
    payload["receipts"][0].update(findings=[item], finding_count=1, exit_code=10)
    with pytest.raises(SecurityContractError):
        parse_envelope(canonical(payload))


def test_failed_receipt_is_valid_evidence_but_cannot_claim_complete() -> None:
    payload = fixture()
    payload["complete"] = False
    payload["receipts"][0].update(state="error", exit_code=1, error_code="native_error")
    assert not parse_envelope(canonical(payload)).complete
    payload["complete"] = True
    with pytest.raises(SecurityContractError):
        parse_envelope(canonical(payload))


def test_serializer_rejects_full_evidence_overflow_without_clipping() -> None:
    payload = fixture()
    payload["receipts"][0].update(exit_code=10, findings=[finding()], finding_count=1)
    envelope = parse_envelope(canonical(payload))
    original = envelope.receipts[0].findings[0]
    item = dataclasses.replace(
        envelope.receipts[0],
        exit_code=10,
        finding_count=128,
        findings=tuple(
            dataclasses.replace(
                original,
                path="p" * 500 + "/sample.py",
                rule_id=f"SYN-{index:03d}",
            )
            for index in range(128)
        ),
    )
    oversized = dataclasses.replace(envelope, receipts=(item, *envelope.receipts[1:]))
    with pytest.raises(SecurityContractError, match="report_size"):
        serialize_envelope(oversized)
    assert len(oversized.receipts[0].findings) == 128


@pytest.mark.parametrize("field", ["stdout_bytes", "scanned_count", "finding_count"])
def test_required_fields_cannot_be_omitted(field: str) -> None:
    payload = fixture()
    del payload["receipts"][0][field]
    with pytest.raises(SecurityContractError):
        parse_envelope(canonical(payload))


def test_frozen_nested_models_and_gap_bounds() -> None:
    payload = fixture()
    payload["complete"] = False
    payload["gaps"] = [{"code": "coverage_gap", "key": None, "path": "src/example.py"}]
    envelope = parse_envelope(canonical(payload))
    with pytest.raises(dataclasses.FrozenInstanceError):
        envelope.receipts[0].key.batch = 1  # type: ignore[misc]
    assert serialize_envelope(envelope)
    payload["gaps"] *= 129
    with pytest.raises(SecurityContractError):
        parse_envelope(canonical(payload))
