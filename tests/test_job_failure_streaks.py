"""How the failures in a row of a job are counted (`scheduler/failure_streaks.py`).

A job that failed with no conversation of its own is counted: a script, a command, a rewrite
of the agent's memory. So is a run whose check disagreed (`test_job_check.py`). Any other
ending closes the count, and the job's row on `/api/jobs` shows how many in a row and since
when. Nobody is told of a count on any channel: the chat hears nothing of a failing job, of
one that mended, or of how long it has been down.

The command of most jobs here is not run: `Shell` stands in for it and says how each run
ends, so a day of failures every five minutes is a second of test.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents.profile import Schedule, consolidate_schedule
from my_agent_crew.config import Settings
from my_agent_crew.llm.fake import ScriptedProvider
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.types import TextDelta
from my_agent_crew.memory import agent_store
from my_agent_crew.scheduler import Scheduler, jobs
from my_agent_crew.scheduler.failure_streaks import Streak, Streaks, counts_as_failure
from my_agent_crew.scheduler.jobs import command_failure
from my_agent_crew.server import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store.runs import AWAITING, DONE, FAILED, HALTED, RunRecord
from tests.test_scheduler import with_schedules

START = datetime(2026, 9, 19, 7, 0)
SYNC, NAME = "default/sync", "Đồng bộ"
MEMORY_JOB = "default/memory-consolidate"
EVERY_FIVE = Schedule("sync", NAME, every="5m", command="sync-ledger")
# How `Shell` ends a command unless told otherwise.
PRINTED, CODE = "đang chép sổ\nkhông vào được sổ\n", 3


class Clock:
    def __init__(self, at: datetime = START):
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    def after(self, **step: float) -> datetime:
        self.at += timedelta(**step)
        return self.at


class Shell:
    """Stands in for running a job's command: every run ends as `result` says, but for a
    command named in `fine`, which runs well."""

    def __init__(self) -> None:
        self.result: tuple[int | None, str] = (CODE, PRINTED)
        self.fine: set[str] = set()
        self.ran = 0
        # Called while a command runs, for what happens to a job in the middle of its run.
        self.during: Callable[[], None] | None = None

    async def __call__(self, command: str, cwd: Any, timeout_s: float, **more: Any):
        self.ran += 1
        if self.during is not None:
            self.during()
        return (0, "xong\n") if command in self.fine else self.result

    def mends(self) -> None:
        self.result = (0, "xong\n")

    def breaks(self) -> None:
        self.result = (CODE, PRINTED)


@dataclass
class Rig:
    sched: Scheduler
    clock: Clock
    shell: Shell
    deps: AgentDeps

    async def tick(self, **after: float) -> list[RunRecord]:
        """Moves the clock on, by five minutes unless told otherwise, and has it look."""
        self.clock.after(**(after or {"minutes": 5}))
        return await self.sched.tick()

    def failing(self, job_id: str = SYNC) -> dict[str, Any] | None:
        [row] = [row for row in self.sched.describe() if row["id"] == job_id]
        return row["failing"]


@pytest.fixture
def shell(monkeypatch) -> Shell:
    shell = Shell()
    monkeypatch.setattr(jobs, "run_shell", shell)
    return shell


def clocked(deps: AgentDeps, shell: Shell, *schedules: Schedule) -> Rig:
    with_schedules(deps, *schedules)
    clock = Clock()
    sched = Scheduler({"default": deps}, ActivityHub(deps.store), clock=clock)
    return Rig(sched, clock, shell, deps)


@pytest.fixture
def rig(deps_factory, shell) -> Rig:
    """A clock over one command job due every five minutes, whose command fails."""
    return clocked(deps_factory(), shell, EVERY_FIVE)


def stamps(since: str, count: int = 1) -> dict[str, Any]:
    """A row's `failing`: how many in a row and since when, and nothing of anyone told."""
    return {"count": count, "since": "2026-09-19T" + since}


def runtime_of(channel, **more) -> Runtime:
    """The runtime around a bot and the agents it knows, as a server start makes it."""
    deps = channel.deps
    return Runtime(
        settings=deps.settings,
        store=deps.store,
        agents=dict(channel.agents),
        hub=channel.hub,
        channel=channel,
        **more,
    )


# --- the count ---


async def test_a_job_failing_every_five_minutes_for_a_day_is_counted_from_its_first_failure(rig):
    assert rig.failing() is None

    for _ in range(24 * 12):
        await rig.tick()

    assert rig.shell.ran == 288
    assert rig.failing() == stamps("07:05", count=288)


async def test_each_job_is_counted_by_itself(deps_factory, shell):
    pull = Schedule("pull", "Kéo thư", every="5m", command="pull-mail")
    rig = clocked(deps_factory(), shell, EVERY_FIVE, pull)
    shell.fine.add("pull-mail")

    await rig.tick()
    shell.fine.clear()
    await rig.tick()

    assert rig.failing() == stamps("07:05", count=2)
    assert rig.failing("default/pull") == stamps("07:10")


async def test_a_job_that_ran_well_again_closes_its_count(rig):
    for _ in range(3):
        await rig.tick()
    rig.shell.mends()

    [run] = await rig.tick()

    assert run.status == DONE and rig.failing() is None


async def test_a_failure_after_the_job_mended_begins_a_new_count(rig):
    await rig.tick()
    await rig.tick()
    rig.shell.mends()
    await rig.tick()
    rig.shell.breaks()

    await rig.tick()

    assert rig.failing() == stamps("07:20")


async def test_a_command_job_that_runs_well_is_never_failing(rig):
    rig.shell.mends()

    [run] = await rig.tick()

    assert run.status == DONE and rig.failing() is None


async def test_a_job_that_left_the_clock_while_it_ran_keeps_no_count(rig):
    """What its run came to would be held against whichever job is later made under its id."""
    rig.shell.during = lambda: rig.sched.forget_agent("default")

    [run] = await rig.tick()

    assert run.status == FAILED and rig.sched.describe() == []
    assert rig.sched._streaks.of(SYNC) is None


# --- one ending at a time ---


def ended(status: str, conversation_id: str | None = None) -> RunRecord:
    return RunRecord("r1", "default", conversation_id, f"job:{SYNC}", NAME, status, "2026-09-19")


ENDINGS = [
    (FAILED, None, False, True),
    (FAILED, "c1", False, False),
    (DONE, None, False, False),
    (DONE, "c1", False, False),
    (HALTED, None, False, False),
    (HALTED, "c1", False, False),
    (AWAITING, "c1", False, False),
    (FAILED, None, True, True),
    (FAILED, "c1", True, True),
]


@pytest.mark.parametrize(("status", "conversation", "check_failed", "counts"), ENDINGS)
def test_what_counts_is_a_failure_with_no_turn_or_a_check_that_disagreed(
    status, conversation, check_failed, counts
):
    """A turn that failed says so in its conversation, which the inbox shows; a run that was
    stopped or waits for an answer has neither failed nor run well."""
    assert counts_as_failure(ended(status, conversation), check_failed) is counts


def test_an_ending_that_does_not_count_closes_the_count_and_the_next_failure_starts_one():
    streaks = Streaks()
    streaks.settle(SYNC, True, START)
    streaks.settle(SYNC, True, START + timedelta(minutes=5))
    assert streaks.of(SYNC) == Streak(2, START)

    streaks.settle(SYNC, False, START + timedelta(minutes=10))
    assert streaks.of(SYNC) is None

    streaks.settle(SYNC, True, START + timedelta(minutes=15))
    assert streaks.of(SYNC) == Streak(1, START + timedelta(minutes=15))
    assert streaks.of(SYNC).to_dict() == stamps("07:15")


def test_what_was_counted_goes_with_the_job_and_with_its_agent():
    streaks = Streaks()
    ids = ["default/sync", "default/pull", "coach/sync", "defaulted/sync"]
    for job_id in ids:
        streaks.settle(job_id, True, START)

    streaks.forget("default/pull")
    assert [job_id for job_id in ids if streaks.of(job_id)] == [ids[0], ids[2], ids[3]]

    # By the agent's whole id: an agent whose id only begins the same keeps its own.
    streaks.forget_agent("default")
    assert [job_id for job_id in ids if streaks.of(job_id)] == ["coach/sync", "defaulted/sync"]
    streaks.forget("nobody/nothing")


def test_the_limit_a_stopped_command_is_summed_up_by_is_the_one_a_command_job_runs_under():
    assert command_failure(None, "") == "Lệnh vượt quá 900 giây và đã bị dừng."
    assert command_failure(None, "in dở\n") == texts.SHELL_TIMEOUT.format(seconds=900)


# --- the other kinds ---


async def test_a_script_job_that_goes_on_failing_is_counted(deps_factory, shell):
    due = Schedule("due", "Nhắc hạn", every="5m", script="print(nowhere_named)")
    rig = clocked(deps_factory(), shell, due)

    await rig.tick()
    await rig.tick(hours=6)

    assert rig.failing("default/due") == stamps("07:05", count=2)


async def test_a_prompt_job_that_keeps_failing_is_never_counted(deps_factory, shell):
    """Each of its turns is a conversation's, and says there why it failed."""
    broken = ScriptedProvider([ProviderError("503"), ProviderError("503")])
    brief = Schedule("brief", "Bản tin", every="5m", prompt="soạn bản tin")
    rig = clocked(deps_factory(providers={"scripted": broken}), shell, brief)

    for _ in range(2):
        [run] = await rig.tick()
        assert run.status == FAILED and run.conversation_id is not None

    assert rig.failing("default/brief") is None


def with_a_note_to_fold_in(deps: AgentDeps) -> AgentDeps:
    """An agent whose memory is due a rewrite: one note newer than its `MEMORY.md`."""
    agent_store.write_memory_md(deps.agent.memory_file, "- Sếp thích trà buổi sáng.")
    agent_store.write_note(deps.agent.memory_dir, "2026-09-19", "Hạn Eco dời sang thứ tư.")
    stamp = deps.agent.memory_file.stat().st_mtime + 10
    os.utime(deps.agent.memory_dir / "2026-09-19.md", (stamp, stamp))
    return deps


NIGHTLY = consolidate_schedule("5 7 * * *")
AFTER = Schedule("after", "Việc sau", cron="5 7 * * *", command="sync-ledger")


async def test_a_rewrite_of_memory_that_raised_is_counted_and_the_jobs_after_it_still_run(
    deps_factory, shell
):
    # The scripted provider raises when it has nothing left to answer with.
    rig = clocked(with_a_note_to_fold_in(deps_factory(script=[])), shell, NIGHTLY, AFTER)
    shell.mends()

    [failed, later] = await rig.tick()

    assert (failed.source, failed.status) == (f"job:{MEMORY_JOB}", FAILED)
    assert failed.conversation_id is None and failed.summary
    assert rig.failing(MEMORY_JOB) == stamps("07:05")
    # The job due in the same round ran, and the clock is not left holding the one that failed.
    assert (later.source, later.status) == ("job:default/after", DONE)
    assert [row["running"] for row in rig.sched.describe()] == [False, False]


class Wordless:
    """A provider whose stream holds words and never the completion they belong to."""

    name = "scripted"

    async def stream(self, messages, tools, model, reasoning=""):
        yield TextDelta("…")


async def test_a_rewrite_the_model_gave_nothing_for_is_counted(deps_factory, shell):
    deps = with_a_note_to_fold_in(deps_factory(providers={"scripted": Wordless()}))
    rig = clocked(deps, shell, NIGHTLY)

    [run] = await rig.tick()

    assert (run.status, run.summary) == (FAILED, texts.CONSOLIDATE_EMPTY)
    assert rig.failing(MEMORY_JOB) == stamps("07:05")


async def test_a_rewrite_with_nothing_new_to_fold_in_is_no_failure(deps_factory, shell):
    rig = clocked(deps_factory(script=[]), shell, NIGHTLY)

    [run] = await rig.tick()

    assert (run.status, run.summary) == (DONE, texts.CONSOLIDATE_NOTHING_NEW)
    assert rig.failing(MEMORY_JOB) is None


EARLIER = [None, DONE, FAILED]


@pytest.mark.parametrize(
    "earlier", EARLIER, ids=["no run of it yet", "after one gone well", "after one that failed"]
)
async def test_a_rewrite_that_raised_before_it_had_a_run_is_raised_as_it_was(
    deps_factory, shell, monkeypatch, earlier
):
    """There is no run of this rewrite to count by, and the run the job's last rewrite
    left, well or not, is not this one's."""
    deps = deps_factory(script=[])
    rig = clocked(with_a_note_to_fold_in(deps) if earlier == FAILED else deps, shell, NIGHTLY)
    if earlier:
        assert (await rig.sched.run_job(MEMORY_JOB)).status == earlier
    before = rig.failing(MEMORY_JOB)

    async def never_began(*args: Any, **kwargs: Any):
        raise RuntimeError("không mở được sổ run")

    monkeypatch.setattr(jobs, "consolidate_memory", never_began)

    with pytest.raises(RuntimeError):
        await rig.sched.run_job(MEMORY_JOB)

    assert rig.failing(MEMORY_JOB) == before
    assert before == (stamps("07:00") if earlier == FAILED else None)


async def test_a_rewrite_that_raised_with_its_run_still_open_is_raised_as_it_was(
    deps_factory, shell, monkeypatch
):
    """What stopped it stopped it from closing its run too, and a run left open says
    nothing of why."""

    async def left_open(deps: AgentDeps, hub: ActivityHub, source: str):
        hub.start(deps.agent.id, source, texts.CONSOLIDATE_JOB_NAME, None)
        raise RuntimeError("đĩa đầy")

    monkeypatch.setattr(jobs, "consolidate_memory", left_open)
    rig = clocked(deps_factory(), shell, NIGHTLY)

    with pytest.raises(RuntimeError):
        await rig.sched.run_job(MEMORY_JOB)

    assert rig.failing(MEMORY_JOB) is None


# --- on the jobs page, with a chat beside it ---


async def test_the_row_of_a_job_shows_its_count_and_the_chat_hears_nothing_of_it(
    make_channel, deps_factory, fake, shell, monkeypatch
):
    deps = with_schedules(deps_factory(), EVERY_FIVE)
    clock = Clock(START.replace(tzinfo=deps.settings.zone))
    monkeypatch.setattr(Settings, "now", lambda self: clock())
    runtime = runtime_of(make_channel(deps))
    transport = httpx.ASGITransport(app=create_app(runtime, schedule=False))
    since = clock.at.replace(minute=5).isoformat(timespec="minutes")

    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:

        async def row() -> dict[str, Any]:
            [job] = (await client.get("/api/jobs")).json()
            return job

        async def tick() -> None:
            clock.after(minutes=5)
            await runtime.scheduler.tick()

        assert (await row())["failing"] is None

        await tick()
        assert (await row())["failing"] == {"count": 1, "since": since}
        # Written on the owner's clock with its offset, as the row's next run is.
        assert datetime.fromisoformat(since).utcoffset() is not None

        await tick()
        await tick()
        assert (await row())["failing"] == {"count": 3, "since": since}

        shell.mends()
        await tick()
        assert (await row())["failing"] is None

    assert fake.calls == []
