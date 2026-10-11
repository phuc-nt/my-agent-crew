"""A script of an agent whose file says `script_calls: gated` calls the tools that change
things too, and each such call is put to the approval gate before it runs: the rules a direct
call meets, in their order. A script waits for nobody, so a call a person would be asked
about ends it, with words that say to make the call directly (`script/gate.py` over
`agent/tool_gate.py`, `script/nested.py`). Which tools such a script may call at all is in
`test_script_gated_scope.py`. Every script here runs in a real child process."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

from my_agent_crew import texts_script as t
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agent.nested_calls import NestedBudget, start_nested_budget
from my_agent_crew.agent.tool_gate import ASK, RUN, verdict
from my_agent_crew.agent.turn_context import set_turn_conversation
from my_agent_crew.script import tool as script_module
from my_agent_crew.script.replies import Answer
from my_agent_crew.script.runner import Outcome
from my_agent_crew.script.scope import SCRIPT_TOOL
from my_agent_crew.script.tool import hand_script, script_tool
from my_agent_crew.store import Conversation
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_kit import TOOL_BLOCKED_BY_HOOK
from my_agent_crew.tools.registry import Tool, ToolError, ToolRegistry
from my_agent_crew.tools.result import ToolResult
from my_agent_crew.tools.schedule_create import build_schedule_create_tool
from my_agent_crew.tools.shell import SHELL_TOOL_NAME
from tests.test_script_batch_run import Pauses, answered, batch, one
from tests.test_script_tool import SCHEMA, Hooks, Reads, halted, play, unfinished

AUTONOMOUS, SUPERVISED, ALWAYS = "autonomous", "supervised", "shell always allowed"
# One agent's three lists: what to ask about, what is routine, what its shell refuses.
LISTS = {
    "shell_ask_patterns": ("--force",),
    "shell_allow_patterns": ("git",),
    "shell_deny_patterns": ("sudo",),
}
# Stands for what a command may hold that no refusal is to repeat.
SECRET = "ghp_bimat123"
PUSH = f"git push --force https://x:{SECRET}@example.com/repo.git"
ASK_LIST, ASKS, DENIED = t.SCRIPT_GATE_ASK_LIST, t.SCRIPT_GATE_ASKS, t.SCRIPT_GATE_DENIED


class Shell:
    """Stands in for `shell_run` under its own name, so the gate reads the agent's lists
    for it as it does for the real one. It runs nothing and keeps the commands it was
    handed, which is how a test knows a refused command never reached it."""

    def __init__(self) -> None:
        self.ran: list[str] = []
        self.tool = Tool(SHELL_TOOL_NAME, "Chạy lệnh.", SCHEMA, self._run, requires_approval=True)

    async def _run(self, arguments: dict[str, Any]) -> str:
        self.ran.append(arguments["command"])
        return f"đã chạy {len(self.ran)}"


def agent(deps_factory, *tools: Tool, **settings: Any) -> tuple[AgentDeps, Shell]:
    """An agent with the three lists, the recording shell and `tools`, handed the script
    tool as the server hands it. Its scripts may change things unless `settings` says not."""
    shell = Shell()
    deps = deps_factory(**{"script_calls": "gated", **LISTS, **settings})
    deps.tools = deps.tools.without(SHELL_TOOL_NAME)
    for tool in (shell.tool, *tools):
        deps.tools.register(tool)
    hand_script(deps)
    return deps, shell


def conversation(deps: AgentDeps, kind: str = AUTONOMOUS) -> Conversation:
    conv = deps.store.create(autonomous=kind == AUTONOMOUS)
    if kind == ALWAYS:
        conv = deps.store.update(conv.id, auto_approve=[SHELL_TOOL_NAME])
    return conv


async def played(
    deps: AgentDeps, conv_id: str, source: str, steps: int = 0
) -> tuple[ToolResult, NestedBudget | None]:
    """The script run as one call of a turn of the conversation, and what the turn's scripts
    had left to call when `steps` gives them a count. The turn is set in a task of its own,
    so nothing of it is left for the next test."""

    async def turn() -> tuple[ToolResult, NestedBudget | None]:
        set_turn_conversation(conv_id)
        budget = start_nested_budget(steps) if steps else None
        return await deps.tools.execute(SCRIPT_TOOL, {"script": dedent(source)}), budget

    return await asyncio.create_task(turn())


async def ran(deps: AgentDeps, conv: Conversation | None, source: str) -> ToolResult:
    result, _ = await played(deps, conv.id if conv else "", source)
    return result


def shelled(command: str) -> str:
    """A script that runs one command, and would carry on if the call only failed."""
    return f"""
        print("trước")
        try:
            print(tools.shell_run(command={command!r}))
        except Exception:
            print("bắt được")
        print("sau")
        """


async def answers_to(monkeypatch, deps: AgentDeps, conv: Conversation, calls) -> list[Answer]:
    """What each call of a batch is answered, as the process a script runs in is told."""
    answers: list[Answer] = []

    async def asking(source, call, **limits):
        answers.extend(await limits["call_many"](calls))
        return Outcome(True, "")

    monkeypatch.setattr(script_module, "run_script", asking)
    await ran(deps, conv, "pass")
    return answers


# --- one call, by the rules a direct call meets ---

RUNS = [
    # Autonomy: nobody is asked to authorise a tool, on the allow list or off it.
    (AUTONOMOUS, "ls -la"),
    (AUTONOMOUS, "git status"),
    # The allow list lets a supervised agent get on with the routine parts of its job.
    (SUPERVISED, "git status"),
    # A tool the person said to always allow in this conversation.
    (ALWAYS, "ls -la"),
]


@pytest.mark.parametrize(("kind", "command"), RUNS)
async def test_a_call_the_gate_would_let_run_unasked_runs_and_is_kept_as_gated(
    deps_factory, kind, command
):
    deps, shell = agent(deps_factory)

    result = await ran(deps, conversation(deps, kind), shelled(command))

    assert (result.ok, result.output) == (True, "trước\nđã chạy 1\nsau")
    assert shell.ran == [command]
    [call] = result.calls
    assert (call.name, call.arguments, call.ok, call.gated) == (
        SHELL_TOOL_NAME,
        {"command": command},
        True,
        True,
    )
    assert call.to_dict()["gated"] is True


HALTS = [
    # Supervised and on no list: a person is asked about a direct call.
    (SUPERVISED, f"ls {SECRET}", ASKS, ""),
    # The ask list holds whatever the conversation allows...
    (AUTONOMOUS, f"rm --force {SECRET}", ASK_LIST, "--force"),
    (ALWAYS, f"rm --force {SECRET}", ASK_LIST, "--force"),
    # ...and beats the allow list: `git` routine and `--force` dangerous means ask.
    (AUTONOMOUS, PUSH, ASK_LIST, "--force"),
    (SUPERVISED, PUSH, ASK_LIST, "--force"),
    # A command the agent's shell refuses is refused before anybody would be asked, and
    # whatever else it matches: no yes would make it run.
    (AUTONOMOUS, f"sudo ls {SECRET}", DENIED, "sudo"),
    (SUPERVISED, f"sudo ls {SECRET}", DENIED, "sudo"),
    (AUTONOMOUS, f"sudo git status {SECRET}", DENIED, "sudo"),
    (AUTONOMOUS, f"sudo rm --force {SECRET}", DENIED, "sudo"),
]


@pytest.mark.parametrize(("kind", "command", "why", "pattern"), HALTS)
async def test_a_call_the_gate_would_not_let_run_unasked_ends_the_script_unrun(
    deps_factory, kind, command, why, pattern
):
    deps, shell = agent(deps_factory)

    result = await ran(deps, conversation(deps, kind), shelled(command))

    # Not a failure the script can catch and carry on from: it ends where it asked.
    reason = why.format(name=SHELL_TOOL_NAME, pattern=pattern)
    assert (result.ok, result.output) == (False, unfinished("trước", halted(4, reason)))
    assert shell.ran == [] and result.calls == ()
    # What the command said is in no word of the refusal, which is kept with the run.
    assert SECRET not in result.output and command not in result.output


def test_a_refusal_says_what_to_do_about_it_and_names_only_the_owners_pattern():
    listed = ASK_LIST.format(name=SHELL_TOOL_NAME, pattern="--force")
    supervised = ASKS.format(name=SHELL_TOOL_NAME)
    denied = DENIED.format(name=SHELL_TOOL_NAME, pattern="sudo")

    # Made directly, the call can wait for a person. One the shell refuses cannot be made.
    for said in (listed, supervised):
        assert "Gọi `shell_run` trực tiếp, ngoài script, để người dùng được hỏi." in said
    assert "trực tiếp" not in denied
    assert "`--force`" in listed and "`sudo`" in denied
    assert len({listed, supervised, denied}) == 3


async def test_a_tools_own_reason_to_ask_is_not_repeated_to_the_script(deps_factory):
    """Its words may quote the call, as the card a person reads does."""
    pays = Reads(
        "pay_send",
        replay_safe=False,
        requires_approval=True,
        ask_reason=lambda arguments: f"chuyển cho {arguments['to']}",
    )
    deps, _ = agent(deps_factory, pays.tool)

    result = await ran(deps, conversation(deps), f"tools.pay_send(to={SECRET!r})")

    # Autonomy does not let it by: its reason outranks every waiver, as for a direct call.
    reason = ASKS.format(name="pay_send")
    assert (result.ok, result.output) == (False, unfinished(halted(1, reason)))
    assert pays.asked == [] and SECRET not in result.output and "chuyển cho" not in result.output


@pytest.mark.parametrize(
    ("kind", "always", "runs"),
    [(AUTONOMOUS, (), True), (SUPERVISED, (), False), (SUPERVISED, ("notes_write",), True)],
)
async def test_a_tool_that_asks_first_follows_the_conversation_and_no_list_of_the_shells(
    deps_factory, kind, always, runs
):
    notes = Reads("notes_write", "đã ghi", replay_safe=False, requires_approval=True)
    deps, _ = agent(deps_factory, notes.tool)
    conv = deps.store.update(conversation(deps, kind).id, auto_approve=list(always))

    # The text matches the allow list, which is the shell's alone.
    result = await ran(deps, conv, 'print(tools.notes_write(text="git status"))')

    if runs:
        assert (result.ok, result.output) == (True, "đã ghi")
        assert notes.asked == [{"text": "git status"}]
        assert [(call.name, call.gated) for call in result.calls] == [("notes_write", True)]
    else:
        reason = ASKS.format(name="notes_write")
        assert (result.ok, result.output) == (False, unfinished(halted(1, reason)))
        assert notes.asked == [] and result.calls == ()


async def test_a_tool_no_person_is_asked_about_runs_as_a_direct_call_of_it_would(deps_factory):
    notes = Reads("notes_write", "đã ghi", replay_safe=False)
    deps, _ = agent(deps_factory, notes.tool)

    result = await ran(deps, conversation(deps, SUPERVISED), "print(tools.notes_write())")

    assert (result.ok, result.output) == (True, "đã ghi")
    assert [(call.name, call.gated) for call in result.calls] == [("notes_write", True)]


async def test_what_the_person_allows_is_read_anew_for_each_call(deps_factory):
    """Autonomy taken back while a script runs holds for the very next call."""
    deps, shell = agent(deps_factory)
    conv = conversation(deps)

    async def take_back(arguments: dict[str, Any]) -> str:
        deps.store.update(conv.id, autonomous=False)
        return "đã thu lại"

    deps.tools.register(Tool("autonomy_off", "Thu lại quyền tự chủ.", SCHEMA, take_back))
    source = """
        tools.shell_run(command="ls")
        print(tools.autonomy_off())
        tools.shell_run(command="ls -la")
        """

    result = await ran(deps, conv, source)

    reason = ASKS.format(name=SHELL_TOOL_NAME)
    assert (result.ok, result.output) == (False, unfinished("đã thu lại", halted(4, reason)))
    # What ran before the script ended is kept all the same.
    assert shell.ran == ["ls"]
    assert [call.name for call in result.calls] == [SHELL_TOOL_NAME, "autonomy_off"]


async def test_a_tool_the_agent_no_longer_holds_is_not_run_on_the_scripts_say_so(deps_factory):
    """A script goes on holding the tools it began with. One the agent has lost meanwhile,
    as a server signed out leaves it, is one the gate knows nothing of, and of such a tool
    it says run: the script is ended there instead."""
    notes = Reads("mcp__notes__write", "đã ghi", requires_approval=True)
    deps, _ = agent(deps_factory, notes.tool)
    conv = conversation(deps)

    async def lose(arguments: dict[str, Any]) -> str:
        deps.tools = deps.tools.without("mcp__notes__write")
        return "đã mất"

    deps.tools.register(Tool("notes_lost", "Làm mất tool ghi.", SCHEMA, lose, replay_safe=True))
    source = """
        print(tools.mcp__notes__write())
        print(tools.notes_lost())
        print(tools.mcp__notes__write())
        """

    result = await ran(deps, conv, source)

    reason = t.SCRIPT_GATE_GONE.format(name="mcp__notes__write")
    assert (result.ok, result.output) == (False, unfinished("đã ghi\nđã mất", halted(4, reason)))
    assert len(notes.asked) == 1


# --- what is never a script's, and what never meets the gate ---


async def test_the_tools_that_always_wait_for_a_person_stay_out_of_a_script(deps_factory):
    deps, _ = agent(deps_factory)
    deps.tools = deps.tools.without(SCRIPT_TOOL)
    deps.tools.register(build_schedule_create_tool(deps.store, "default", (), datetime.now))
    hand_script(deps)
    conv = conversation(deps)

    asked = await ran(deps, conv, 'tools.ask_user(question="A hay B?")')
    planned = await ran(deps, conv, 'tools.schedule_create(name="x", prompt="y", every="1h")')

    for result, name in ((asked, "ask_user"), (planned, "schedule_create")):
        reason = t.SCRIPT_ALWAYS_ASKS.format(name=name, instead=t.SCRIPT_CALL_DIRECTLY)
        assert (result.ok, result.output) == (False, unfinished(halted(1, reason)))
        assert result.calls == ()
    assert deps.store.created_schedules.count("default") == 0
    assert deps.store.approvals.pending(conv.id) is None


async def test_a_script_of_an_agent_left_as_it_was_is_refused_as_before(deps_factory):
    deps, shell = agent(deps_factory, script_calls="read_only")

    result = await ran(deps, conversation(deps), shelled("git status"))

    # Autonomous and on the allow list, which a direct call needs no more than: the gate
    # is not what refuses here.
    reason = t.SCRIPT_ASKS_FIRST.format(name=SHELL_TOOL_NAME, instead=t.SCRIPT_CALL_DIRECTLY)
    assert (result.ok, result.output) == (False, unfinished("trước", halted(4, reason)))
    assert shell.ran == [] and result.calls == ()


async def test_a_call_that_only_reads_is_not_put_to_the_gate():
    rows, notes = Reads("rows_read"), Reads("notes_write", replay_safe=False)
    put: list[tuple[str, dict[str, Any]]] = []

    def gate(name: str, arguments: dict[str, Any]) -> None:
        put.append((name, arguments))

    registry = ToolRegistry([rows.tool, notes.tool])
    registry.register(script_tool(lambda: registry, [], gate))

    result = await play(
        registry,
        f"""
        tools.rows_read(page=1)
        tools.notes_write(text="x")
        tools.batch([{one("rows_read", page=2)}, {one("rows_read", page=3)}])
        """,
    )

    assert result.ok and put == [("notes_write", {"text": "x"})]
    assert [(call.name, call.gated) for call in result.calls] == [
        ("rows_read", False),
        ("notes_write", True),
        ("rows_read", False),
        ("rows_read", False),
    ]
    # A call that only read is kept as one was before a script could do more.
    assert ["gated" in call.to_dict() for call in result.calls] == [False, True, False, False]


@pytest.mark.parametrize("turn", ["", "no-such-conversation"], ids=["no turn", "one unknown"])
async def test_with_no_conversation_to_go_by_a_call_that_changes_things_is_refused(
    deps_factory, turn
):
    rows = Reads("rows_read", "ba dòng")
    deps, shell = agent(deps_factory, rows.tool)
    source = """
        print(tools.rows_read())
        tools.shell_run(command="git status")
        """

    result, _ = await played(deps, turn, source)

    # Reading needs nobody's leave. A command does, and there is nobody's to read.
    reason = t.SCRIPT_GATE_NO_TURN.format(name=SHELL_TOOL_NAME)
    assert (result.ok, result.output) == (False, unfinished("ba dòng", halted(3, reason)))
    assert shell.ran == [] and [call.name for call in result.calls] == ["rows_read"]


# --- what a call the gate let run goes through ---


async def test_a_call_that_ran_and_failed_is_the_scripts_to_catch(deps_factory):
    notes = Reads("notes_write", ToolError("đĩa đầy"), replay_safe=False)
    deps, _ = agent(deps_factory, notes.tool)
    source = """
        try:
            tools.notes_write(text="x")
        except Exception as e:
            print("lỗi:", e)
        """

    result = await ran(deps, conversation(deps), source)

    failed = TOOL_FAILED.format(error="đĩa đầy")
    assert (result.ok, result.output) == (True, f"lỗi: {failed}")
    assert [(c.name, c.ok, c.output, c.gated) for c in result.calls] == [
        ("notes_write", False, failed, True)
    ]


async def test_the_agents_hooks_are_asked_about_a_call_the_gate_let_run():
    notes = Reads("notes_write", "đã ghi", replay_safe=False)
    locked = Reads("locked_write", replay_safe=False)
    hooks = Hooks(blocked=("locked_write",), noted=("notes_write",))
    registry = ToolRegistry([notes.tool, locked.tool], hooks=hooks)
    registry.register(script_tool(lambda: registry, [], lambda name, arguments: None))

    result = await play(
        registry,
        """
        print(tools.notes_write(text="x"))
        try:
            tools.locked_write()
        except Exception as e:
            print("bị chặn:", e)
        """,
    )

    blocked = TOOL_BLOCKED_BY_HOOK.format(name="locked_write", reason="không phải lúc")
    assert (result.ok, result.output) == (True, f"đã ghi [đã ghi sổ]\nbị chặn: {blocked}")
    assert notes.asked == [{"text": "x"}] and locked.asked == []
    assert hooks.asked == [
        ("before", SCRIPT_TOOL),
        ("before", "notes_write"),
        ("after", "notes_write"),
        ("before", "locked_write"),
        ("after", SCRIPT_TOOL),
    ]


async def test_a_refused_call_takes_nothing_from_what_the_turns_scripts_may_call(deps_factory):
    rows = Reads("rows_read")
    deps, shell = agent(deps_factory, rows.tool)
    conv = conversation(deps)
    refused = batch(one("rows_read"), one(SHELL_TOOL_NAME, command=PUSH))
    made = batch(one("rows_read"), one(SHELL_TOOL_NAME, command="git status"))

    halted_at, left = await played(deps, conv.id, refused, steps=1)
    assert not halted_at.ok and left is not None and (left.used, left.spent) == (0, False)

    result, counted = await played(deps, conv.id, made, steps=1)
    assert result.ok and counted is not None and (counted.used, counted.spent) == (2, False)
    assert shell.ran == ["git status"]


# --- batches ---


async def test_a_batch_with_one_call_the_gate_refuses_makes_none_of_its_calls(deps_factory):
    rows = Reads("rows_read")
    deps, shell = agent(deps_factory, rows.tool)
    calls = (
        one(SHELL_TOOL_NAME, command="git status"),
        one("rows_read"),
        one(SHELL_TOOL_NAME, command=PUSH),
    )
    source = f"""
        print("trước")
        try:
            tools.batch([{", ".join(calls)}])
        except Exception:
            print("bắt được")
        print("sau")
        """

    result = await ran(deps, conversation(deps), source)

    reason = ASK_LIST.format(name=SHELL_TOOL_NAME, pattern="--force")
    assert (result.ok, result.output) == (False, unfinished("trước", halted(4, reason)))
    # The command written first would have run alone. In this batch it did not.
    assert (shell.ran, rows.asked, result.calls) == ([], [], ())
    assert SECRET not in result.output


async def test_each_call_of_a_refused_batch_is_answered_the_refused_ones_with_why(
    monkeypatch, deps_factory
):
    rows = Reads("rows_read")
    deps, shell = agent(deps_factory, rows.tool)
    calls = [
        (SHELL_TOOL_NAME, {"command": PUSH}),
        (SHELL_TOOL_NAME, {"command": "git status"}),
        ("rows_read", {}),
        (SHELL_TOOL_NAME, {"command": "sudo ls"}),
    ]

    answers = await answers_to(monkeypatch, deps, conversation(deps), calls)

    skipped = Answer(False, t.SCRIPT_BATCH_NOT_RUN)
    assert answers == [
        Answer(False, ASK_LIST.format(name=SHELL_TOOL_NAME, pattern="--force"), halt=True),
        skipped,
        skipped,
        Answer(False, DENIED.format(name=SHELL_TOOL_NAME, pattern="sudo"), halt=True),
    ]
    assert (shell.ran, rows.asked) == ([], [])


async def test_a_batch_with_a_call_that_changes_things_is_made_one_call_at_a_time_as_written(
    deps_factory,
):
    """Written slowest first: side by side the calls would end in another order, and be in
    the middle of one another."""
    pauses = Pauses()
    slow = replace(pauses.tool("slow_write", 0.3, "chậm"), replay_safe=False)
    middle = replace(pauses.tool("mid_write", 0.15, "vừa"), replay_safe=False)
    quick = pauses.tool("quick_read", 0.0, "nhanh")
    deps, _ = agent(deps_factory, slow, middle, quick)
    written = ["slow_write", "quick_read", "mid_write", "quick_read"]

    result = await ran(deps, conversation(deps), batch(*(one(name) for name in written)))

    assert (pauses.peak, pauses.ended) == (1, written)
    assert [answer["output"] for answer in answered(result)] == ["chậm", "nhanh", "vừa", "nhanh"]
    assert [(call.name, call.gated) for call in result.calls] == [
        ("slow_write", True),
        ("quick_read", False),
        ("mid_write", True),
        ("quick_read", False),
    ]


async def test_a_batch_whose_calls_all_only_read_is_still_made_side_by_side(deps_factory):
    """The same tools and the same waits, with nothing among them that changes things."""
    pauses = Pauses()
    slow, middle = pauses.tool("slow_read", 0.3), pauses.tool("mid_read", 0.15)
    quick = pauses.tool("quick_read", 0.0)
    deps, _ = agent(deps_factory, slow, middle, quick)

    result = await ran(
        deps, conversation(deps), batch(one("slow_read"), one("quick_read"), one("mid_read"))
    )

    assert len(answered(result)) == 3
    assert (pauses.peak, pauses.ended) == (3, ["quick_read", "mid_read", "slow_read"])


async def test_the_commands_of_a_batch_run_in_the_order_written_each_answered_on_its_own(
    deps_factory,
):
    broken = Reads("notes_write", ToolError("đĩa đầy"), replay_safe=False)
    deps, shell = agent(deps_factory, broken.tool)
    commands = ["git fetch", "git merge", "git tag v1"]
    first, second, third = (one(SHELL_TOOL_NAME, command=command) for command in commands)

    result = await ran(
        deps,
        conversation(deps, SUPERVISED),
        batch(first, one("notes_write"), second, one("nowhere"), third),
    )

    # One that failed, and a name that is no tool's, keep none of the others from running.
    assert shell.ran == commands
    assert answered(result) == [
        {"ok": True, "output": "đã chạy 1"},
        {"ok": False, "error": TOOL_FAILED.format(error="đĩa đầy")},
        {"ok": True, "output": "đã chạy 2"},
        {"ok": False, "error": t.SCRIPT_UNKNOWN_TOOL.format(name="nowhere", near="")},
        {"ok": True, "output": "đã chạy 3"},
    ]
    assert [(call.name, call.ok) for call in result.calls] == [
        (SHELL_TOOL_NAME, True),
        ("notes_write", False),
        (SHELL_TOOL_NAME, True),
        (SHELL_TOOL_NAME, True),
    ]


async def test_each_call_of_a_batch_that_changes_things_is_judged_again_as_its_turn_comes(
    deps_factory,
):
    """Autonomy taken back by the second call of a batch holds for the third, as it does for
    calls written one after another: what ran is kept, and nothing runs after."""
    rows = Reads("rows_read")
    deps, shell = agent(deps_factory, rows.tool)
    conv = conversation(deps)

    async def take_back(arguments: dict[str, Any]) -> str:
        deps.store.update(conv.id, autonomous=False)
        return "đã thu lại"

    deps.tools.register(Tool("autonomy_off", "Thu lại quyền tự chủ.", SCHEMA, take_back))
    calls = (
        one(SHELL_TOOL_NAME, command="ls"),
        one("autonomy_off"),
        one(SHELL_TOOL_NAME, command="ls -la"),
        one("rows_read"),
    )
    source = f"""
        print("trước")
        try:
            tools.batch([{", ".join(calls)}])
        except Exception:
            print("bắt được")
        print("sau")
        """

    result = await ran(deps, conv, source)

    reason = ASKS.format(name=SHELL_TOOL_NAME)
    assert (result.ok, result.output) == (False, unfinished("trước", halted(4, reason)))
    assert (shell.ran, rows.asked) == (["ls"], [])
    assert [call.name for call in result.calls] == [SHELL_TOOL_NAME, "autonomy_off"]


async def test_a_call_refused_as_its_turn_comes_is_answered_with_why_and_the_rest_as_not_made(
    monkeypatch, deps_factory
):
    rows = Reads("rows_read")
    deps, shell = agent(deps_factory, rows.tool)
    conv = conversation(deps)

    async def take_back(arguments: dict[str, Any]) -> str:
        deps.store.update(conv.id, autonomous=False)
        return "đã thu lại"

    deps.tools.register(Tool("autonomy_off", "Thu lại quyền tự chủ.", SCHEMA, take_back))
    calls = [
        (SHELL_TOOL_NAME, {"command": "ls"}),
        ("autonomy_off", {}),
        (SHELL_TOOL_NAME, {"command": "ls -la"}),
        ("rows_read", {}),
        (SHELL_TOOL_NAME, {"command": "git status"}),
    ]

    answers = await answers_to(monkeypatch, deps, conv, calls)

    skipped = Answer(False, t.SCRIPT_BATCH_NOT_RUN)
    assert answers == [
        Answer(True, "đã chạy 1"),
        Answer(True, "đã thu lại"),
        Answer(False, ASKS.format(name=SHELL_TOOL_NAME), halt=True),
        skipped,
        # Routine by the agent's own list, and still not made: the script ended above.
        skipped,
    ]
    assert (shell.ran, rows.asked) == (["ls"], [])


async def test_what_a_call_of_a_batch_left_behind_is_there_when_the_next_is_judged(
    deps_factory, tmp_path
):
    """A command on the ask list is let run unasked when all it touches is under the temp
    directory. The call before it makes the path it names a link to somewhere else: judged
    with the batch it would be let run, and judged as its turn comes it is not."""
    elsewhere = Path.home()  # outside every temp directory, and only ever pointed at
    deps, shell = agent(deps_factory, shell_ask_patterns=("rm -rf",), shell_allow_patterns=())
    link = tmp_path / "x"
    delete = f"rm -rf {link}/sub"
    lists = dict(deps=deps, name=SHELL_TOOL_NAME)

    async def linked(arguments: dict[str, Any]) -> str:
        link.symlink_to(elsewhere)  # what the command of that call would have done
        return "đã nối"

    deps.tools.register(Tool("link_make", "Nối đường dẫn.", SCHEMA, linked))
    conv = conversation(deps)
    assert verdict(conv=conv, arguments={"command": delete}, **lists) == RUN

    result = await ran(deps, conv, batch(one("link_make"), one(SHELL_TOOL_NAME, command=delete)))

    assert verdict(conv=conv, arguments={"command": delete}, **lists) == ASK
    reason = ASK_LIST.format(name=SHELL_TOOL_NAME, pattern="rm -rf")
    assert (result.ok, result.output) == (False, unfinished(halted(1, reason)))
    assert shell.ran == [] and [call.name for call in result.calls] == ["link_make"]
