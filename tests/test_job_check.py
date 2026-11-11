"""A schedule's `check`: the command that says whether a job did what it was for
(`scheduler/check.py`).

A job that ended well and states a check has the check run after it, as a command job's
command is run. A check that leaves with 0 changes nothing. One that leaves with anything
else, or runs past its limit, makes the run a failed one, and the person is told in words
that say the job ended well and the check disagreed, at the pace any failing job is told
at. A job that states none runs as it always did.

`Shell` stands in for the commands of most jobs here, as in `test_job_failure_streaks.py`;
that a check runs through the real shell, in the agent's workspace, is tested on real ones.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from my_agent_crew import texts
from my_agent_crew import texts_job_failure as words
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.agents.profile_yaml import parse_profile
from my_agent_crew.llm.fake import completion
from my_agent_crew.scheduler import Scheduler, jobs
from my_agent_crew.scheduler.check import CheckFailed
from my_agent_crew.scheduler.failure_notice import failure_notice
from my_agent_crew.store.runs import DONE, FAILED
from tests.test_job_failure_streaks import (
    NAME,
    SINCE,
    SYNC,
    WHY,
    Chat,
    Clock,
    Rig,
    Shell,
    again,
    clocked,
    first,
    mended,
)
from tests.test_scheduler import with_schedules

CHECK = "test -s ledger.csv"
CHECKED = Schedule("sync", NAME, every="5m", command="sync-ledger", check=CHECK)
ASKED = Schedule("sync", NAME, every="5m", prompt="chép sổ", check=CHECK)


def disagreed(reason: str = WHY, closing: str | None = None) -> str:
    """The message of a job that ended well and whose check did not: its own first line."""
    head = words.JOB_CHECK_FAILED.format(name=NAME, reason=reason)
    return f"{head}\n{closing or words.JOB_FAILED_NEXT.format(hours=6)}"


class Shells(Shell):
    """`Shell`, keeping what each command was run with."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, Any, float]] = []

    async def __call__(self, command: str, cwd: Any, timeout_s: float, **more: Any):
        self.calls.append((command, cwd, timeout_s))
        return await super().__call__(command, cwd, timeout_s, **more)


@pytest.fixture
def shell(monkeypatch) -> Shells:
    shell = Shells()
    shell.fine = {"sync-ledger"}
    monkeypatch.setattr(jobs, "run_shell", shell)
    return shell


@pytest.fixture
def rig(deps_factory, shell) -> Rig:
    """A command job that runs well every five minutes, and whose check fails."""
    return clocked(deps_factory(), shell, CHECKED)


def asking(deps_factory, shell: Shells, *replies: str) -> tuple[Rig, list[tuple[str, str]]]:
    """A prompt job the model answers, with its check; and what was sent on of its turns."""
    deps = deps_factory(script=[completion(reply) for reply in replies])
    with_schedules(deps, ASKED)
    clock = Clock()
    chat = Chat(clock)
    sent: list[tuple[str, str]] = []

    async def deliver(agent_id: str, conversation_id: str) -> bool:
        history = deps.store.history(conversation_id)
        sent.append((history[-1].message.content, sched_runs(deps)[0].status))
        return True

    hub = ActivityHub(deps.store)
    sched = Scheduler({"default": deps}, hub, clock=clock, deliver=deliver, notify=chat)
    return Rig(sched, clock, chat, shell, deps), sent


def sched_runs(deps):
    return deps.store.runs.recent(10)


# --- a command job ---


async def test_a_check_that_agrees_leaves_the_run_done_and_tells_nobody(rig):
    rig.shell.fine.add(CHECK)

    [run] = await rig.tick()

    assert (run.status, run.summary) == (DONE, "xong")
    workspace = rig.deps.agent.workspace
    assert rig.shell.calls == [
        ("sync-ledger", workspace, jobs.COMMAND_TIMEOUT_SECONDS),
        (CHECK, workspace, jobs.COMMAND_TIMEOUT_SECONDS),
    ]
    assert [(step["name"], step["ok"]) for step in run.steps] == [
        ("shell_run", True),
        ("shell_run", True),
    ]
    assert rig.chat.asked == [] and rig.failing() is None


async def test_a_check_that_disagrees_fails_the_run_and_says_the_job_itself_ended_well(rig):
    [run] = await rig.tick()

    assert run.status == FAILED and run.conversation_id is None
    assert run.summary == words.JOB_CHECK_SUMMARY.format(reason=WHY)
    assert [step["ok"] for step in run.steps] == [True, False]
    [kept] = sched_runs(rig.deps)
    assert (kept.id, kept.status, kept.summary) == (run.id, FAILED, run.summary)
    assert rig.chat.texts == [disagreed()]
    assert rig.chat.texts[0] == (
        'Lịch "Đồng bộ" báo đã chạy xong, nhưng lệnh kiểm tra sau khi chạy không xác nhận:\n'
        "Lệnh thoát với mã 3. Dòng cuối lệnh in ra: không vào được sổ\n"
        "Xem lượt chạy ở web UI, mục Quản lý → Hoạt động.\n"
        "Nếu lịch còn hỏng, tin nhắc kế tiếp sẽ đến sau 6 giờ."
    )
    # Not the words of a job that broke.
    assert rig.chat.texts[0] != first()
    assert rig.failing()["count"] == 1


async def test_a_check_stopped_at_its_limit_is_told_as_one_that_ran_too_long(rig):
    rig.shell.result = (None, "")

    [run] = await rig.tick()

    assert run.status == FAILED
    limit = texts.SHELL_TIMEOUT.format(seconds=jobs.COMMAND_TIMEOUT_SECONDS)
    assert rig.chat.texts == [disagreed(limit)]


async def test_a_job_that_failed_is_not_checked_and_is_told_as_any_failed_job(rig):
    rig.shell.fine.clear()

    [run] = await rig.tick()

    assert run.status == FAILED
    assert [command for command, _, _ in rig.shell.calls] == ["sync-ledger"]
    assert rig.chat.texts == [first()]


async def test_a_check_that_keeps_disagreeing_is_told_at_the_pace_of_a_failing_job(rig):
    for _ in range(72):
        await rig.tick()
    assert rig.chat.texts == [disagreed()]

    await rig.tick()

    closing = words.JOB_FAILED_AGAIN.format(count=73, since=SINCE, hours=6)
    assert rig.chat.texts == [disagreed(), disagreed(closing=closing)]

    rig.shell.fine.add(CHECK)
    [run] = await rig.tick()

    assert run.status == DONE and rig.failing() is None
    assert rig.chat.texts[2:] == [mended(73)]


async def test_a_job_that_broke_and_then_fails_its_check_is_one_streak_told_in_each_ones_words(
    rig,
):
    rig.shell.fine.clear()
    await rig.tick()
    rig.shell.fine.add("sync-ledger")

    await rig.tick(hours=6)

    since = "07:05 ngày 19/09"
    closing = words.JOB_FAILED_AGAIN.format(count=2, since=since, hours=6)
    assert rig.chat.texts == [first(), disagreed(closing=closing)]
    assert rig.chat.texts[1] != again(2)


async def test_a_job_with_no_check_runs_one_command_and_ends_as_it_did(deps_factory, shell):
    plain = Schedule("sync", NAME, every="5m", command="sync-ledger")
    rig = clocked(deps_factory(), shell, plain)

    [run] = await rig.tick()

    assert (run.status, run.summary, len(run.steps)) == (DONE, "xong", 1)
    assert [command for command, _, _ in shell.calls] == ["sync-ledger"]
    assert rig.chat.asked == []


# --- a job that asks the agent ---


async def test_a_turn_that_said_done_is_sent_on_and_then_told_its_check_disagrees(
    deps_factory, shell
):
    rig, sent = asking(deps_factory, shell, "Đã chép xong sổ.")

    [run] = await rig.tick()

    # The answer went on as the turn left it, before the check ran.
    assert sent == [("Đã chép xong sổ.", DONE)]
    assert run.status == FAILED and run.conversation_id is not None
    assert run.summary == words.JOB_CHECK_SUMMARY.format(reason=WHY)
    assert [kept.status for kept in sched_runs(rig.deps)] == [FAILED]
    assert rig.chat.texts == [disagreed()]
    assert [command for command, _, _ in shell.calls] == [CHECK]
    assert rig.failing()["count"] == 1


async def test_a_turn_whose_check_agrees_is_sent_on_and_nothing_more(deps_factory, shell):
    rig, sent = asking(deps_factory, shell, "Đã chép xong sổ.")
    shell.fine.add(CHECK)

    [run] = await rig.tick()

    assert run.status == DONE and sent == [("Đã chép xong sổ.", DONE)]
    assert rig.chat.asked == [] and rig.failing() is None


async def test_a_turn_whose_check_disagrees_and_then_agrees_gets_the_line_of_a_job_mended(
    deps_factory, shell
):
    rig, sent = asking(deps_factory, shell, "Đã chép xong sổ.", "Đã chép lại.")
    await rig.tick()
    shell.fine.add(CHECK)

    [run] = await rig.tick()

    assert run.status == DONE and len(sent) == 2
    assert rig.chat.texts == [disagreed(), mended(1)]


def test_a_failed_turn_with_no_check_behind_it_is_still_not_told_here(deps_factory, shell):
    """Only a failure of the check's own kind is told of a turn: an ordinary text that says
    why a run failed, beside a run that has a conversation, is no message."""
    deps = with_schedules(deps_factory(), ASKED)
    hub = ActivityHub(deps.store)
    conversation = deps.store.create(title="lượt", agent_id="default")
    run = hub.start("default", "job:" + SYNC, "lượt", conversation.id)
    hub.finish(run, status=FAILED, summary="hỏng")
    [job] = Scheduler({"default": deps}, hub).jobs()

    assert failure_notice(job, run, WHY) is None
    assert failure_notice(job, run, CheckFailed(WHY)) == words.JOB_CHECK_FAILED.format(
        name=NAME, reason=WHY
    )


# --- through the real shell ---


async def test_a_check_runs_in_the_agents_workspace_after_the_command_it_checks(deps_factory):
    made = Schedule(
        "make", "Xuất sổ", every="1h", command="echo 1 > out.csv", check="test -s out.csv"
    )
    lost = Schedule("lose", "Xuất hụt", every="1h", command="true", check="echo thiếu tệp; exit 4")
    deps = with_schedules(deps_factory(), made, lost)
    chat = Chat(Clock())
    sched = Scheduler({"default": deps}, ActivityHub(deps.store), notify=chat)

    well = await sched.run_job("default/make")
    badly = await sched.run_job("default/lose")

    assert well.status == DONE and (Path(deps.agent.workspace) / "out.csv").is_file()
    assert badly.status == FAILED
    why = "Lệnh thoát với mã 4. Dòng cuối lệnh in ra: thiếu tệp"
    [told] = chat.texts
    assert told.startswith(words.JOB_CHECK_FAILED.format(name="Xuất hụt", reason=why))


# --- the key in the file and on the jobs list ---


def row(**more: Any) -> dict[str, Any]:
    return {"schedules": [{"id": "sync", "every": "5m", "command": "sync-ledger", **more}]}


def test_the_key_is_read_from_the_file_for_every_kind_of_row(settings, tmp_path):
    [command] = parse_profile("a", tmp_path, row(check=CHECK), settings).schedules
    asked = {"schedules": [{"id": "ask", "cron": "0 7 * * *", "prompt": "chép", "check": CHECK}]}
    [prompt] = parse_profile("a", tmp_path, asked, settings).schedules
    [none] = parse_profile("a", tmp_path, row(), settings).schedules

    assert (command.check, prompt.check, none.check) == (CHECK, CHECK, None)
    assert command.to_dict()["check"] == CHECK
    # A row that states none shows none: what an editor reads and writes back is unchanged.
    assert "check" not in none.to_dict()


@pytest.mark.parametrize("value", ["", "   ", 7, True, ["test -s a"], {"run": "x"}, 0, False])
def test_a_check_that_is_no_command_is_refused_when_the_file_is_read(settings, tmp_path, value):
    with pytest.raises(ValueError, match="agent a: schedule sync: check must be a non-empty"):
        parse_profile("a", tmp_path, row(check=value), settings)


def test_the_jobs_list_shows_the_check_a_job_states(deps_factory, shell):
    plain = Schedule("plain", "Không kiểm", every="5m", command="sync-ledger")
    rig = clocked(deps_factory(), shell, CHECKED, plain)

    rows = {described["id"]: described for described in rig.sched.describe()}

    assert rows[SYNC]["check"] == CHECK
    assert "check" not in rows["default/plain"]
