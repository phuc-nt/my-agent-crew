"""How often the person is told of a job that keeps failing (`scheduler/failure_streaks.py`).

A job that failed with no conversation to say so in is told to the agent's channel: a script
(`test_script_job_failure_notice.py`), a command, a rewrite of the agent's memory. One that
goes on failing is not told every time it does. The first failure is told at once; after it
at most one message every `RETELL_AFTER` says how many times in a row, since when, and why
the latest run failed; and one line says the job ran well again, if the person had been told
it was failing. A message counts as told only when the channel took it. The job's row on
`/api/jobs` shows the count through each of those.

The command of most jobs here is not run: `Shell` stands in for it and says how each run
ends, so a day of failures every five minutes is a second of test. What a command's failure
is told by is tested on real commands.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest

from my_agent_crew import texts, texts_script_job
from my_agent_crew import texts_job_failure as words
from my_agent_crew import texts_script as t
from my_agent_crew.activity import ActivityHub
from my_agent_crew.activity.step_previews import CUT, FAILURE_HEAD, FAILURE_TAIL
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents.profile import Schedule, consolidate_schedule
from my_agent_crew.channels.telegram_api import TelegramError
from my_agent_crew.config import Settings
from my_agent_crew.llm.fake import ScriptedProvider
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.types import TextDelta
from my_agent_crew.memory import agent_store
from my_agent_crew.scheduler import Job, Scheduler, jobs
from my_agent_crew.scheduler.failure_streaks import RETELL_AFTER, Streak, Streaks
from my_agent_crew.scheduler.jobs import command_failure
from my_agent_crew.server import create_app
from my_agent_crew.store.runs import AWAITING, DONE, FAILED, HALTED, RunRecord
from tests.test_scheduler import with_schedules
from tests.test_script_job_failure_notice import runtime_of
from tests.test_script_tool import erred

START = datetime(2026, 9, 19, 7, 0)
SYNC, NAME = "default/sync", "Đồng bộ"
MEMORY_JOB = "default/memory-consolidate"
EVERY_FIVE = Schedule("sync", NAME, every="5m", command="sync-ledger")
# How `Shell` ends a command unless told otherwise, and what the person is told of that.
PRINTED, CODE = "đang chép sổ\nkhông vào được sổ\n", 3
WHY = "Lệnh thoát với mã 3. Dòng cuối lệnh in ra: không vào được sổ"
SINCE = "07:05 ngày 19/09"
LOGGER = "my_agent_crew.scheduler.failure_notice"
# A channel that neither takes a message nor refuses it.
HANGS = object()


def first(reason: str = WHY, name: str = NAME) -> str:
    """The message of a first failure: which schedule, why, where the run is, and when the
    next message comes."""
    head = words.JOB_FAILED.format(name=name, reason=reason)
    return f"{head}\n{words.JOB_FAILED_NEXT.format(hours=6)}"


def again(count: int, since: str = SINCE, reason: str = WHY, name: str = NAME) -> str:
    """The message of a failure further on: the same lines, closed by how long it has been."""
    head = words.JOB_FAILED.format(name=name, reason=reason)
    return f"{head}\n{words.JOB_FAILED_AGAIN.format(count=count, since=since, hours=6)}"


def mended(count: int, name: str = NAME) -> str:
    return words.JOB_RECOVERED.format(name=name, count=count)


class Clock:
    def __init__(self, at: datetime = START):
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    def after(self, **step: float) -> datetime:
        self.at += timedelta(**step)
        return self.at


class Chat:
    """The agent's channel as the clock is given it: every message it was asked to say, and
    those it took, each with when."""

    def __init__(self, clock: Clock, answer: Any = True):
        self.clock, self.answer = clock, answer
        self.asked: list[str] = []
        self.took: list[tuple[datetime, str]] = []

    async def __call__(self, agent_id: str, text: str) -> bool:
        self.asked.append(text)
        if isinstance(self.answer, Exception):
            raise self.answer
        if self.answer is HANGS:
            await asyncio.Event().wait()
        if self.answer is True:
            self.took.append((self.clock(), text))
        return self.answer

    @property
    def texts(self) -> list[str]:
        return [text for _, text in self.took]


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
    chat: Chat
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
    chat = Chat(clock)
    sched = Scheduler({"default": deps}, ActivityHub(deps.store), clock=clock, notify=chat)
    return Rig(sched, clock, chat, shell, deps)


@pytest.fixture
def rig(deps_factory, shell) -> Rig:
    """A clock over one command job due every five minutes, whose command fails."""
    return clocked(deps_factory(), shell, EVERY_FIVE)


def stamps(since: str, told_at: str | None = None, again_at: str | None = None, count: int = 1):
    day = "2026-09-19T"
    return {
        "count": count,
        "since": day + since,
        "told_at": told_at and day + told_at,
        "next_notice_at": again_at and day + again_at,
    }


# --- how often ---


async def test_the_first_failure_is_told_at_once_and_says_when_the_next_message_comes(rig):
    assert rig.failing() is None

    [run] = await rig.tick()

    assert (run.status, run.conversation_id) == (FAILED, None)
    assert rig.chat.texts == [first()]
    assert rig.chat.texts[0] == (
        'Lịch "Đồng bộ" gặp lỗi khi chạy:\n'
        "Lệnh thoát với mã 3. Dòng cuối lệnh in ra: không vào được sổ\n"
        "Xem lượt chạy ở web UI, mục Quản lý → Hoạt động.\n"
        "Nếu lịch còn hỏng, tin nhắc kế tiếp sẽ đến sau 6 giờ."
    )
    assert rig.failing() == stamps("07:05", "07:05", "13:05")


async def test_a_job_failing_every_five_minutes_for_a_day_is_told_a_handful_of_times(rig):
    """What the spacing is for. Told at every run, the chat says the same thing two hundred
    and eighty-eight times and nobody reads it; told once, a job that has been down all day
    looks like one that mended in the morning."""
    for _ in range(24 * 12):
        await rig.tick()

    assert rig.shell.ran == 288 and rig.failing()["count"] == 288
    assert rig.chat.asked == rig.chat.texts
    times = [at for at, _ in rig.chat.took]
    # More than the first, and far fewer than the runs.
    assert 1 < len(times) < 10
    gaps = [later - sooner for sooner, later in zip(times, times[1:], strict=False)]
    # Never two closer than the wait between them, and never a wait a whole run longer:
    # the job was told of to the end of the day.
    assert all(RETELL_AFTER <= gap < RETELL_AFTER + timedelta(minutes=5) for gap in gaps)
    assert rig.clock() - times[-1] < RETELL_AFTER
    # The last of them says how long it has gone on by then.
    assert rig.chat.texts[-1] == again(217)


async def test_a_failure_before_the_wait_is_over_is_counted_and_not_told(rig):
    await rig.tick()
    await rig.tick()
    await rig.tick(hours=5, minutes=50)  # 13:00, five minutes short of the wait

    assert rig.shell.ran == 3 and rig.chat.asked == [first()]
    assert rig.failing() == stamps("07:05", "07:05", "13:05", count=3)


async def test_once_the_wait_is_over_the_next_failure_says_how_many_in_a_row_and_since_when(rig):
    await rig.tick()
    await rig.tick()
    await rig.tick(hours=5, minutes=50)
    await rig.tick()  # 13:05, the wait to the minute

    assert rig.chat.texts == [first(), again(4)]
    assert rig.chat.texts[1].split("\n")[1:] == [
        WHY,
        "Xem lượt chạy ở web UI, mục Quản lý → Hoạt động.",
        "Đây là lần hỏng thứ 4 liên tiếp, tính từ 07:05 ngày 19/09. "
        "Nếu lịch còn hỏng, tin nhắc kế tiếp sẽ đến sau 6 giờ.",
    ]
    assert rig.failing() == stamps("07:05", "13:05", "19:05", count=4)

    # The next wait is counted from that message, not from the first.
    await rig.tick()
    await rig.tick(hours=5, minutes=50)
    assert len(rig.chat.asked) == 2
    await rig.tick()
    assert rig.chat.texts[2:] == [again(7)]


async def test_the_latest_reason_is_the_one_told(rig):
    await rig.tick()
    rig.shell.result = (1, "sổ đã khoá\n")
    await rig.tick(hours=6)

    later = "Lệnh thoát với mã 1. Dòng cuối lệnh in ra: sổ đã khoá"
    assert rig.chat.texts == [first(), again(2, reason=later)]


async def test_each_job_is_counted_by_itself(deps_factory, shell):
    pull = Schedule("pull", "Kéo thư", every="5m", command="pull-mail")
    rig = clocked(deps_factory(), shell, EVERY_FIVE, pull)
    shell.fine.add("pull-mail")

    await rig.tick()
    shell.fine.clear()
    await rig.tick()

    # The second failure of one is inside its wait; the first of the other is told at once.
    assert rig.chat.texts == [first(), first(name="Kéo thư")]
    assert rig.failing() == stamps("07:05", "07:05", "13:05", count=2)
    assert rig.failing("default/pull") == stamps("07:10", "07:10", "13:10")


# --- a message the channel did not take ---

UNSENT = [False, TelegramError("refused by the chat"), HANGS]


@pytest.mark.parametrize("answer", UNSENT, ids=["nowhere to say it", "refused", "no answer"])
async def test_a_message_the_channel_did_not_take_is_tried_again_at_the_next_failure(
    rig, monkeypatch, answer
):
    monkeypatch.setattr(f"{LOGGER}.NOTICE_TIMEOUT_SECONDS", 0.05)
    rig.chat.answer = answer

    await rig.tick()
    await rig.tick()

    # Asked at each failure, the wait notwithstanding: nothing of this has been told yet.
    assert rig.chat.asked == [first(), again(2)] and rig.chat.took == []
    assert rig.failing() == stamps("07:05", count=2)

    rig.chat.answer = True
    await rig.tick()

    # What gets through says how many there have been by then, and the wait begins there.
    assert rig.chat.texts == [again(3)]
    assert rig.failing() == stamps("07:05", "07:15", "13:15", count=3)
    await rig.tick()
    assert len(rig.chat.asked) == 3


async def test_a_clock_with_nobody_to_tell_counts_all_the_same(deps_factory, shell):
    deps = with_schedules(deps_factory(), EVERY_FIVE)
    clock = Clock()
    sched = Scheduler({"default": deps}, ActivityHub(deps.store), clock=clock)

    for _ in range(2):
        clock.after(minutes=5)
        await sched.tick()

    assert sched.describe()[0]["failing"] == stamps("07:05", count=2)


# --- running well again ---


async def test_a_job_that_ran_well_again_is_told_once_with_how_many_failures_it_follows(rig):
    for _ in range(3):
        await rig.tick()
    rig.shell.mends()

    [run] = await rig.tick()

    assert run.status == DONE
    assert rig.chat.texts == [first(), 'Lịch "Đồng bộ" đã chạy lại được sau 3 lần hỏng liên tiếp.']
    assert rig.failing() is None
    await rig.tick()
    assert len(rig.chat.asked) == 2


async def test_a_job_nobody_was_told_had_failed_mends_without_a_word(rig):
    rig.chat.answer = False
    await rig.tick()
    await rig.tick()
    rig.chat.answer = True
    rig.shell.mends()

    await rig.tick()

    assert len(rig.chat.asked) == 2 and rig.chat.took == []
    assert rig.failing() is None


async def test_a_failure_after_the_job_mended_begins_a_new_count_and_is_told_at_once(rig):
    await rig.tick()
    await rig.tick()
    rig.shell.mends()
    await rig.tick()
    rig.shell.breaks()

    await rig.tick()  # 07:20, well inside the wait the first message began

    assert rig.chat.texts == [first(), mended(2), first()]
    assert rig.failing() == stamps("07:20", "07:20", "13:20")


async def test_a_line_of_recovery_the_channel_did_not_take_is_not_said_again(rig):
    await rig.tick()
    rig.shell.mends()
    rig.chat.answer = False

    await rig.tick()
    rig.chat.answer = True
    await rig.tick()

    assert rig.chat.asked == [first(), mended(1)] and rig.failing() is None


async def test_a_command_job_that_runs_well_says_nothing(rig):
    rig.shell.mends()

    [run] = await rig.tick()

    assert run.status == DONE and rig.chat.asked == [] and rig.failing() is None


async def test_a_command_that_ran_well_hands_on_no_reason_it_failed(deps_factory, shell):
    deps = with_schedules(deps_factory(), EVERY_FIVE)
    job = Job(SYNC, "default", EVERY_FIVE)
    shell.mends()

    run, why = await jobs.run_command(job, deps, ActivityHub(deps.store), NAME)

    assert (run.status, why) == (DONE, "")


# --- the count itself, one ending at a time ---


def ended(status: str, conversation_id: str | None = None) -> RunRecord:
    return RunRecord("r1", "default", conversation_id, f"job:{SYNC}", NAME, status, "2026-09-19")


def counting(notify: Any = None) -> tuple[Streaks, Clock, Chat, Job]:
    clock = Clock()
    chat = Chat(clock)
    return Streaks(notify or chat, clock), clock, chat, Job(SYNC, "default", EVERY_FIVE)


WORDLESS = [(HALTED, None), (HALTED, "c1"), (FAILED, "c1"), (AWAITING, "c1")]


@pytest.mark.parametrize(("status", "conversation"), WORDLESS)
async def test_an_ending_that_is_neither_a_failure_nor_a_run_gone_well_ends_the_count_unsaid(
    status, conversation
):
    """A run that was stopped, or a turn that failed and says so where it failed: the job
    is no longer failing in the way that was counted, and has not run well either."""
    streaks, clock, chat, job = counting()
    await streaks.settle(job, ended(FAILED), WHY)
    assert streaks.of(SYNC) == Streak(1, START, START)

    await streaks.settle(job, ended(status, conversation), "")

    assert streaks.of(SYNC) is None and chat.asked == [first()]
    # What fails after it is the first of a new count.
    clock.after(minutes=5)
    await streaks.settle(job, ended(FAILED), WHY)
    assert chat.texts == [first(), first()] and streaks.of(SYNC).count == 1


async def test_a_turn_that_went_well_ends_the_count_with_the_line_as_any_run_gone_well_does():
    """A script job's run has a conversation when its script printed and the turn was made."""
    streaks, _, chat, job = counting()
    await streaks.settle(job, ended(FAILED), WHY)

    await streaks.settle(job, ended(DONE, "c1"), "")

    assert chat.texts == [first(), mended(1)] and streaks.of(SYNC) is None


async def test_the_wait_is_counted_from_when_the_channel_took_the_message():
    async def slow(agent_id: str, text: str) -> bool:
        clock.after(minutes=2)
        return True

    streaks, clock, _, job = counting(slow)

    await streaks.settle(job, ended(FAILED), WHY)

    assert streaks.of(SYNC) == Streak(1, START, START + timedelta(minutes=2))
    assert streaks.of(SYNC).to_dict() == stamps("07:00", "07:02", "13:02")


async def test_a_failure_counted_while_a_message_was_on_its_way_is_kept():
    """Two runs of one job can overlap: the clock's, and one started from the button."""
    gate = asyncio.Event()
    asked: list[str] = []

    async def held(agent_id: str, text: str) -> bool:
        asked.append(text)
        await gate.wait()
        return True

    streaks, _, _, job = counting(held)
    one = asyncio.create_task(streaks.settle(job, ended(FAILED), WHY))
    await asyncio.sleep(0)
    other = asyncio.create_task(streaks.settle(job, ended(FAILED), WHY))
    await asyncio.sleep(0)
    gate.set()
    await asyncio.gather(one, other)

    assert asked == [first(), again(2, "07:00 ngày 19/09")]
    assert streaks.of(SYNC) == Streak(2, START, START)


async def test_a_job_that_left_while_its_message_was_on_its_way_keeps_no_count():
    async def leaves(agent_id: str, text: str) -> bool:
        streaks.forget(SYNC)
        return True

    streaks, _, _, job = counting(leaves)

    await streaks.settle(job, ended(FAILED), WHY)

    assert streaks.of(SYNC) is None


async def test_what_was_counted_goes_with_the_job_and_with_its_agent():
    streaks, _, _, _ = counting()
    ids = ["default/sync", "default/pull", "coach/sync", "defaulted/sync"]
    for job_id in ids:
        job = Job(job_id, job_id.split("/")[0], EVERY_FIVE)
        await streaks.settle(job, ended(FAILED), WHY)

    streaks.forget("default/pull")
    assert [job_id for job_id in ids if streaks.of(job_id)] == [ids[0], ids[2], ids[3]]

    # By the agent's whole id: an agent whose id only begins the same keeps its own.
    streaks.forget_agent("default")
    assert [job_id for job_id in ids if streaks.of(job_id)] == ["coach/sync", "defaulted/sync"]
    streaks.forget("nobody/nothing")


async def test_a_job_that_left_the_clock_while_it_ran_is_not_told(rig):
    """What its run came to would be held against whichever job is later made under its id."""
    rig.shell.during = lambda: rig.sched.forget_agent("default")

    [run] = await rig.tick()

    assert run.status == FAILED and rig.sched.describe() == []
    assert rig.chat.asked == []


# --- what a command's failure is told by ---

COMMANDS = [
    ("echo đang chép sổ; echo 'không vào được sổ'; exit 3", WHY),
    ("echo 'lỗi ở stderr' >&2; exit 2", "Lệnh thoát với mã 2. Dòng cuối lệnh in ra: lỗi ở stderr"),
    ("echo hết chỗ; echo; echo ' '; exit 1", "Lệnh thoát với mã 1. Dòng cuối lệnh in ra: hết chỗ"),
    ("exit 4", "Lệnh thoát với mã 4."),
]


def real(deps: AgentDeps, *schedules: Schedule) -> tuple[Scheduler, Chat]:
    """A clock whose jobs run their commands for real."""
    with_schedules(deps, *schedules)
    clock = Clock()
    chat = Chat(clock)
    return Scheduler({"default": deps}, ActivityHub(deps.store), clock=clock, notify=chat), chat


@pytest.mark.parametrize(
    ("command", "why"), COMMANDS, ids=["last line", "stderr", "blank lines after", "silent"]
)
async def test_a_command_job_that_failed_is_told_by_its_exit_code_and_its_last_line(
    deps_factory, command, why
):
    sched, chat = real(deps_factory(), Schedule("sync", NAME, every="1h", command=command))

    run = await sched.run_job(SYNC)

    assert (run.status, run.conversation_id) == (FAILED, None)
    assert chat.texts == [first(why)]


async def test_a_command_stopped_at_its_limit_is_told_it_ran_past_it(deps_factory, monkeypatch):
    monkeypatch.setattr(jobs, "COMMAND_TIMEOUT_SECONDS", 0.2)
    command = "echo bắt đầu; exec sleep 5"
    sched, chat = real(deps_factory(), Schedule("sync", NAME, every="1h", command=command))

    run = await sched.run_job(SYNC)

    assert (run.status, run.conversation_id) == (FAILED, None)
    assert chat.texts == [first("Lệnh vượt quá 0.2 giây và đã bị dừng.")]


def test_the_limit_a_stopped_command_is_told_by_is_the_one_a_command_job_runs_under():
    assert command_failure(None, "") == "Lệnh vượt quá 900 giây và đã bị dừng."
    assert command_failure(None, "in dở\n") == texts.SHELL_TIMEOUT.format(seconds=900)


async def test_a_long_last_line_is_cut_as_every_reason_is(rig):
    rig.shell.result = (3, "dòng đầu\nmở đầu " + "x" * 900 + " việc cần làm\n")

    await rig.tick()

    whole = "Lệnh thoát với mã 3. Dòng cuối lệnh in ra: mở đầu " + "x" * 900 + " việc cần làm"
    reason = whole[:FAILURE_HEAD] + CUT + whole[-FAILURE_TAIL:]
    assert len(reason) == 601 and rig.chat.texts == [first(reason)]
    assert "dòng đầu" not in rig.chat.texts[0]


# --- the other kinds ---


async def test_a_script_job_that_goes_on_failing_keeps_its_own_first_lines(deps_factory, shell):
    due = Schedule("due", "Nhắc hạn", every="5m", script="print(nowhere_named)")
    rig = clocked(deps_factory(), shell, due)

    await rig.tick()
    await rig.tick(hours=6)

    why = erred(1, t.SCRIPT_NO_NAME.format(name="nowhere_named"))
    head = texts_script_job.JOB_SCRIPT_FAILED.format(name="Nhắc hạn", reason=why)
    closing = words.JOB_FAILED_AGAIN.format(count=2, since=SINCE, hours=6)
    assert rig.chat.texts == [
        f"{head}\n{words.JOB_FAILED_NEXT.format(hours=6)}",
        f"{head}\n{closing}",
    ]
    assert rig.failing("default/due") == stamps("07:05", "13:05", "19:05", count=2)


async def test_a_prompt_job_that_keeps_failing_is_never_counted_here(deps_factory, shell):
    """Each of its turns is a conversation's, and is sent on with why it failed."""
    broken = ScriptedProvider([ProviderError("503"), ProviderError("503")])
    brief = Schedule("brief", "Bản tin", every="5m", prompt="soạn bản tin")
    rig = clocked(deps_factory(providers={"scripted": broken}), shell, brief)

    for _ in range(2):
        [run] = await rig.tick()
        assert run.status == FAILED and run.conversation_id is not None

    assert rig.chat.asked == [] and rig.failing("default/brief") is None


def with_a_note_to_fold_in(deps: AgentDeps) -> AgentDeps:
    """An agent whose memory is due a rewrite: one note newer than its `MEMORY.md`."""
    agent_store.write_memory_md(deps.agent.memory_file, "- Sếp thích trà buổi sáng.")
    agent_store.write_note(deps.agent.memory_dir, "2026-09-19", "Hạn Eco dời sang thứ tư.")
    stamp = deps.agent.memory_file.stat().st_mtime + 10
    os.utime(deps.agent.memory_dir / "2026-09-19.md", (stamp, stamp))
    return deps


NIGHTLY = consolidate_schedule("5 7 * * *")
AFTER = Schedule("after", "Việc sau", cron="5 7 * * *", command="sync-ledger")


async def test_a_rewrite_of_memory_that_raised_is_told_and_the_jobs_after_it_still_run(
    deps_factory, shell
):
    # The scripted provider raises when it has nothing left to answer with.
    rig = clocked(with_a_note_to_fold_in(deps_factory(script=[])), shell, NIGHTLY, AFTER)
    shell.mends()

    [failed, later] = await rig.tick()

    assert (failed.source, failed.status) == (f"job:{MEMORY_JOB}", FAILED)
    assert failed.conversation_id is None and failed.summary
    assert rig.chat.texts == [first(failed.summary, texts.CONSOLIDATE_JOB_NAME)]
    assert rig.failing(MEMORY_JOB) == stamps("07:05", "07:05", "13:05")
    # The job due in the same round ran, and the clock is not left holding the one that failed.
    assert (later.source, later.status) == ("job:default/after", DONE)
    assert [row["running"] for row in rig.sched.describe()] == [False, False]


class Wordless:
    """A provider whose stream holds words and never the completion they belong to."""

    name = "scripted"

    async def stream(self, messages, tools, model, reasoning=""):
        yield TextDelta("…")


async def test_a_rewrite_the_model_gave_nothing_for_is_told_by_the_line_that_says_so(
    deps_factory, shell
):
    deps = with_a_note_to_fold_in(deps_factory(providers={"scripted": Wordless()}))
    rig = clocked(deps, shell, NIGHTLY)

    [run] = await rig.tick()

    assert (run.status, run.summary) == (FAILED, texts.CONSOLIDATE_EMPTY)
    assert rig.chat.texts == [first(texts.CONSOLIDATE_EMPTY, texts.CONSOLIDATE_JOB_NAME)]


async def test_a_rewrite_with_nothing_new_to_fold_in_is_no_failure(deps_factory, shell):
    rig = clocked(deps_factory(script=[]), shell, NIGHTLY)

    [run] = await rig.tick()

    assert (run.status, run.summary) == (DONE, texts.CONSOLIDATE_NOTHING_NEW)
    assert rig.chat.asked == [] and rig.failing(MEMORY_JOB) is None


EARLIER = [None, DONE, FAILED]


@pytest.mark.parametrize(
    "earlier", EARLIER, ids=["no run of it yet", "after one gone well", "after one that failed"]
)
async def test_a_rewrite_that_raised_before_it_had_a_run_is_raised_as_it_was(
    deps_factory, shell, monkeypatch, earlier
):
    """There is no run of this rewrite to tell the person by, and the run the job's last
    rewrite left, well or not, is not this one's."""
    deps = deps_factory(script=[])
    rig = clocked(with_a_note_to_fold_in(deps) if earlier == FAILED else deps, shell, NIGHTLY)
    if earlier:
        assert (await rig.sched.run_job(MEMORY_JOB)).status == earlier
    told = list(rig.chat.asked)
    assert len(told) == (1 if earlier == FAILED else 0)

    async def never_began(*args: Any, **kwargs: Any):
        raise RuntimeError("không mở được sổ run")

    monkeypatch.setattr(jobs, "consolidate_memory", never_began)

    with pytest.raises(RuntimeError):
        await rig.sched.run_job(MEMORY_JOB)

    assert rig.chat.asked == told
    assert rig.failing(MEMORY_JOB) == (stamps("07:00", "07:00", "13:00") if told else None)


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

    assert rig.chat.asked == [] and rig.failing(MEMORY_JOB) is None


# --- on the jobs page ---


async def test_the_row_of_a_job_shows_its_count_through_every_stage(
    make_channel, deps_factory, fake, shell, monkeypatch
):
    deps = with_schedules(deps_factory(), EVERY_FIVE)
    clock = Clock(START.replace(tzinfo=deps.settings.zone))
    monkeypatch.setattr(Settings, "now", lambda self: clock())
    runtime = runtime_of(make_channel(deps))
    transport = httpx.ASGITransport(app=create_app(runtime, schedule=False))

    def at(minutes: int) -> str:
        return (clock.at.replace(hour=7, minute=0) + timedelta(minutes=minutes)).isoformat(
            timespec="minutes"
        )

    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:

        async def row() -> dict[str, Any]:
            [job] = (await client.get("/api/jobs")).json()
            return job

        async def tick() -> None:
            clock.after(minutes=5)
            await runtime.scheduler.tick()

        assert (await row())["failing"] is None

        # Failed, and the chat refused the message.
        fake.fail["sendMessage"] = 500
        await tick()
        untold = {"count": 1, "since": at(5), "told_at": None, "next_notice_at": None}
        assert (await row())["failing"] == untold

        # Failed again, and this time the chat took it.
        fake.fail.clear()
        await tick()
        told = {"count": 2, "since": at(5), "told_at": at(10), "next_notice_at": at(370)}
        assert (await row())["failing"] == told
        assert fake.sent == [again(2)]
        # Written on the owner's clock with its offset, as the row's next run is.
        assert datetime.fromisoformat(told["since"]).utcoffset() is not None

        # Failed inside the wait: counted, and the rest as it was.
        await tick()
        assert (await row())["failing"] == {**told, "count": 3}
        assert len(fake.sent) == 1

        # Ran well: the line of it, and the row is as one that never failed.
        shell.mends()
        await tick()
        assert (await row())["failing"] is None
        assert fake.sent == [again(2), mended(3)]
