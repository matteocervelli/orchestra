"""Bounded native byte protocol; no diagnostics redaction or scanner policy."""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import selectors
import signal
import subprocess
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic

from orchestra.security.profile import (
    ProfileError,
    read_regular,
    require,
    validate_security_environment,
)
from orchestra.security.runtime import (
    FileIdentity as FileIdentity,
)
from orchestra.security.runtime import (
    RuntimeCapability as RuntimeCapability,
)
from orchestra.security.runtime import (
    admit_executable as admit_executable,
)
from orchestra.security.runtime import (
    observe_executable as observe_executable,
)
from orchestra.security.runtime import (
    verify_identity as verify_identity,
)

_KILL_WAIT_S = 0.2


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    process_group_id: int
    start_identity: str


def _killpg(pgid: int, sig: signal.Signals) -> bool:
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        return False
    return True


def _terminate(process: subprocess.Popen[bytes]) -> bool:
    # The session leader's pid remains the group id even after the leader is reaped;
    # leader is reaped, so members that ignore SIGTERM are still killed below.
    pgid = process.pid
    if _killpg(pgid, signal.SIGTERM):
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=_KILL_WAIT_S)
    _killpg(pgid, signal.SIGKILL)
    try:
        process.wait(timeout=_KILL_WAIT_S)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return process.returncode is not None


def _process_start_identity(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
        closing = raw.rfind(")")
        fields = raw[closing + 2 :].split()
        return f"linux-proc:{pid}:{fields[19]}"
    except (OSError, IndexError):
        return f"pid:{pid}"


@dataclass(frozen=True)
class ProtocolLaunch:
    executable: FileIdentity = field(repr=False)
    argv: tuple[str, ...] = field(repr=False)
    cwd: Path = field(repr=False)
    environment: tuple[tuple[str, str], ...] = field(repr=False)
    stdin: bytes = field(repr=False)
    stdin_limit: int
    stdout_limit: int
    stderr_limit: int
    deadline_seconds: float


@dataclass(frozen=True)
class ProtocolObservation:
    exit_code: int | None
    timed_out: bool
    cancelled: bool
    io_error: bool
    wall_ms: int
    process_identity: ProcessIdentity
    stdout_bytes: bytes = field(repr=False)
    stderr_bytes: bytes = field(repr=False)
    stdout_total: int
    stderr_total: int
    stdout_truncated: bool
    stderr_truncated: bool
    stdout_digest: str
    stderr_digest: str
    stdin_complete: bool
    reaped: bool


def _protocol_limits(launch: ProtocolLaunch) -> None:
    if (
        type(launch.stdin) is not bytes
        or type(launch.stdin_limit) is not int
        or not 0 < launch.stdin_limit <= 2097152
        or len(launch.stdin) > launch.stdin_limit
        or any(
            type(cap) is not int or not 0 < cap <= 65536
            for cap in (launch.stdout_limit, launch.stderr_limit)
        )
    ):
        raise ValueError("invalid_protocol_launch")


def _protocol_command(launch: ProtocolLaunch) -> None:
    if (
        not launch.argv
        or launch.argv[0] != str(launch.executable.path)
        or any(type(arg) is not str or "\0" in arg for arg in launch.argv)
        or not launch.cwd.is_absolute()
    ):
        raise ValueError("invalid_protocol_launch")


def _protocol_validate(launch: ProtocolLaunch) -> dict[str, str]:
    _protocol_limits(launch)
    if (
        type(launch.deadline_seconds) not in (int, float)
        or not math.isfinite(launch.deadline_seconds)
        or not 0 < launch.deadline_seconds <= 3600
    ):
        raise ValueError("invalid_protocol_launch")
    _protocol_command(launch)
    environment = dict(launch.environment)
    if len(environment) != len(launch.environment):
        raise ValueError("invalid_protocol_launch")
    validate_security_environment(environment)
    verify_identity(launch.executable)
    return environment


class _ProtocolIO:
    def __init__(
        self, process: subprocess.Popen[bytes], launch: ProtocolLaunch
    ) -> None:
        self.process, self.launch = process, launch
        self.buffers = [bytearray(), bytearray()]
        self.hashes = [hashlib.sha256(), hashlib.sha256()]
        self.counts = [0, 0]
        self.overflow = [False, False]
        self.written = 0
        self.error = False
        self.exited = False
        self.selector = selectors.DefaultSelector()
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise ValueError("protocol_io_failed")
        for index, stream in enumerate((process.stdout, process.stderr, process.stdin)):
            os.set_blocking(stream.fileno(), False)
            if index != 2 or launch.stdin:
                self.selector.register(
                    stream,
                    selectors.EVENT_WRITE if index == 2 else selectors.EVENT_READ,
                    index,
                )
            else:
                stream.close()

    def step(self) -> None:
        for key, _ in self.selector.select(0):
            try:
                if key.data == 2:
                    self.written += os.write(
                        key.fd, self.launch.stdin[self.written : self.written + 8192]
                    )
                    if self.written == len(self.launch.stdin):
                        self.selector.unregister(key.fileobj)
                        if self.process.stdin is None:
                            raise ValueError("protocol_io_failed")
                        self.process.stdin.close()
                else:
                    self.read(key)
            except (OSError, ValueError):
                self.error = True
        if not self.exited and self.process.poll() is not None:
            self.exited = True
            # A live group after leader exit is a descendant, not successful completion.
            if _killpg(self.process.pid, signal.SIGTERM):
                self.error = True
            self.error |= not _terminate(self.process)

    def read(self, key: selectors.SelectorKey) -> None:
        data = os.read(key.fd, 8192)
        if not data:
            self.selector.unregister(key.fileobj)
            return
        index = key.data
        self.counts[index] += len(data)
        self.hashes[index].update(data)
        cap = (self.launch.stdout_limit, self.launch.stderr_limit)[index]
        self.buffers[index].extend(data[: max(0, cap - len(self.buffers[index]))])
        self.overflow[index] |= self.counts[index] > cap


def _protocol_start(
    launch: ProtocolLaunch, environment: dict[str, str]
) -> tuple[subprocess.Popen[bytes], ProcessIdentity, _ProtocolIO]:
    try:
        process = subprocess.Popen(  # noqa: S603, RUF100 - admitted identity and argv
            launch.argv,
            cwd=launch.cwd,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError:
        raise ValueError("protocol_spawn_failed") from None
    identity = ProcessIdentity(
        process.pid, process.pid, _process_start_identity(process.pid)
    )
    try:
        state = _ProtocolIO(process, launch)
    except OSError:
        _terminate(process)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        raise ValueError("protocol_io_failed") from None
    return process, identity, state


def _protocol_observation(
    launch: ProtocolLaunch,
    state: _ProtocolIO,
    identity: ProcessIdentity,
    timed_out: bool,
    start: float,
) -> ProtocolObservation:
    process = state.process
    return ProtocolObservation(
        exit_code=None if timed_out else process.returncode,
        timed_out=timed_out,
        cancelled=False,
        io_error=state.error
        or state.written != len(launch.stdin)
        or process.returncode is None,
        wall_ms=int((monotonic() - start) * 1000),
        process_identity=identity,
        stdout_bytes=bytes(state.buffers[0]),
        stderr_bytes=bytes(state.buffers[1]),
        stdout_total=state.counts[0],
        stderr_total=state.counts[1],
        stdout_truncated=state.overflow[0],
        stderr_truncated=state.overflow[1],
        stdout_digest=state.hashes[0].hexdigest(),
        stderr_digest=state.hashes[1].hexdigest(),
        stdin_complete=state.written == len(launch.stdin),
        reaped=process.returncode is not None,
    )


async def _protocol_pump(
    state: _ProtocolIO, on_heartbeat: Callable[[], Awaitable[None]] | None
) -> None:
    next_heartbeat = monotonic() + 30
    while state.selector.get_map() or state.process.poll() is None:
        state.step()
        if state.error or any(state.overflow):
            break
        if on_heartbeat is not None and monotonic() >= next_heartbeat:
            await on_heartbeat()
            next_heartbeat = monotonic() + 30
        await asyncio.sleep(0.001)


async def run_protocol(
    launch: ProtocolLaunch,
    *,
    on_started: Callable[[ProcessIdentity], Awaitable[None]] | None = None,
    on_heartbeat: Callable[[], Awaitable[None]] | None = None,
) -> ProtocolObservation:
    environment = _protocol_validate(launch)
    start = monotonic()
    process, identity, state = _protocol_start(launch, environment)
    timed_out = False
    try:
        async with asyncio.timeout(
            max(0, launch.deadline_seconds - (monotonic() - start))
        ):
            if on_started is not None:
                await on_started(identity)
            await _protocol_pump(state, on_heartbeat)
    except TimeoutError:
        timed_out = True
    except asyncio.CancelledError:
        raise
    except Exception:
        raise ValueError("protocol_hook_failed") from None
    finally:
        state.error |= not _terminate(process)
        state.error |= bool(state.selector.get_map())
        state.selector.close()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        verify_identity(launch.executable)
    return _protocol_observation(launch, state, identity, timed_out, start)


class NativeRunner:
    """Local supervision only; live capability admission is a separate prerequisite."""

    run = staticmethod(run_protocol)


def _stop(process: subprocess.Popen[bytes]) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        with suppress(ProcessLookupError):
            os.killpg(process.pid, sig)
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=0.2)


def _collect(process: subprocess.Popen[bytes], cap: int) -> bytes:
    if process.stdout is None or process.stderr is None:
        raise ProfileError("native_error")
    streams = (process.stdout, process.stderr)
    buffers = (bytearray(), bytearray())
    deadline = monotonic() + 30
    try:
        with selectors.DefaultSelector() as selector:
            for index, stream in enumerate(streams):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, index)
            while selector.get_map():
                require(monotonic() < deadline, "native_timeout")
                for key, _ in selector.select(0.05):
                    data = os.read(key.fd, 8192)
                    index = key.data
                    if not data:
                        selector.unregister(key.fileobj)
                    else:
                        buffers[index].extend(data)
                        require(
                            len(buffers[index]) <= (cap if index == 0 else 4096),
                            "scope_overflow",
                        )
            require(
                process.wait(timeout=max(0.001, deadline - monotonic())) == 0,
                "scope_drift",
            )
        return bytes(buffers[0])
    finally:
        _stop(process)
        for stream in streams:
            stream.close()


def _git_bytes(
    repo: Path, git: Path, args: tuple[str, ...], cap: int = 2097152
) -> bytes:
    require(git.is_absolute() and not git.is_symlink(), "configuration_drift")
    environment = {
        "PATH": str(git.parent),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_ALLOW_PROTOCOL": "",
    }
    argv = [
        str(git),
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "diff.external=",
        "-c",
        "core.attributesFile=/dev/null",
        *args,
    ]
    try:
        process = subprocess.Popen(  # noqa: S603, RUF100 - fixed trusted git argv
            argv,
            cwd=repo,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        return _collect(process, cap)
    except (OSError, subprocess.TimeoutExpired):
        raise ProfileError("scope_drift") from None


def _local_git_state(repo: Path, git: Path) -> None:
    # Git 2.43 has no reliable no-lazy-fetch switch: deny every transport even
    # before inspecting config names, then reject partial/alternate object stores.
    names = (
        _git_bytes(
            repo,
            git,
            ("config", "--no-includes", "--local", "--null", "--name-only", "--list"),
        )
        .lower()
        .split(b"\0")
    )
    require(
        not any(
            name.startswith((b"include.", b"includeif.", b"filter."))
            or name in {b"extensions.partialclone", b"extensions.worktreeconfig"}
            or name.endswith((b".promisor", b".partialclonefilter"))
            for name in names
        ),
        "coverage_gap",
    )
    common = Path(
        os.fsdecode(
            _git_bytes(
                repo,
                git,
                ("rev-parse", "--path-format=absolute", "--git-common-dir"),
                4096,
            ).strip()
        )
    )
    try:
        require(common.is_absolute() and not common.is_symlink(), "coverage_gap")
        for relative in ("objects", "objects/info", "objects/pack", "info"):
            require(not (common / relative).is_symlink(), "coverage_gap")
        require(
            not any(
                (common / relative).exists()
                for relative in (
                    "objects/info/alternates",
                    "objects/info/http-alternates",
                    "info/grafts",
                    "shallow",
                )
            ),
            "coverage_gap",
        )
        require(not any((common / "objects/pack").glob("*.promisor")), "coverage_gap")
    except OSError:
        raise ProfileError("coverage_gap") from None
    require(
        not _git_bytes(
            repo, git, ("for-each-ref", "--format=%(refname)", "refs/replace/"), 4096
        ).strip(),
        "coverage_gap",
    )


def git_bytes(
    repo: Path, git: Path, args: tuple[str, ...], cap: int = 2097152
) -> bytes:
    _local_git_state(repo, git)
    return _git_bytes(repo, git, args, cap)


@dataclass(frozen=True)
class NativeFile:
    raw: bytes = field(repr=False)
    digest: str
    byte_count: int


def read_native_file(unit_root: Path, relative: str, limit: int = 65536) -> NativeFile:
    require(type(limit) is int and 0 < limit <= 65536, "native_overflow")
    require(
        unit_root.is_absolute()
        and not unit_root.is_symlink()
        and unit_root.stat().st_mode & 0o077 == 0,
        "configuration_drift",
    )
    raw = read_regular(unit_root, relative, limit)
    return NativeFile(
        raw=raw, digest=hashlib.sha256(raw).hexdigest(), byte_count=len(raw)
    )
