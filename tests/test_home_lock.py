"""One server at a time on a home (`home_lock.py`).

A server that starts closes the runs the last one left running and carries the cut turns on.
Under a server that is still up, that ends its turns in the record and runs each of them a
second time. So a server holds its home from before it opens what is kept there until its
process is gone, and a start that finds the home held stops there."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from my_agent_crew import __main__ as entry
from my_agent_crew.agents.templates_cli import list_templates
from my_agent_crew.home_lock import HomeHeld, hold

# Another process that holds the home it is named, says so, and stays until it is killed.
# Told to, it first starts a process of its own that keeps every descriptor it is handed.
HOLDER = """
import subprocess, sys
from pathlib import Path
from my_agent_crew.home_lock import hold

hold(Path(sys.argv[1]))
started = ""
if sys.argv[2:] == ["with-child"]:
    nap = "import time; time.sleep(120)"
    started = subprocess.Popen([sys.executable, "-c", nap], close_fds=False).pid
print(f"held {started}", flush=True)
sys.stdin.read()
"""


class Holder:
    def __init__(self, home: Path, *flags: str):
        command = [sys.executable, "-c", HOLDER, str(home), *flags]
        self._proc = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
        )
        assert self._proc.stdout is not None
        said = self._proc.stdout.readline().split()
        assert said[:1] == ["held"], said
        self.child = int(said[1]) if said[1:] else None

    def killed(self) -> None:
        """Gone the hard way, with no chance to let go of anything itself."""
        self._proc.kill()
        self._proc.wait(timeout=10)
        for pipe in (self._proc.stdin, self._proc.stdout):
            assert pipe is not None
            pipe.close()


@pytest.fixture
def holder() -> Iterator[list[Holder]]:
    started: list[Holder] = []
    yield started
    for one in started:
        one.killed()
        if one.child is not None:
            os.kill(one.child, signal.SIGKILL)


def free(home: Path) -> bool:
    """Whether the home could be held right now."""
    try:
        os.close(hold(home))
    except HomeHeld:
        return False
    return True


def test_a_home_another_process_holds_cannot_be_held(tmp_path, holder):
    holder.append(Holder(tmp_path))

    with pytest.raises(HomeHeld, match=tmp_path.name):
        hold(tmp_path)


def test_a_home_is_free_again_once_the_process_that_held_it_is_gone(tmp_path, holder):
    holder.append(Holder(tmp_path))
    assert not free(tmp_path)

    holder[0].killed()

    assert free(tmp_path)


def test_a_process_the_holder_started_does_not_keep_the_home(tmp_path, holder):
    """A command an agent left running outlives the server that started it, and the next
    server still starts."""
    holder.append(Holder(tmp_path, "with-child"))
    assert holder[0].child is not None
    assert not free(tmp_path)

    holder[0].killed()

    os.kill(holder[0].child, 0)  # still there
    assert free(tmp_path)


def test_a_home_is_held_until_what_holds_it_is_closed(tmp_path):
    held = hold(tmp_path)
    assert not free(tmp_path)

    os.close(held)

    assert free(tmp_path)


def test_two_homes_do_not_block_each_other(tmp_path):
    first = hold(tmp_path / "a")
    try:
        assert free(tmp_path / "b")
    finally:
        os.close(first)


def test_a_home_reached_by_another_path_is_the_same_home(tmp_path):
    (tmp_path / "home").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "home", target_is_directory=True)
    held = hold(tmp_path / "home")
    try:
        assert not free(tmp_path / "link")
    finally:
        os.close(held)


def test_a_home_that_is_not_there_yet_is_made_and_held(tmp_path):
    home = tmp_path / "new" / "home"

    held = hold(home)
    try:
        assert home.is_dir()
        assert not free(home)
    finally:
        os.close(held)


def test_a_home_that_cannot_be_locked_for_another_reason_says_so(tmp_path, monkeypatch):
    """Only a home someone holds is called held: what else keeps the lock away is not hidden
    behind that."""

    opened: list[int] = []

    def unsupported(fd: int, how: int) -> None:
        opened.append(fd)
        raise OSError(45, "Operation not supported")

    monkeypatch.setattr("my_agent_crew.home_lock.fcntl.flock", unsupported)

    with pytest.raises(OSError, match="not supported") as refused:
        hold(tmp_path)

    assert not isinstance(refused.value, HomeHeld)
    with pytest.raises(OSError, match="Bad file descriptor"):
        os.fstat(opened[0])  # what it opened to lock is closed again


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch, tmp_path) -> dict[str, object]:
    """What a start got to: whether it built a runtime and served, and whether the home
    was held at each of those."""
    seen: dict[str, object] = {}
    monkeypatch.setenv("MY_AGENT_HOME", str(tmp_path))

    def build_runtime(settings: object) -> object:
        seen["held when built"] = not free(tmp_path)
        return SimpleNamespace(agents={})

    def run(app: object, **kwargs: object) -> None:
        seen["held while serving"] = not free(tmp_path)

    monkeypatch.setattr(entry, "build_runtime", build_runtime)
    monkeypatch.setattr(entry, "create_app", lambda runtime, schedule=True: object())
    monkeypatch.setattr(entry.uvicorn, "run", run)
    return seen


def start(monkeypatch: pytest.MonkeyPatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["my-agent-crew", *args])
    return entry.main()


def test_a_server_holds_its_home_before_it_builds_on_it_and_while_it_serves(
    started, monkeypatch, tmp_path
):
    assert free(tmp_path)

    assert start(monkeypatch) == 0

    assert started == {"held when built": True, "held while serving": True}


@pytest.mark.parametrize("flags", [(), ("--no-schedule",), ("--port", "8798")])
def test_a_server_does_not_start_on_a_home_another_one_holds(
    started, monkeypatch, tmp_path, capsys, flags
):
    """Whatever port it was given, and with its jobs and channels off too: it would close the
    other one's runs all the same."""
    held = hold(tmp_path)
    try:
        assert start(monkeypatch, *flags) == 1
    finally:
        os.close(held)

    assert started == {}  # nothing of the home was read, and nothing was served
    said = capsys.readouterr()
    assert str(tmp_path) in said.err
    assert "MY_AGENT_HOME" in said.err
    assert said.out == ""


def test_a_server_starts_on_its_own_home_while_another_home_is_held(started, monkeypatch, tmp_path):
    other = hold(tmp_path.parent / f"{tmp_path.name}-other")
    try:
        assert start(monkeypatch) == 0
    finally:
        os.close(other)

    assert started == {"held when built": True, "held while serving": True}


def test_an_agent_is_added_to_a_home_a_server_holds(started, monkeypatch, tmp_path, capsys):
    """Adding one writes files a running server picks up at its next start."""
    template = list_templates()[0].id
    held = hold(tmp_path)
    try:
        assert start(monkeypatch, "agent", "list-templates") == 0
        assert start(monkeypatch, "agent", "add", template) == 0
    finally:
        os.close(held)

    assert (tmp_path / "agents" / template).is_dir()
    assert started == {}
    assert capsys.readouterr().err == ""


SERVE = [sys.executable, "-u", "-m", "my_agent_crew", "--port", "0", "--no-schedule"]


def alone_on(home: Path) -> dict[str, str]:
    """An environment that names this home and a model that costs nothing, with none of what
    the machine the test runs on keeps."""
    kept = {name: os.environ[name] for name in ("PATH", "PYTHONPATH") if name in os.environ}
    return {**kept, "HOME": str(home), "MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}


def serving(home: Path) -> subprocess.Popen[str]:
    """A real server on `home`, once it has built on it and said so."""
    server = subprocess.Popen(
        SERVE, env=alone_on(home), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
    )
    assert server.stdout is not None
    said = server.stdout.readline()
    assert f"home={home}" in said, (said, server.poll())
    return server


def gone(server: subprocess.Popen[str]) -> None:
    server.kill()
    server.wait(timeout=30)
    assert server.stdout is not None
    server.stdout.close()


def test_the_command_itself_refuses_a_home_in_use_and_takes_it_once_the_other_is_killed(tmp_path):
    """Nothing stood in for: the command the README gives, run against a server that is up,
    then again after that server was killed with no chance to let go, as a restart does."""
    first = serving(tmp_path)
    try:
        second = subprocess.run(
            SERVE, env=alone_on(tmp_path), capture_output=True, text=True, timeout=60
        )

        assert second.returncode == 1
        assert str(tmp_path) in second.stderr and "MY_AGENT_HOME" in second.stderr
        assert "Traceback" not in second.stderr
        assert second.stdout == ""
        assert first.poll() is None  # the one that was there serves on
    finally:
        gone(first)

    gone(serving(tmp_path))
