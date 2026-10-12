"""A job's row is right on a page that is open while the job fails.

The page reads the job list when a run ends. The failures in a row a job is in are counted
after that, and the message about them is sent after that again, a wait of up to a minute.
A row read in between used to say no message had got through, of a message that arrived a
moment later, and went on saying so until some other run ended. So the streak says while a
message is on its way (`telling`), and once the run's count is settled the stream tells every
page to read the list again (`{"type": "jobs"}`).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.scheduler import Scheduler, jobs
from my_agent_crew.scheduler.failure_streaks import RETELL_AFTER, Streak
from my_agent_crew.store.runs import DONE, FAILED
from tests.test_job_failure_streaks import (
    EVERY_FIVE,
    START,
    SYNC,
    WHY,
    Chat,
    Clock,
    Shell,
    counting,
    ended,
    stamps,
)
from tests.test_scheduler import with_schedules

MARK = {"id": "read-up-to-here"}


class Held:
    """A channel that keeps each message until `answer` is given."""

    def __init__(self) -> None:
        self.asked = asyncio.Event()
        self.answer: asyncio.Future[bool] = asyncio.get_running_loop().create_future()

    async def __call__(self, agent_id: str, text: str) -> bool:
        self.asked.set()
        return await self.answer


# --- the streak, while its message is on the way ---


async def test_a_streak_says_its_message_is_on_the_way_until_the_channel_answers():
    held = Held()
    streaks, _, _, job = counting(held)

    settling = asyncio.create_task(streaks.settle(job, ended(FAILED), WHY))
    await held.asked.wait()

    assert streaks.of(SYNC) == Streak(1, START, None, telling=True)
    assert streaks.of(SYNC).to_dict() == {**stamps("07:00"), "telling": True}

    held.answer.set_result(True)
    await settling
    assert streaks.of(SYNC) == Streak(1, START, START)
    assert streaks.of(SYNC).to_dict() == stamps("07:00", "07:00", "13:00")


@pytest.mark.parametrize("answer", [False, RuntimeError("no route to the chat")])
async def test_a_message_that_did_not_get_through_is_no_longer_on_its_way(answer):
    held = Held()
    streaks, _, _, job = counting(held)
    settling = asyncio.create_task(streaks.settle(job, ended(FAILED), WHY))
    await held.asked.wait()

    if isinstance(answer, Exception):
        held.answer.set_exception(answer)
    else:
        held.answer.set_result(answer)
    await settling

    assert streaks.of(SYNC) == Streak(1, START) and streaks.of(SYNC).telling is False


async def test_a_send_cut_short_does_not_leave_the_streak_saying_one_is_under_way():
    """The run was started from the button and the request behind it went away."""
    held = Held()
    streaks, _, _, job = counting(held)
    settling = asyncio.create_task(streaks.settle(job, ended(FAILED), WHY))
    await held.asked.wait()

    settling.cancel()
    with pytest.raises(asyncio.CancelledError):
        await settling

    assert streaks.of(SYNC) == Streak(1, START)


async def test_a_message_sent_again_after_the_wait_keeps_what_was_told_while_it_is_on_the_way():
    held = Held()
    asked: list[str] = []

    async def first_taken_then_held(agent_id: str, text: str) -> bool:
        asked.append(text)
        return len(asked) == 1 or await held(agent_id, text)

    streaks, clock, _, job = counting(first_taken_then_held)
    await streaks.settle(job, ended(FAILED), WHY)
    clock.after(hours=6)

    settling = asyncio.create_task(streaks.settle(job, ended(FAILED), WHY))
    await held.asked.wait()

    assert streaks.of(SYNC) == Streak(2, START, START, telling=True)
    assert streaks.of(SYNC).to_dict() == {
        **stamps("07:00", "07:00", "13:00", count=2),
        "telling": True,
    }
    held.answer.set_result(True)
    await settling
    assert streaks.of(SYNC) == Streak(2, START, START + RETELL_AFTER)


async def test_a_failure_counted_while_a_message_waits_outlives_that_message_not_being_taken():
    """Two runs of one job overlap: the button was pressed while the clock's run was going.
    What the first one's message comes to is written onto the streak as it then stands."""
    held = Held()
    asked: list[str] = []

    async def first_held_then_taken(agent_id: str, text: str) -> bool:
        asked.append(text)
        return await held(agent_id, text) if len(asked) == 1 else True

    streaks, _, _, job = counting(first_held_then_taken)
    first = asyncio.create_task(streaks.settle(job, ended(FAILED), WHY))
    await held.asked.wait()
    await streaks.settle(job, ended(FAILED), WHY)
    assert streaks.of(SYNC) == Streak(2, START, START)

    held.answer.set_result(False)
    await first

    assert streaks.of(SYNC) == Streak(2, START, START)


async def test_a_failure_inside_the_wait_sends_nothing_and_is_never_on_its_way():
    streaks, clock, chat, job = counting()
    await streaks.settle(job, ended(FAILED), WHY)
    clock.after(minutes=5)

    await streaks.settle(job, ended(FAILED), WHY)

    assert len(chat.asked) == 1 and streaks.of(SYNC) == Streak(2, START, START)


# --- what a page watching the stream is sent ---


@pytest.fixture
def shell(monkeypatch) -> Shell:
    shell = Shell()
    monkeypatch.setattr(jobs, "run_shell", shell)
    return shell


class Page:
    """A page open on the job list: the stream it watches, and the row it would read."""

    def __init__(self, deps: Any, notify: Any, clock: Clock):
        with_schedules(deps, EVERY_FIVE)
        self.clock, self.hub = clock, ActivityHub(deps.store)
        self.sched = Scheduler({"default": deps}, self.hub, clock=clock, notify=notify)
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


async def test_a_row_read_when_the_run_ended_is_read_again_once_the_owner_was_told(
    deps_factory, shell
):
    """The read that used to go wrong: after the run's end, before the channel answered."""
    held = Held()
    page = await Page(deps_factory(), held, Clock()).opens()
    ticking = asyncio.create_task(page.tick())
    await held.asked.wait()

    # The run is over on the page, and the page is not yet asked to read again.
    sent = await page.sent()
    assert sent[-1] == FAILED and "jobs" not in sent
    # What it reads now says a message is on the way, not that none got through.
    assert page.row() == {**stamps("07:05"), "telling": True}

    held.answer.set_result(True)
    await ticking

    assert await page.sent() == ["jobs"]
    assert page.row() == stamps("07:05", "07:05", "13:05")


async def test_the_page_is_asked_to_read_again_as_just_that_and_nothing_more(deps_factory, shell):
    clock = Clock()
    page = await Page(deps_factory(), Chat(clock), clock).opens()
    await page.tick()

    payloads = await page.payloads()

    assert payloads[-1] == {"type": "jobs"}
    assert [p["type"] for p in payloads].count("jobs") == 1


async def test_a_failure_nobody_could_be_told_of_is_read_again_too(deps_factory, shell):
    """Counted after the run ended all the same, so the row the page read may lack it."""
    page = await Page(deps_factory(), None, Clock()).opens()

    await page.tick()

    assert (await page.sent())[-2:] == [FAILED, "jobs"]
    assert page.row() == stamps("07:05")


async def test_a_failure_inside_the_wait_is_read_again_for_its_count(deps_factory, shell):
    clock = Clock()
    page = await Page(deps_factory(), Chat(clock), clock).opens()
    await page.tick()
    await page.sent()

    await page.tick()

    assert (await page.sent())[-2:] == [FAILED, "jobs"]
    assert page.row() == stamps("07:05", "07:05", "13:05", count=2)


async def test_a_job_that_mended_is_read_again_and_one_that_never_failed_is_not(
    deps_factory, shell
):
    clock = Clock()
    page = await Page(deps_factory(), Chat(clock), clock).opens()
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
