"""Private metadata-only publication uses synthetic temporary directories."""

import os
from pathlib import Path

import pytest

from orchestra.dashboard.shadow_store import CommitState, commit_receipt, read_receipt


def metadata():
    return {
        "schema": "shadow-observation/1",
        "nonce": "1" * 32,
        "verdict": "BLOCK",
        "phase": "preflight",
        "profile_id": "m3s-full-boundary/1",
        "final_generated": "2026-10-27T12:00:00.000001Z",
        "final_board_digest": "a" * 64,
        "prior_generated": "2026-10-27T11:00:00.000001Z",
        "prior_board_digest": "b" * 64,
        "witness_sha": "c" * 64,
        "code_pins": [],
        "coverage": dict.fromkeys(
            ("roots", "roster", "opaque", "callables", "frame", "postgraph", "publish"),
            False,
        ),
        "counts": dict.fromkeys(
            ("items", "nodes", "edges", "callbacks", "probes", "differences"), 0
        ),
        "shape_sha": "d" * 64,
        "alias_sha": "e" * 64,
        "diffs": [{"code": "root_schema", "path": "$roots.asm", "count": 1}],
    }


def private_root(tmp_path: Path) -> Path:
    root = tmp_path / "shadow"
    root.mkdir(mode=0o700)
    return root


def test_receipt_requires_trusted_commit_capability_and_exact_filename(
    tmp_path: Path,
) -> None:
    root = private_root(tmp_path)
    result = commit_receipt(root, metadata())
    assert result.state is CommitState.COMMITTED and result.receipt is not None
    assert read_receipt(root, result.receipt) == metadata()
    assert (
        root / "receipts" / result.receipt.final_name
    ).stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError):
        read_receipt(root, None)
    assert (root / ".pending" / ("1" * 32 + ".tmp")).exists()  # no cleanup


def test_collision_never_overwrites_or_retries(tmp_path: Path) -> None:
    root = private_root(tmp_path)
    first = commit_receipt(root, metadata())
    second = commit_receipt(root, metadata())
    assert first.state is CommitState.COMMITTED
    assert second.state is CommitState.NOT_COMMITTED and second.receipt is None
    assert read_receipt(root, first.receipt) == metadata()


def test_complete_temp_without_commit_is_never_consumable(
    tmp_path: Path, monkeypatch
) -> None:
    root = private_root(tmp_path)

    def fail(*args, **kwargs):
        raise OSError("synthetic failure")

    monkeypatch.setattr(os, "link", fail)
    result = commit_receipt(root, metadata())
    assert result.state is CommitState.NOT_COMMITTED and result.receipt is None
    assert (root / ".pending" / ("1" * 32 + ".tmp")).exists()
    with pytest.raises(ValueError):
        read_receipt(root, None)


def test_link_success_final_fsync_failure_is_unknown(
    tmp_path: Path, monkeypatch
) -> None:
    root = private_root(tmp_path)
    real = os.fsync

    def fsync(fd):
        if os.path.basename(os.readlink(f"/proc/self/fd/{fd}")) == "receipts":
            raise OSError("synthetic fsync failure")
        real(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    result = commit_receipt(root, metadata())
    assert result.state is CommitState.COMMIT_UNKNOWN and result.receipt is None
    assert len(list((root / "receipts").iterdir())) == 1


def test_subdirectory_replacement_after_link_is_unknown(
    tmp_path: Path, monkeypatch
) -> None:
    root = private_root(tmp_path)
    real = os.fsync

    def fsync(fd):
        real(fd)
        if os.path.basename(os.readlink(f"/proc/self/fd/{fd}")) == "receipts":
            (root / "receipts").rename(root / "retained-old-receipts")
            (root / "receipts").mkdir(mode=0o700)

    monkeypatch.setattr(os, "fsync", fsync)
    result = commit_receipt(root, metadata())
    assert result.state is CommitState.COMMIT_UNKNOWN and result.receipt is None


@pytest.mark.parametrize("kind", ["unknown", "path", "message", "oversize", "private"])
def test_metadata_rejects_values_outside_closed_receipt(
    tmp_path: Path, kind: str
) -> None:
    payload = metadata()
    if kind == "unknown":
        payload["headers"] = "PRIVATE_CANARY"
    if kind == "path":
        payload["diffs"][0]["path"] = "$roots.PRIVATE_CANARY"
    if kind == "message":
        payload["diffs"][0]["code"] = "PRIVATE_CANARY"
    if kind == "oversize":
        payload["diffs"] *= 101
    if kind == "private":
        payload["counts"]["items"] = "PRIVATE_CANARY"
    root = private_root(tmp_path)
    result = commit_receipt(root, payload)
    assert result.state is CommitState.NOT_COMMITTED
    assert list(root.iterdir()) == []


def test_reconstructed_receipt_values_are_not_a_commit_capability(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    root = private_root(tmp_path)
    result = commit_receipt(root, metadata())
    assert result.receipt is not None
    reconstructed = replace(result.receipt)
    with pytest.raises(ValueError, match="receipt"):
        read_receipt(root, reconstructed)
