"""The sweep loop: sweeps at once, repeats on its interval, survives a failed sweep, and
stops when cancelled."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest

from my_agent_crew.server import housekeeping
from my_agent_crew.server.housekeeping import sweep_loop
from my_agent_crew.tools.output_spill import Spill


async def _until(condition, seconds: float = 2.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "condition never became true"
        await asyncio.sleep(0.01)


def _old_file(home: Path) -> Path:
    spill = Spill(home)
    assert spill.write("conv1", "call1", "x" * 10)
    [path] = (home / "spill" / "conv1").iterdir()
    old = time.time() - 30 * 86400
    os.utime(path, (old, old))
    return path


async def test_it_sweeps_straight_away_not_after_the_first_interval(tmp_path: Path):
    path = _old_file(tmp_path)

    task = asyncio.create_task(sweep_loop(tmp_path, interval_seconds=3600))
    await _until(lambda: not path.exists())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_it_sweeps_again_every_interval(tmp_path: Path):
    task = asyncio.create_task(sweep_loop(tmp_path, interval_seconds=0.01))
    await asyncio.sleep(0.05)  # the first sweep has run and the loop is waiting
    path = _old_file(tmp_path)

    await _until(lambda: not path.exists())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_a_failing_sweep_does_not_end_the_loop(tmp_path: Path, monkeypatch):
    calls: list[int] = []

    def flaky(home: Path) -> int:
        calls.append(1)
        if len(calls) == 1:
            raise OSError("disk went away")
        return 0

    monkeypatch.setattr(housekeeping, "sweep", flaky)
    task = asyncio.create_task(sweep_loop(tmp_path, interval_seconds=0.01))

    await _until(lambda: len(calls) >= 3)
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_cancelling_while_waiting_ends_it_promptly(tmp_path: Path):
    task = asyncio.create_task(sweep_loop(tmp_path, interval_seconds=3600))
    await asyncio.sleep(0.05)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)


@pytest.mark.parametrize("scheduled", [True, False])
def test_the_server_sweeps_on_startup_only_when_it_runs_its_background_work(
    deps_factory, scheduled: bool
):
    from fastapi.testclient import TestClient

    from my_agent_crew.config import Route
    from my_agent_crew.server import create_app

    deps = deps_factory(routes=(Route("fake", "echo"),))
    path = _old_file(deps.settings.home)

    with TestClient(create_app(deps, schedule=scheduled), base_url="http://127.0.0.1"):
        time.sleep(0.3)

    assert path.exists() is (not scheduled)
