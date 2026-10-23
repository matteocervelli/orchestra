import asyncio
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from orchestra.security.process import admit_executable, run_protocol


def private_python(tmp_path: Path) -> Path:
    """Copy the launcher only; borrow the existing stdlib for synthetic tests."""
    root = tmp_path / "python-runtime"
    python = root / "bin/python"
    if not python.exists():
        root.mkdir(mode=0o700)
        python.parent.mkdir(mode=0o700)
        shutil.copyfile(Path(sys.executable).resolve(), python)
        python.chmod(0o700)
        (root / "pyvenv.cfg").write_text(
            f"home = {Path(sys.base_prefix) / 'bin'}\n"
            "include-system-site-packages = false\n"
        )
    return python


@pytest.mark.parametrize("no_site", [True, False])
def test_private_runtime_executes_with_writable_host_input(
    tmp_path: Path, monkeypatch, no_site: bool
) -> None:
    from dataclasses import replace

    from test_process import capability_fixture, protocol_launch

    source = Path(sys.executable).resolve()
    before = source.stat()
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    host = tmp_path / "writable-host-python"
    shutil.copyfile(source, host)
    host.chmod(0o770)
    monkeypatch.setattr(sys, "executable", str(host))
    target, python, bindings, capability, _ = capability_fixture(tmp_path, monkeypatch)
    identity = target.admit_executable(
        python,
        source_digest,
        tmp_path / "candidate",
        tmp_path / "scratch",
        runtime=bindings,
        capability=capability,
    )
    assert python != host and python.is_relative_to(tmp_path / "python-runtime")
    assert python.stat().st_ino != host.stat().st_ino
    assert python.stat().st_mode & 0o022 == 0
    code = (
        "import hashlib,json,os,ssl,sys,zlib;print(json.dumps({"
        "'isolated':sys.flags.isolated,'no_site':sys.flags.no_site,"
        "'no_bytecode':sys.dont_write_bytecode,'version':list(sys.version_info[:3]),"
        "'hash':hashlib.sha256(b'fixture').hexdigest(),"
        "'data':zlib.decompress(zlib.compress(b'fixture')).decode(),"
        "'ssl':bool(ssl.OPENSSL_VERSION)}))"
    )
    flags = ("-I", "-S", "-B") if no_site else ("-I", "-B")
    launch = replace(
        protocol_launch(tmp_path, code),
        executable=identity,
        argv=(str(python), *flags, "-c", code),
    )
    observed = asyncio.run(run_protocol(launch))
    assert observed.exit_code == 0 and not observed.io_error and observed.reaped
    assert json.loads(observed.stdout_bytes) == {
        "isolated": 1,
        "no_site": int(no_site),
        "no_bytecode": True,
        "version": list(sys.version_info[:3]),
        "hash": hashlib.sha256(b"fixture").hexdigest(),
        "data": "fixture",
        "ssl": True,
    }
    after = source.stat()
    assert (after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns) == (
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
    )
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_digest


@pytest.mark.parametrize("mode", [0o770, 0o707])
def test_group_or_world_writable_executable_is_rejected(
    tmp_path: Path, mode: int
) -> None:
    from orchestra.security.profile import ProfileError

    path = tmp_path / "writable-python"
    shutil.copyfile(Path(sys.executable).resolve(), path)
    path.chmod(mode)
    with pytest.raises(ProfileError, match=r"^configuration_drift$"):
        admit_executable(
            path,
            hashlib.sha256(path.read_bytes()).hexdigest(),
            tmp_path / "candidate",
            tmp_path / "scratch",
            live=False,
        )
