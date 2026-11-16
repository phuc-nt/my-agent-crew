"""A job's row is right on a page that is open while the job fails.

The page reads the job list when a run ends. The failures in a row a job is in are counted
after that, so a row read at the run's end may lack the failure that run added, or still
show a count the run closed. Once the run's count is settled and differs from before, the
stream tells every page to read the list again (`{"type": "jobs"}`), and says nothing when
the count stayed as it was.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.scheduler import Scheduler, jobs
from my_agent_crew.store.runs import DONE, FAILED
from tests.test_job_failure_streaks import EVERY_FIVE, Clock, Shell, stamps
from tests.test_scheduler import with_schedules

MARK = {"id": "read-up-to-here"}


@pytest.fixture
def shell(monkeypatch) -> Shell:
    shell = Shell()
    monkeypatch.setattr(jobs, "run_shell", shell)
    return shell


class Page:
    """A page open on the job list: the stream it watches, and the row it would read."""

    def __init__(self, deps: Any):
        with_schedules(deps, EVERY_FIVE)
        self.clock, self.hub = Clock(), ActivityHub(deps.store)
        self.sched = Scheduler({"default": deps}, self.hub, clock=self.clock)
        self._stream: AsyncIterator[dict[str, Any]] = self.hub.subscribe()

    async def opens(self) -> Page:
        assert (await anext(self._stream))["type"] == "snapshot"
        return self

    async def payloads(self) -> list[dict[str, Any]]:
        """What the stream carried since the page last looked, in order. Read up to a mark
        published now, so nothing is waited for."""
        self.hub.publish_conversation(MARK)
        carried: list[dict[str, Any]] = []
        while (payload := await anext(self._stream)).get("conversation") != MARK:
            carried.append(payload)
        return carried

    async def sent(self) -> list[str]:
        """The same in short: a run by how it stands, anything else by its type."""
        return [
            p["run"]["status"] if p["type"] == "run" else p["type"] for p in await self.payloads()
        ]

    def row(self) -> dict[str, Any] | None:
        [row] = self.sched.describe()
        return row["failing"]

    async def tick(self) -> None:
        self.clock.after(minutes=5)
        await self.sched.tick()


async def test_a_failure_counted_after_the_run_ended_asks_the_page_to_read_again(
    deps_factory, shell
):
    page = await Page(deps_factory()).opens()

    await page.tick()

    assert (await page.sent())[-2:] == [FAILED, "jobs"]
    assert page.row() == stamps("07:05")


async def test_the_page_is_asked_to_read_again_as_just_that_and_nothing_more(deps_factory, shell):
    page = await Page(deps_factory()).opens()
    await page.tick()

    payloads = await page.payloads()

    assert payloads[-1] == {"type": "jobs"}
    assert [p["type"] for p in payloads].count("jobs") == 1


async def test_each_failure_more_in_the_row_is_read_again_for_its_count(deps_factory, shell):
    page = await Page(deps_factory()).opens()
    await page.tick()
    await page.sent()

    await page.tick()

    assert (await page.sent())[-2:] == [FAILED, "jobs"]
    assert page.row() == stamps("07:05", count=2)


async def test_a_job_that_mended_is_read_again_and_one_that_never_failed_is_not(
    deps_factory, shell
):
    page = await Page(deps_factory()).opens()
    await page.tick()
    await page.sent()

    shell.mends()
    await page.tick()
    assert (await page.sent())[-2:] == [DONE, "jobs"]
    assert page.row() is None

    # Nothing was counted and nothing closed: the read at the run's end was already right.
    await page.tick()
    sent = await page.sent()
    assert sent[-1] == DONE and "jobs" not in sent
