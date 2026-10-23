import asyncio
import hashlib
import os
import sys
from pathlib import Path

import pytest
from test_runtime_fixture import private_python

from orchestra.security.process import (
    ProtocolLaunch,
    admit_executable,
    read_native_file,
    run_protocol,
)
from orchestra.security.profile import security_environment


def test_termination_reports_a_failed_final_reap(monkeypatch) -> None:
    import subprocess
    from types import SimpleNamespace

    import orchestra.security.process as target

    def wait(*, timeout):
        raise subprocess.TimeoutExpired("synthetic", timeout)

    process = SimpleNamespace(pid=12345, returncode=None, wait=wait)
    monkeypatch.setattr(target, "_killpg", lambda *args: False)
    assert target._terminate(process) is False


def test_raw_protocol_cleanup_failure_is_io_error(tmp_path: Path, monkeypatch) -> None:
    import orchestra.security.process as target

    original = target._terminate

    def incomplete(process):
        original(process)
        return False

    monkeypatch.setattr(target, "_terminate", incomplete)
    outcome = asyncio.run(target.run_protocol(protocol_launch(tmp_path, "print('{}')")))
    assert outcome.reaped and outcome.io_error


def test_raw_protocol_incomplete_drain_is_io_error(tmp_path: Path, monkeypatch) -> None:
    import orchestra.security.process as target

    monkeypatch.setattr(target._ProtocolIO, "read", lambda *args: None)
    outcome = asyncio.run(
        target.run_protocol(protocol_launch(tmp_path, "print('{}')", deadline=0.05))
    )
    assert outcome.reaped and outcome.timed_out and outcome.io_error


@pytest.mark.parametrize("phase", ["before-spawn", "after-spawn"])
def test_live_capability_freshness_is_checked_at_process_boundaries(
    tmp_path: Path, monkeypatch, phase: str
) -> None:
    from dataclasses import replace

    from orchestra.security.profile import ProfileError

    target, path, binding, capability, _ = capability_fixture(tmp_path, monkeypatch)
    identity = target.admit_executable(
        path,
        hashlib.sha256(path.read_bytes()).hexdigest(),
        tmp_path / "candidate",
        tmp_path / "scratch",
        runtime=binding,
        capability=capability,
    )
    launch = replace(
        protocol_launch(tmp_path, "open('marker','w').write('executed')"),
        executable=identity,
    )

    async def started(process_identity):
        capability.revision = "changed"

    if phase == "before-spawn":
        capability.revision = "changed"
    with pytest.raises(ProfileError, match=r"^configuration_drift$"):
        asyncio.run(
            run_protocol(launch, on_started=started if phase == "after-spawn" else None)
        )
    assert (tmp_path / "marker").exists() == (phase == "after-spawn")


@pytest.mark.parametrize("kind", ["unbound", "bound", "provisioning"])
def test_immutable_but_unbound_shebang_interpreter_is_rejected(
    tmp_path: Path, monkeypatch, kind: str
) -> None:
    target, python, binding, capability, tree = capability_fixture(
        tmp_path, monkeypatch
    )
    other = tmp_path / "other-python"
    other.write_bytes(python.read_bytes())
    other.chmod(0o700)
    if kind != "unbound":
        other = python
    candidate, scratch = tmp_path / "candidate", tmp_path / "scratch"
    observed = target.admit_executable(
        other,
        hashlib.sha256(other.read_bytes()).hexdigest(),
        candidate,
        scratch,
        live=False,
    )
    script = tmp_path / "script"
    script.write_text("#!" + str(other) + "\npass\n")
    script.chmod(0o700)
    wire = binding.wire()
    for tool_binding in wire["tools"]:
        tool_binding["absolute_path"] = str(script)
        tool_binding["sha256"] = hashlib.sha256(script.read_bytes()).hexdigest()
    binding = type(binding).from_wire(wire)
    if kind == "provisioning":
        tree.write_bytes(b"interpreter tree changed")
    from orchestra.security.profile import ProfileError

    def admit():
        return target.admit_executable(
            script,
            hashlib.sha256(script.read_bytes()).hexdigest(),
            candidate,
            scratch,
            runtime=binding,
            capability=capability,
            interpreters=(observed,),
        )

    if kind == "bound":
        identity = admit()
        target.verify_identity(identity)
        assert identity.interpreters[0].path == python
    else:
        with pytest.raises(ProfileError, match=r"^configuration_drift$"):
            admit()


def capability_fixture(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    import orchestra.security.process as target
    from orchestra.security.profile import CATALOG
    from orchestra.security.request import RuntimeBindings

    python = private_python(tmp_path)
    git_path = Path("/usr/bin/git").resolve()
    artifact = tmp_path / "artifact"
    artifact.mkdir(mode=0o700)
    tree = tmp_path / "stdlib.py"
    tree.write_bytes(b"synthetic full runtime tree")
    provision = hashlib.sha256(tree.read_bytes()).hexdigest()
    from orchestra.security.profile import canonical

    artifact_bytes = canonical(
        {
            "format": "orchestra.producer-artifact/v1",
            "revision": "a" * 40,
            "files": [],
        }
    )
    (artifact / "producer-manifest.json").write_bytes(artifact_bytes)
    artifact_digest = hashlib.sha256(artifact_bytes).hexdigest()
    bindings = RuntimeBindings.from_wire(
        {
            "python": {"absolute_path": str(python), "provisioning_digest": provision},
            "producer": {
                "absolute_root": str(artifact),
                "revision": "a" * 40,
                "manifest_digest": artifact_digest,
            },
            "git": {
                "absolute_path": str(git_path),
                "sha256": hashlib.sha256(git_path.read_bytes()).hexdigest(),
                "provisioning_digest": provision,
            },
            "tools": [
                {
                    "adapter_id": name,
                    "absolute_path": str(python),
                    "sha256": hashlib.sha256(python.read_bytes()).hexdigest(),
                    "provisioning_digest": provision,
                }
                for name in sorted(CATALOG)
                if name != "portable-patterns-v1"
            ],
            "scratch_root": str(tmp_path / "scratch"),
            "runner_capability_revision": "synthetic-fixture-only",
            "capability_digest": "f" * 64,
            "registry_capability_digest": None,
        }
    )
    capability = SimpleNamespace(
        revision="synthetic-fixture-only",
        digest="f" * 64,
        candidate_can_write=lambda path: False,
        assert_immutable=lambda path: None,
        provisioning_digest=lambda path: artifact_digest
        if path == artifact
        else hashlib.sha256(tree.read_bytes()).hexdigest(),
    )
    # A unit seam avoids asserting that /tmp ancestors are production immutable.
    runtime_module = sys.modules[target.admit_executable.__module__]
    monkeypatch.setattr(runtime_module, "_chain", lambda path: (path,))
    return target, python, bindings, capability, tree


@pytest.mark.parametrize(
    "mutation",
    [
        "revision",
        "capability-digest",
        "provisioning",
        "producer",
        "producer-revision",
        "tool-sha",
        "unbound-path",
        "missing-runtime",
        "provider-error",
        "provider-unknown-write",
        "provider-false-immutable",
    ],
)
def test_live_authority_requires_exact_retained_runtime(
    tmp_path: Path, monkeypatch, mutation: str
) -> None:
    target, path, binding, capability, tree = capability_fixture(tmp_path, monkeypatch)
    wire = binding.wire()
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if mutation == "revision":
        capability.revision = "different"
    elif mutation == "capability-digest":
        capability.digest = "0" * 64
    elif mutation == "provisioning":
        tree.write_bytes(b"different interpreter tree")
    elif mutation == "producer":
        wire["producer"]["manifest_digest"] = "0" * 64
    elif mutation == "producer-revision":
        wire["producer"]["revision"] = "0" * 40
    elif mutation == "tool-sha":
        for tool_binding in wire["tools"]:
            tool_binding["sha256"] = "0" * 64
    elif mutation == "unbound-path":
        path = tmp_path / "unbound"
        path.write_bytes(b"\x7fELF synthetic never executed")
        path.chmod(0o700)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
    elif mutation == "provider-error":

        def broken(path):
            raise RuntimeError("synthetic-secret-provider")

        capability.provisioning_digest = broken
    elif mutation == "provider-unknown-write":
        capability.candidate_can_write = lambda path: None
    elif mutation == "provider-false-immutable":
        capability.assert_immutable = lambda path: False
    binding = type(binding).from_wire(wire)
    from orchestra.security.profile import ProfileError

    with pytest.raises(ProfileError, match=r"^configuration_drift$"):
        target.admit_executable(
            path,
            sha,
            tmp_path / "candidate",
            tmp_path / "scratch",
            runtime=None if mutation == "missing-runtime" else binding,
            capability=capability,
        )


def test_live_binding_is_retained_and_rechecked_without_new_authority(
    tmp_path: Path, monkeypatch
) -> None:
    target, path, binding, capability, tree = capability_fixture(tmp_path, monkeypatch)
    identity = target.admit_executable(
        path,
        hashlib.sha256(path.read_bytes()).hexdigest(),
        tmp_path / "candidate",
        tmp_path / "scratch",
        runtime=binding,
        capability=capability,
    )
    target.verify_identity(identity)
    assert str(tmp_path) not in repr(identity) and "synthetic" not in repr(identity)
    tree.write_bytes(b"different tool/interpreter provisioning")
    from orchestra.security.profile import ProfileError

    with pytest.raises(ProfileError, match=r"^configuration_drift$"):
        target.verify_identity(identity)


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


@pytest.mark.parametrize("kind", ["exact", "excess", "symlink", "fifo"])
def test_native_report_file_has_independent_no_follow_bound(
    tmp_path: Path, kind: str
) -> None:
    from orchestra.security.profile import ProfileError

    tmp_path.chmod(0o700)
    report = tmp_path / "report.json"
    if kind == "fifo":
        os.mkfifo(report)
    elif kind == "symlink":
        target = tmp_path / "target"
        target.write_bytes(b"{}")
        report.symlink_to(target)
    else:
        report.write_bytes(b"x" * (65536 + (kind == "excess")))
    if kind == "exact":
        observed = read_native_file(tmp_path, "report.json")
        assert observed.byte_count == 65536
        assert observed.digest == hashlib.sha256(b"x" * 65536).hexdigest()
        assert "xxxx" not in repr(observed)
    else:
        with pytest.raises(ProfileError):
            read_native_file(tmp_path, "report.json")


def protocol_launch(
    tmp_path: Path,
    code: str,
    *,
    data: bytes = b"",
    cap: int = 65536,
    deadline: float = 2.0,
) -> ProtocolLaunch:
    python = private_python(tmp_path)
    binding = admit_executable(
        python,
        hashlib.sha256(python.read_bytes()).hexdigest(),
        tmp_path / "candidate",
        tmp_path / "uncreated",
        live=False,
    )
    env = security_environment(
        tmp_path, tmp_path / "private", (python.parent,), "fixture"
    )
    return ProtocolLaunch(
        executable=binding,
        argv=(str(python), "-I", "-B", "-c", code),
        cwd=tmp_path,
        environment=tuple(sorted(env.items())),
        stdin=data,
        stdin_limit=2097152,
        stdout_limit=cap,
        stderr_limit=cap,
        deadline_seconds=deadline,
    )


@pytest.mark.parametrize("cap", [4096, 65536])
@pytest.mark.parametrize("stream", [1, 2])
@pytest.mark.parametrize("extra", [0, 1])
def test_raw_protocol_exact_cap_and_first_excess(
    tmp_path: Path, stream: int, extra: int, cap: int
) -> None:
    launch = protocol_launch(
        tmp_path, f"import os;os.write({stream},b'x'*{cap + extra})", cap=cap
    )
    outcome = asyncio.run(run_protocol(launch))
    assert outcome.reaped and outcome.stdin_complete
    assert getattr(
        outcome, "stdout_truncated" if stream == 1 else "stderr_truncated"
    ) == bool(extra)
    assert len(outcome.stdout_bytes) <= cap and len(outcome.stderr_bytes) <= cap
    assert (
        getattr(outcome, "stdout_total" if stream == 1 else "stderr_total")
        == cap + extra
    )
    if not extra:
        assert outcome.exit_code == 0 and not outcome.io_error and not outcome.timed_out
        assert (
            getattr(outcome, "stdout_digest" if stream == 1 else "stderr_digest")
            == hashlib.sha256(b"x" * cap).hexdigest()
        )


def test_raw_protocol_preserves_bytes_and_hashes_without_redaction(
    tmp_path: Path,
) -> None:
    data = b'{"api_key":"synthetic-canary","bytes":"\xff"}'
    code = (
        'import os;os.write(1,b\'{\\"api_key\\":\\"synthetic-\');'
        'os.write(1,b\'canary\\",\\"bytes\\":\\"\\xff\\"}\')'
    )
    outcome = asyncio.run(run_protocol(protocol_launch(tmp_path, code)))
    assert outcome.stdout_bytes == data
    assert outcome.stdout_digest == hashlib.sha256(data).hexdigest()
    assert "synthetic-canary" not in repr(outcome)
    assert str(tmp_path) not in repr(outcome)
    assert "synthetic-canary" not in repr(outcome)


def test_raw_protocol_stdin_overflow_rejects_before_child_exists(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    marker = tmp_path / "must-not-exist"
    launch = protocol_launch(tmp_path, "open('must-not-exist','w').write('executed')")
    launch = replace(launch, stdin=b"x" * 2097153)
    with pytest.raises(ValueError, match="invalid_protocol_launch"):
        asyncio.run(run_protocol(launch))
    assert not marker.exists()
    assert str(tmp_path) not in repr(launch) and "must-not-exist" not in repr(launch)


def test_raw_protocol_concurrent_complete_stdin_and_broken_pipe(tmp_path: Path) -> None:
    data = b"x" * 1048576
    launch = protocol_launch(
        tmp_path, "import sys;data=sys.stdin.buffer.read();print(len(data))", data=data
    )
    outcome = asyncio.run(run_protocol(launch))
    assert (
        outcome.stdin_complete
        and not outcome.io_error
        and outcome.stdout_bytes.strip() == b"1048576"
    )
    other = tmp_path / "other"
    other.mkdir()
    broken = protocol_launch(other, "import os;os.close(0);print('{}')", data=data)
    outcome = asyncio.run(run_protocol(broken))
    assert outcome.io_error and not outcome.stdin_complete and outcome.reaped


def test_raw_protocol_timeout_and_cancellation_cleanup(tmp_path: Path) -> None:
    launch = protocol_launch(tmp_path, "import time;time.sleep(30)", deadline=0.05)
    outcome = asyncio.run(run_protocol(launch))
    assert outcome.timed_out and outcome.reaped
    assert not pid_alive(outcome.process_identity.pid)
    observed = []

    async def exercise() -> None:
        async def started(identity) -> None:
            observed.append(identity)

        task = asyncio.create_task(run_protocol(launch, on_started=started))
        while not observed:
            await asyncio.sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    assert not pid_alive(observed[0].pid)


def test_raw_protocol_inherited_pipe_and_hook_failure_cleanup(tmp_path: Path) -> None:
    code = "import os,time;pid=os.fork();time.sleep(30) if pid==0 else os._exit(0)"
    outcome = asyncio.run(run_protocol(protocol_launch(tmp_path, code, deadline=0.2)))
    assert outcome.io_error or outcome.timed_out
    assert outcome.reaped
    other = tmp_path / "other"
    other.mkdir()
    identities = []

    async def started(identity) -> None:
        identities.append(identity)
        raise ValueError("synthetic-secret-must-not-be-exposed")

    with pytest.raises(ValueError, match="protocol_hook_failed"):
        asyncio.run(
            run_protocol(
                protocol_launch(other, "import time;time.sleep(30)"), on_started=started
            )
        )
    assert not pid_alive(identities[0].pid)
