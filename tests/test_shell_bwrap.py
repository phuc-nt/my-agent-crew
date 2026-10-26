"""On Linux, where `sandbox-exec` is missing, a confined `shell_run` command and the script
child run under bubblewrap with the same policy: no network, writes only where the profile
says, the private folders closed. Where bwrap cannot hold the policy, the command is refused.

The choice of backend is tested everywhere with a stand-in `bwrap` that records what it was
given; what a real bwrap enforces is tested only where one works (Linux with user namespaces)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from my_agent_crew import texts
from my_agent_crew.script import runner
from my_agent_crew.tools import shell, shell_bwrap
from my_agent_crew.tools.shell_bwrap import BASE, bwrap_args, bwrap_path, sealed_args
from my_agent_crew.tools.shell_sandbox import close_port, temp_dirs
from tests.test_shell_network_sandbox import connect_command, listen, run


def _bwrap_works() -> bool:
    found = bwrap_path()
    if not sys.platform.startswith("linux") or found is None:
        return False
    probe = [str(found), *BASE, "--unshare-net", "true"]
    return subprocess.run(probe, capture_output=True, timeout=10).returncode == 0


needs_bwrap = pytest.mark.skipif(not _bwrap_works(), reason="a working bwrap only")


@pytest.fixture
def stand_in(tmp_path: Path, monkeypatch) -> Path:
    """No sandbox-exec, and a `bwrap` that writes its arguments down and runs the command."""
    log = tmp_path / "bwrap-args.json"
    fake = tmp_path / "bin" / "bwrap"
    fake.parent.mkdir()
    fake.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        f"open({str(log)!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
        "rest = sys.argv[sys.argv.index('/bin/sh'):]\n"
        "os.execv(rest[0], rest)\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    monkeypatch.setattr(shell, "SANDBOX_EXEC", tmp_path / "no-sandbox-exec")
    monkeypatch.setattr(runner, "SANDBOX_EXEC", tmp_path / "no-sandbox-exec")
    monkeypatch.setattr(shell, "bwrap_path", lambda: fake)
    monkeypatch.setattr(runner, "bwrap_path", lambda: fake)
    return log


def test_offline_the_root_is_read_only_and_only_the_write_paths_and_temp_are_mounted():
    args = bwrap_args([Path("/w/data")], cwd=Path("/w"))
    assert args[: len(BASE)] == list(BASE) and "--unshare-net" in args
    binds = [args[i + 1] for i, a in enumerate(args) if a == "--bind-try"]
    assert binds == ["/w/data", *(str(d) for d in temp_dirs())]
    assert args[-2:] == ["--chdir", "/w"]


def test_a_private_folder_is_covered_after_the_writable_mounts(tmp_path: Path):
    kept = tmp_path / "data" / "browser"
    kept.mkdir(parents=True)
    args = bwrap_args([tmp_path / "data"], private=[kept, tmp_path / "not-made-yet"])
    covered = [args[i + 1] for i, a in enumerate(args) if a == "--tmpfs"]
    assert str(kept) in covered and str(tmp_path / "not-made-yet") not in covered
    assert args.index(str(kept)) > args.index(str(tmp_path / "data"))


def test_the_network_on_keeps_the_namespace_unless_the_server_named_its_port():
    """A namespace has the network or none; one port closed is beyond bwrap, so it refuses."""
    online = bwrap_args([Path("/w/data")], network=True)
    assert online is not None and "--unshare-net" not in online
    close_port(8765)
    assert bwrap_args([Path("/w/data")], network=True) is None
    assert bwrap_args([Path("/w/data")]) is not None


def test_the_script_child_is_offline_and_writes_nowhere(monkeypatch):
    monkeypatch.setattr(shell_bwrap, "helper_dirs", lambda: ())
    assert sealed_args() == [*BASE, "--unshare-net"]


def test_sandbox_exec_comes_first_where_both_are(tmp_path: Path, monkeypatch):
    present = tmp_path / "sandbox-exec"
    present.touch()
    monkeypatch.setattr(shell, "SANDBOX_EXEC", present)
    monkeypatch.setattr(shell, "bwrap_path", lambda: Path("/usr/bin/bwrap"))
    found = shell.confinement("(version 1)", [], network=False, private=[], cwd=tmp_path)
    assert found == [str(present), "-p", "(version 1)"]


async def test_without_sandbox_exec_a_confined_command_runs_under_bwrap(tmp_path: Path, stand_in):
    data = tmp_path / "data"
    data.mkdir()
    result = await run(tmp_path, "echo ran", network=False, write_paths=[data])
    assert result.ok and result.output.strip() == "ran"
    given = json.loads(stand_in.read_text(encoding="utf-8"))
    assert "--unshare-net" in given and str(data.resolve()) in given
    assert given[given.index("--chdir") + 1] == str(tmp_path)


async def test_the_network_on_with_the_servers_port_named_is_refused_not_run(
    tmp_path: Path, stand_in
):
    close_port(8765)
    data = tmp_path / "data"
    data.mkdir()
    result = await run(tmp_path, "touch ran.txt", write_paths=[data])
    assert result.ok is False and texts.SHELL_NO_SANDBOX in result.output
    assert not stand_in.exists() and not (tmp_path / "ran.txt").exists()


async def test_with_neither_sandbox_a_confined_command_is_refused(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(shell, "SANDBOX_EXEC", tmp_path / "no-sandbox-exec")
    monkeypatch.setattr(shell, "bwrap_path", lambda: None)
    result = await run(tmp_path, "touch ran.txt", network=False)
    assert result.ok is False and texts.SHELL_NO_SANDBOX in result.output
    assert not (tmp_path / "ran.txt").exists()


def test_the_script_child_runs_under_bwrap_where_sandbox_exec_is_missing(stand_in, monkeypatch):
    first = runner.command()
    assert first[0].endswith("bwrap") and first[1 : 1 + len(BASE)] == list(BASE)
    assert "--unshare-net" in first and "--bind-try" not in first
    monkeypatch.setattr(runner, "bwrap_path", lambda: None)
    assert runner.command()[0] == sys.executable


@needs_bwrap
async def test_under_bwrap_an_offline_command_reaches_no_server(tmp_path: Path):
    server = await listen()
    port = server.sockets[0].getsockname()[1]
    try:
        result = await run(tmp_path, connect_command(port), network=False)
    finally:
        server.close()
        await server.wait_closed()
    assert result.ok is False and "reached" not in result.output


@needs_bwrap
async def test_under_bwrap_a_command_writes_only_where_its_profile_says(tmp_path: Path):
    """Outside the temp directories, where `tmp_path` lies: beside this test file."""
    data = tmp_path / "data"
    data.mkdir()
    beside = Path(__file__).with_name(f"bwrap-wrote-{tmp_path.name}")
    inside = await run(
        tmp_path, f"echo x > {data}/f && cat {data}/f", network=False, write_paths=[data]
    )
    try:
        outside = await run(tmp_path, f"echo x > {beside}", network=False, write_paths=[data])
        assert not beside.exists()
    finally:
        beside.unlink(missing_ok=True)
    assert inside.ok and inside.output.strip() == "x"
    assert outside.ok is False
    assert texts.SHELL_WRITE_DENIED.format(paths=data.resolve()) in outside.output


@needs_bwrap
async def test_under_bwrap_a_private_folder_is_empty(tmp_path: Path):
    kept = tmp_path / "data" / "browser"
    kept.mkdir(parents=True)
    (kept / "Cookies").write_text("secret", encoding="utf-8")
    result = await run(
        tmp_path,
        f"ls -A {kept}; echo end",
        network=False,
        write_paths=[tmp_path / "data"],
        private=[kept],
    )
    assert result.ok and result.output.split() == ["end"]
    assert (kept / "Cookies").read_text(encoding="utf-8") == "secret"
