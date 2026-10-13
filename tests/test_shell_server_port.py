"""A sandboxed command with the network on is kept off the server it runs under. The server's
API asks for no login, so one request to it would undo the sandbox: a saved
`shell_write_paths`, a stopped browser. The server names its own port as it starts, and every
sandbox profile written after that closes the port on every address."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from my_agent_crew import __main__ as entry
from my_agent_crew.tools.shell_sandbox import close_port, sandbox_profile, server_rules
from tests.test_shell_network_sandbox import listen, needs_sandbox, python, run

RULE = '(deny network-outbound (remote tcp "*:{port}"))'
# Every way a command on this machine spells the address of a server on loopback.
HOSTS = ("127.0.0.1", "::1", "localhost")


def reach(host: str, port: int) -> str:
    """A command that exits 0 only if it reached the listener at `host` and `port`."""
    return python(
        f"import socket; socket.create_connection(('{host}', {port}), timeout=3); print('reached')"
    )


async def on_both_loopbacks() -> tuple[list[asyncio.Server], int]:
    """A listener on one port of 127.0.0.1 and of ::1, as a server on `localhost` has."""
    first = await listen()
    port = first.sockets[0].getsockname()[1]
    second = await asyncio.start_server(lambda r, w: w.close(), "::1", port)
    return [first, second], port


def test_a_profile_closes_no_port_until_the_server_names_its_own():
    online = sandbox_profile([Path("/w/data")], network=True)
    offline = sandbox_profile([Path("/w/data")])
    assert server_rules() == "" and "network-outbound" not in online

    close_port(8765)

    # Last in the profile, where no later rule opens it again, and on every address.
    assert sandbox_profile([Path("/w/data")], network=True) == online + RULE.format(port=8765)
    assert sandbox_profile([Path("/w/data")]) == offline + RULE.format(port=8765)


def test_a_port_named_twice_is_closed_once_beside_any_other():
    # Two numbers a set hands back the larger first: the profile is the same text each time.
    for port in (8769, 8762, 8769):
        close_port(port)

    assert server_rules() == RULE.format(port=8762) + RULE.format(port=8769)


@needs_sandbox
async def test_a_sandboxed_command_with_the_network_does_not_reach_the_server(tmp_path: Path):
    workspace = tmp_path / "coach"
    (workspace / "data").mkdir(parents=True)
    kwargs = {"write_paths": [workspace / "data"]}
    servers, port = await on_both_loopbacks()
    other = await listen()
    elsewhere = other.sockets[0].getsockname()[1]
    try:
        before = [await run(workspace, reach(host, port), **kwargs) for host in HOSTS]
        close_port(port)
        after = [await run(workspace, reach(host, port), **kwargs) for host in HOSTS]
        beside = await run(workspace, reach("127.0.0.1", elsewhere), **kwargs)
    finally:
        for server in (*servers, other):
            server.close()
            await server.wait_closed()

    assert [r.ok and "reached" in r.output for r in before] == [True, True, True]
    # The sandbox's refusal, not a closed port's: that would be ConnectionRefusedError.
    assert [r.ok is False and "PermissionError" in r.output for r in after] == [True, True, True]
    # The rest of the network is the command's as before.
    assert beside.ok and "reached" in beside.output


@pytest.mark.parametrize(("flags", "port"), [((), 8765), (("--port", "8798"), 8798)])
def test_a_server_closes_its_own_port_before_it_builds_its_crew(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, flags: tuple[str, ...], port: int
):
    seen: dict[str, str] = {}
    monkeypatch.setenv("MY_AGENT_HOME", str(tmp_path))

    def build_runtime(settings: object) -> object:
        # A sandboxed shell is given its profile as the crew is built.
        seen["rules"] = server_rules()
        return SimpleNamespace(agents={})

    monkeypatch.setattr(entry, "build_runtime", build_runtime)
    monkeypatch.setattr(entry, "create_app", lambda runtime, schedule=True: object())
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, **kwargs: None)
    monkeypatch.setattr(sys, "argv", ["my-agent-crew", *flags])

    assert entry.main() == 0
    assert seen["rules"] == RULE.format(port=port)
