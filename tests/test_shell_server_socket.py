"""A server on a Unix socket (`--uds`) closes the socket's folder, not a port, to every
sandboxed command: the folder is reached by its path, so it is closed where a port cannot be
alone, and a command keeps the network on under bwrap too. The server's own process is made
undumpable on Linux, so a command reads neither its environment nor its memory."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from my_agent_crew import __main__ as entry
from my_agent_crew.tools import own_process, shell_bwrap
from my_agent_crew.tools.own_process import PR_SET_DUMPABLE, close_own_process
from my_agent_crew.tools.shell_bwrap import bwrap_args, sealed_args
from my_agent_crew.tools.shell_sandbox import (
    SANDBOX_EXEC,
    close_socket,
    sandbox_profile,
    served_folders,
    server_rules,
)
from tests.test_shell_bwrap import needs_bwrap
from tests.test_shell_network_sandbox import python, run

needs_a_sandbox = pytest.mark.skipif(
    not SANDBOX_EXEC.is_file() and needs_bwrap.args[0],
    reason="a working sandbox-exec or bwrap only",
)


@pytest.fixture
def short_dir() -> Iterator[Path]:
    """A socket path is short on macOS (104 bytes), shorter than a test's own folder."""
    made = Path(tempfile.mkdtemp(prefix="uds", dir="/tmp")).resolve()
    yield made
    shutil.rmtree(made, ignore_errors=True)


def reach(socket: Path) -> str:
    """Prints `reached` only once connected; the words of the command do not hold it whole."""
    return python(
        "import socket; s = socket.socket(socket.AF_UNIX);"
        f" s.settimeout(3); s.connect('{socket}'); print('reach' + 'ed')"
    )


def test_a_socket_closes_its_folder_and_no_port(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    close_socket(run_dir / "engine.sock")

    profile = sandbox_profile([tmp_path / "data"], network=True)
    assert served_folders() == (run_dir.resolve(),) and server_rules() == ""
    assert f'(deny file-read* file-write* network-outbound (subpath "{run_dir.resolve()}"))' in (
        profile
    )
    assert "(deny network*)" not in profile


def test_under_bwrap_the_folder_is_covered_with_the_network_on_or_off(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(shell_bwrap, "helper_dirs", lambda: ())
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    close_socket(run_dir / "engine.sock")

    online = bwrap_args([tmp_path / "data"], network=True)
    for args in (online, bwrap_args([tmp_path / "data"]), sealed_args()):
        assert args is not None
        covered = [args[i + 1] for i, a in enumerate(args) if a == "--tmpfs"]
        assert covered == [str(run_dir.resolve())]
    assert "--unshare-net" not in online


@needs_a_sandbox
async def test_a_command_with_the_network_does_not_reach_the_servers_socket(
    tmp_path: Path, short_dir: Path
):
    socket = short_dir / "engine.sock"
    server = await asyncio.start_unix_server(lambda r, w: w.close(), str(socket))
    data = tmp_path / "data"
    data.mkdir()
    try:
        before = await run(tmp_path, reach(socket), write_paths=[data])
        close_socket(socket)
        after = await run(tmp_path, reach(socket), write_paths=[data])
        online = await run(tmp_path, python("import socket; print(socket.gethostname())"))
    finally:
        server.close()
        await server.wait_closed()

    assert before.ok and "reached" in before.output
    assert after.ok is False and "reached" not in after.output
    assert online.ok


def test_a_server_on_a_socket_closes_its_folder_before_it_builds_its_crew(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    seen: dict[str, object] = {}
    socket = tmp_path / "run" / "engine.sock"
    monkeypatch.setenv("MY_AGENT_HOME", str(tmp_path / "home"))

    def build_runtime(settings: object) -> object:
        seen["closed"] = (served_folders(), server_rules())
        return SimpleNamespace(agents={})

    monkeypatch.setattr(entry, "build_runtime", build_runtime)
    monkeypatch.setattr(entry, "create_app", lambda runtime, schedule=True: object())
    monkeypatch.setattr(entry, "close_own_process", lambda: seen.setdefault("undumpable", True))
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, **kwargs: seen.update(run=kwargs))
    monkeypatch.setattr(sys, "argv", ["my-agent-crew", "--uds", str(socket)])

    assert entry.main() == 0
    assert seen == {
        "closed": (((tmp_path / "run").resolve(),), ""),
        "undumpable": True,
        "run": {"uds": str(socket), "log_level": "info"},
    }
    assert (socket.parent.stat().st_mode & 0o777) == 0o700


def test_the_process_is_made_undumpable_on_linux_only(monkeypatch):
    calls: list[tuple[int, ...]] = []
    libc = SimpleNamespace(prctl=lambda *args: calls.append(args) or 0)
    monkeypatch.setattr(own_process.sys, "platform", "darwin")
    assert close_own_process(libc) is False and calls == []
    monkeypatch.setattr(own_process.sys, "platform", "linux")
    assert close_own_process(libc) is True and calls == [(PR_SET_DUMPABLE, 0, 0, 0, 0)]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux only")
def test_on_linux_the_process_is_undumpable_after():
    code = (
        "import ctypes; from my_agent_crew.tools.own_process import close_own_process;"
        " libc = ctypes.CDLL(None); before = libc.prctl(3, 0, 0, 0, 0);"
        " print(before, close_own_process(), libc.prctl(3, 0, 0, 0, 0))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.split() == ["1", "True", "0"]
