"""A schedule's `check`: the command that says whether a job did what it was for
(`scheduler/check.py`).

A job that ended well and states a check has the check run after it, as a command job's
command is run. A check that leaves with 0 changes nothing. One that leaves with anything
else, or runs past its limit, makes the run a failed one, summed up in words that say the
job ended well and the check disagreed, and counted into the job's failures in a row as any
failed job is. A job that states none runs as it always did.

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
from my_agent_crew.store.runs import DONE, FAILED
from tests.test_job_failure_streaks import NAME, SYNC, Clock, Rig, Shell, clocked, stamps
from tests.test_scheduler import with_schedules

CHECK = "test -s ledger.csv"
CHECKED = Schedule("sync", NAME, every="5m", command="sync-ledger", check=CHECK)
ASKED = Schedule("sync", NAME, every="5m", prompt="chép sổ", check=CHECK)
# Why `Shell`'s failing command failed, as a failed check's run is summed up by.
WHY = "Lệnh thoát với mã 3. Dòng cuối lệnh in ra: không vào được sổ"


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


def asking(deps_factory, shell: Shells, *replies: str) -> Rig:
    """A prompt job the model answers, with its check."""
    deps = deps_factory(script=[completion(reply) for reply in replies])
    with_schedules(deps, ASKED)
    clock = Clock()
    sched = Scheduler({"default": deps}, ActivityHub(deps.store), clock=clock)
    return Rig(sched, clock, shell, deps)


def answer_of(rig: Rig, conversation_id: str) -> str:
    return rig.deps.store.history(conversation_id)[-1].message.content


def sched_runs(deps):
    return deps.store.runs.recent(10)


# --- a command job ---


async def test_a_check_that_agrees_leaves_the_run_done(rig):
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
    assert rig.failing() is None


async def test_a_check_that_disagrees_fails_the_run_and_says_the_job_itself_ended_well(rig):
    [run] = await rig.tick()

    assert run.status == FAILED and run.conversation_id is None
    assert run.summary == words.JOB_CHECK_SUMMARY.format(reason=WHY)
    assert [step["ok"] for step in run.steps] == [True, False]
    [kept] = sched_runs(rig.deps)
    assert (kept.id, kept.status, kept.summary) == (run.id, FAILED, run.summary)
    assert rig.failing() == stamps("07:05")


async def test_a_check_stopped_at_its_limit_is_summed_up_as_one_that_ran_too_long(rig):
    rig.shell.result = (None, "")

    [run] = await rig.tick()

    assert run.status == FAILED
    limit = texts.SHELL_TIMEOUT.format(seconds=jobs.COMMAND_TIMEOUT_SECONDS)
    assert run.summary == words.JOB_CHECK_SUMMARY.format(reason=limit)


async def test_a_job_that_failed_is_not_checked(rig):
    rig.shell.fine.clear()

    [run] = await rig.tick()

    assert run.status == FAILED and run.summary != words.JOB_CHECK_SUMMARY.format(reason=WHY)
    assert [command for command, _, _ in rig.shell.calls] == ["sync-ledger"]
    assert rig.failing() == stamps("07:05")


async def test_a_check_that_keeps_disagreeing_is_counted_until_it_agrees(rig):
    for _ in range(73):
        await rig.tick()
    assert rig.failing() == stamps("07:05", count=73)

    rig.shell.fine.add(CHECK)
    [run] = await rig.tick()

    assert run.status == DONE and rig.failing() is None


async def test_a_job_that_broke_and_then_fails_its_check_is_one_streak(rig):
    rig.shell.fine.clear()
    await rig.tick()
    rig.shell.fine.add("sync-ledger")

    await rig.tick(hours=6)

    assert rig.failing() == stamps("07:05", count=2)


async def test_a_job_with_no_check_runs_one_command_and_ends_as_it_did(deps_factory, shell):
    plain = Schedule("sync", NAME, every="5m", command="sync-ledger")
    rig = clocked(deps_factory(), shell, plain)

    [run] = await rig.tick()

    assert (run.status, run.summary, len(run.steps)) == (DONE, "xong", 1)
    assert [command for command, _, _ in shell.calls] == ["sync-ledger"]
    assert rig.failing() is None


# --- a job that asks the agent ---


async def test_a_turn_that_said_done_keeps_its_answer_and_its_check_fails_the_run(
    deps_factory, shell
):
    rig = asking(deps_factory, shell, "Đã chép xong sổ.")

    [run] = await rig.tick()

    # The answer stays in the conversation as the turn left it; the run says the check
    # disagreed, and is counted, turn or no turn.
    assert run.status == FAILED and run.conversation_id is not None
    assert answer_of(rig, run.conversation_id) == "Đã chép xong sổ."
    assert run.summary == words.JOB_CHECK_SUMMARY.format(reason=WHY)
    assert [kept.status for kept in sched_runs(rig.deps)] == [FAILED]
    assert [command for command, _, _ in shell.calls] == [CHECK]
    assert rig.failing() == stamps("07:05")


async def test_a_turn_whose_check_agrees_is_done_and_nothing_more(deps_factory, shell):
    rig = asking(deps_factory, shell, "Đã chép xong sổ.")
    shell.fine.add(CHECK)

    [run] = await rig.tick()

    assert run.status == DONE and answer_of(rig, run.conversation_id) == "Đã chép xong sổ."
    assert rig.failing() is None


async def test_a_turn_whose_check_disagrees_and_then_agrees_closes_the_count(deps_factory, shell):
    rig = asking(deps_factory, shell, "Đã chép xong sổ.", "Đã chép lại.")
    await rig.tick()
    assert rig.failing() == stamps("07:05")
    shell.fine.add(CHECK)

    [run] = await rig.tick()

    assert run.status == DONE and rig.failing() is None


# --- through the real shell ---


async def test_a_check_runs_in_the_agents_workspace_after_the_command_it_checks(deps_factory):
    made = Schedule(
        "make", "Xuất sổ", every="1h", command="echo 1 > out.csv", check="test -s out.csv"
    )
    lost = Schedule("lose", "Xuất hụt", every="1h", command="true", check="echo thiếu tệp; exit 4")
    deps = with_schedules(deps_factory(), made, lost)
    sched = Scheduler({"default": deps}, ActivityHub(deps.store))

    well = await sched.run_job("default/make")
    badly = await sched.run_job("default/lose")

    assert well.status == DONE and (Path(deps.agent.workspace) / "out.csv").is_file()
    assert badly.status == FAILED
    why = "Lệnh thoát với mã 4. Dòng cuối lệnh in ra: thiếu tệp"
    assert badly.summary == words.JOB_CHECK_SUMMARY.format(reason=why)


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
