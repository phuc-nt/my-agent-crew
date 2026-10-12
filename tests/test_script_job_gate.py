"""What the script of a schedule may call unasked, and what it reads of the turns around it.

Nobody watches a job. Its script is put to the approval gate as the turn a job opens is: a
tool nobody would be asked to authorise there runs, and a call a person is asked about
whoever watches (the agent's ask list, a tool's own reason) ends the script, as does a
command the agent's shell refuses. Nothing waits, and no conversation is made up to wait in
(`script/gate.py`). A script is no turn either: jobs run one after another in one task, where
the turn before left its conversation, its call id and its count of calls behind, and the
script reads none of them and leaves what it found (`scheduler/script_job.py`). The run a
script job comes to is in `test_script_job.py`. Every script here runs in a real child
process.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from textwrap import dedent
from typing import Any

import pytest

from my_agent_crew import texts_script as t
from my_agent_crew.activity import ActivityHub
from my_agent_crew.activity.step_previews import failure_preview
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agent.nested_calls import (
    NestedBudget,
    nested_budget,
    note_nested_call,
    set_nested_sink,
    start_nested_budget,
)
from my_agent_crew.agent.turn_context import (
    JOB,
    TELEGRAM,
    canvas_writes,
    note_canvas_write,
    set_tool_call_id,
    set_turn_conversation,
    set_turn_source,
    tool_call_id,
    turn_conversation_id,
    turn_depth,
    turn_source,
)
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.scheduler import Scheduler
from my_agent_crew.store.runs import DONE, FAILED
from my_agent_crew.tools.registry import Tool
from my_agent_crew.tools.result import NestedCall
from my_agent_crew.tools.shell import SHELL_TOOL_NAME
from tests.test_scheduler import with_schedules
from tests.test_script_gate import (
    ASK_LIST,
    ASKS,
    DENIED,
    PUSH,
    SECRET,
    agent,
    conversation,
    ran,
    shelled,
)
from tests.test_script_tool import SCHEMA, Reads, halted, unfinished

MORNING = datetime(2026, 9, 19, 7, 0)
DUE, ASK = "default/due", "default/ask"

Where = tuple[str, str, int, str, NestedBudget | None]


def scheduled(deps: AgentDeps, source: str, *also: Schedule) -> Scheduler:
    """The agent's clock, with the script as its schedule `due` beside its others."""
    due = Schedule("due", "Nhắc hạn", cron="0 7 * * *", script=dedent(source).strip())
    with_schedules(deps, due, *also)
    return Scheduler({"default": deps}, ActivityHub(deps.store), clock=lambda: MORNING)


# --- the gate, with nobody watching ---


@pytest.mark.parametrize("command", ["ls -la", "git status"])
async def test_a_command_nobody_is_asked_about_in_a_job_runs(deps_factory, command):
    """On the allow list or off it: a supervised turn's script is ended for the first."""
    deps, shell = agent(deps_factory)
    sched = scheduled(deps, shelled(command))

    run = await sched.run_job(DUE)

    assert (run.status, run.summary) == (DONE, "trước\nđã chạy 1\nsau")
    assert shell.ran == [command]
    [call] = run.steps[0]["calls"]
    assert (call["name"], call["arguments"], call["ok"], call["gated"]) == (
        SHELL_TOOL_NAME,
        {"command": command},
        True,
        True,
    )


HALTS = [
    # The ask list holds though nobody is there to be asked, and beats the allow list.
    (f"rm --force {SECRET}", ASK_LIST, "--force"),
    (PUSH, ASK_LIST, "--force"),
    # A command the agent's shell refuses, whatever else it matches.
    (f"sudo ls {SECRET}", DENIED, "sudo"),
    (f"sudo rm --force {SECRET}", DENIED, "sudo"),
]


@pytest.mark.parametrize(("command", "why", "pattern"), HALTS)
async def test_a_command_the_gate_would_not_let_run_unasked_ends_the_jobs_script_unrun(
    deps_factory, command, why, pattern
):
    deps, shell = agent(deps_factory)
    sched = scheduled(deps, shelled(command))

    run = await sched.run_job(DUE)

    # Not a failure the script catches and carries on from: it ends where it asked.
    said = unfinished("trước", halted(3, why.format(name=SHELL_TOOL_NAME, pattern=pattern)))
    [step] = run.steps
    # Kept whole, to the last sentence, which says what to do about it.
    assert (run.status, step["ok"], step["output"]) == (FAILED, False, failure_preview(said))
    assert step["output"] == said.replace("\n", " ")
    assert run.summary and said.endswith(run.summary)
    assert shell.ran == [] and not step.get("calls")
    # Nothing waits: there is no conversation for a yes to arrive in.
    assert run.conversation_id is None and deps.store.list() == []
    # What the command said is in no word of the refusal.
    assert SECRET not in step["output"] and SECRET not in run.summary


async def test_a_tools_own_reason_to_ask_ends_the_jobs_script_and_is_not_repeated(deps_factory):
    pays = Reads(
        "pay_send",
        replay_safe=False,
        requires_approval=True,
        ask_reason=lambda arguments: f"chuyển cho {arguments['to']}",
    )
    deps, _ = agent(deps_factory, pays.tool)
    sched = scheduled(deps, f"tools.pay_send(to={SECRET!r})")

    run = await sched.run_job(DUE)

    # Nobody watching does not let it by: its reason outranks that, as for a direct call.
    said = unfinished(halted(1, ASKS.format(name="pay_send")))
    assert (run.status, run.steps[0]["output"]) == (FAILED, failure_preview(said))
    assert pays.asked == [] and "chuyển cho" not in run.steps[0]["output"] + run.summary


async def test_a_tool_that_asks_first_runs_in_a_job_as_in_the_turn_a_job_opens(deps_factory):
    notes = Reads("notes_write", "đã ghi", replay_safe=False, requires_approval=True)
    deps, _ = agent(deps_factory, notes.tool)
    sched = scheduled(deps, 'print(tools.notes_write(text="nhắc hạn"))')

    run = await sched.run_job(DUE)

    assert (run.status, run.summary) == (DONE, "đã ghi")
    assert notes.asked == [{"text": "nhắc hạn"}]


async def test_the_job_of_an_agent_whose_scripts_only_read_is_refused_what_its_turn_is(
    deps_factory,
):
    deps, shell = agent(deps_factory, script_calls="read_only")
    source = dedent(shelled("ls -la")).strip()
    sched = scheduled(deps, source)

    run = await sched.run_job(DUE)
    in_turn = await ran(deps, conversation(deps), source)

    reason = t.SCRIPT_ASKS_FIRST.format(name=SHELL_TOOL_NAME, instead="gọi trực tiếp")
    said = unfinished("trước", halted(3, reason))
    assert (in_turn.ok, in_turn.output) == (False, said)
    assert (run.status, run.steps[0]["output"]) == (FAILED, failure_preview(said))
    assert shell.ran == []


# --- between the turns of other jobs ---


def where() -> Where:
    """What a tool reads of the turn it is called in."""
    return turn_source(), turn_conversation_id(), turn_depth(), tool_call_id(), nested_budget()


class Looks:
    """A tool that only reads, and keeps where each call of it found itself."""

    def __init__(self) -> None:
        self.seen: list[Where] = []
        self.tool = Tool("where_read", "Đọc.", SCHEMA, self._run, replay_safe=True)

    async def _run(self, arguments: dict[str, Any]) -> str:
        self.seen.append(where())
        return "đã nhìn"


def two_jobs(deps_factory) -> tuple[AgentDeps, Scheduler, Looks]:
    """An agent with a job that asks the model, which calls the tool, and one that runs a
    script, which calls it too."""
    looks = Looks()
    asks = completion(tool_calls=(ToolCall("p1", "where_read", {}),))
    model = ScriptedProvider([asks, completion("Xong.")])
    deps = deps_factory(providers={"scripted": model}, extra_tools=[looks.tool])
    by_model = Schedule("ask", "Hỏi", cron="0 7 * * *", prompt="nhìn đi")
    return deps, scheduled(deps, 'tools.where_read()\nprint("CỦA SCRIPT")', by_model), looks


def said(deps: AgentDeps, conv_id: str) -> list[tuple[str, str]]:
    return [(m.message.role, m.message.content) for m in deps.store.history(conv_id)]


async def test_a_script_job_reads_nothing_of_the_turn_the_job_before_it_left(deps_factory):
    deps, sched, looks = two_jobs(deps_factory)

    async def one_after_the_other():
        turn = await sched.run_job(ASK)
        return turn, said(deps, turn.conversation_id), await sched.run_job(DUE)

    # In one task, as the clock runs the jobs that are due.
    turn, before, alone = await asyncio.create_task(one_after_the_other())

    in_turn, in_script = looks.seen
    assert in_turn[:4] == (JOB, turn.conversation_id, 0, "p1") and in_turn[4] is not None
    # A job's work, in no conversation, under a call id of its own, counted against no turn.
    assert in_script == (JOB, "", 0, f"job-{alone.id}", None)
    # And so nothing of it could land in the conversation of the turn before.
    assert (alone.status, alone.conversation_id) == (DONE, None)
    assert said(deps, turn.conversation_id) == before
    assert all("CỦA SCRIPT" not in content for _, content in before)
    assert [conv.id for conv in deps.store.list()] == [turn.conversation_id]


async def test_the_turn_of_the_job_after_a_script_job_is_its_own(deps_factory):
    deps, sched, looks = two_jobs(deps_factory)

    async def one_after_the_other():
        return await sched.run_job(DUE), await sched.run_job(ASK)

    alone, turn = await asyncio.create_task(one_after_the_other())

    in_script, in_turn = looks.seen
    assert in_script == (JOB, "", 0, f"job-{alone.id}", None)
    assert in_turn[:4] == (JOB, turn.conversation_id, 0, "p1")
    # Its scripts have a count of their own, and the script before took nothing from it.
    assert in_turn[4] is not None and (in_turn[4].used, in_turn[4].spent) == (0, False)
    assert alone.conversation_id is None
    assert all("CỦA SCRIPT" not in content for _, content in said(deps, turn.conversation_id))


@pytest.mark.parametrize("last_line", ['print("xong")', "print(nowhere_named)"])
async def test_a_script_job_leaves_what_the_task_went_by_as_it_found_it(deps_factory, last_line):
    """However it ended. Each value is one no job sets, so none is there by chance."""
    looks = Looks()
    deps = deps_factory(extra_tools=[looks.tool])
    sched = scheduled(deps, f"tools.where_read()\n{last_line}")
    told: list[NestedCall] = []
    mine = NestedCall("notes_read", {}, True, "của lượt trước", 1)

    async def amid_another_turn():
        set_turn_source(TELEGRAM)
        set_turn_conversation("conv-before", depth=2)
        set_tool_call_id("call-before")
        note_canvas_write("canvas-before")
        set_nested_sink(told.append)
        budget = start_nested_budget(3)
        run = await sched.run_job(DUE)
        heard = list(told)
        note_nested_call(mine)
        return run, budget, where(), canvas_writes("canvas-before"), heard

    run, budget, after, written, heard = await asyncio.create_task(amid_another_turn())

    assert looks.seen == [(JOB, "", 0, f"job-{run.id}", None)]
    assert after[:4] == (TELEGRAM, "conv-before", 2, "call-before") and after[4] is budget
    # Its call was counted against no turn and told to its own run alone...
    assert (budget.used, budget.spent, heard, written) == (0, False, [], 1)
    assert [call["name"] for call in run.steps[0]["calls"]] == ["where_read"]
    # ...and a call made after it is told where calls were told before it.
    assert told == [mine]
