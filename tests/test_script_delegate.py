"""A task handed to another agent from a script: `tools.delegate` (`script/delegation.py`
over `tools/delegate.py`).

Only the script of an agent that changes things hands one on, and only in a turn of the
agent's own. Each such call opens a conversation under an id of its own, which the same
script run again finds; a few are handed on side by side; and what the conversations spent
is on the script's result, once. How many are handed on at the same moment and how long such
a script is given are in `test_script_limits.py`; who else reads the conversations a script
opened is in `test_store.py`, `test_tools_delegate.py`, `test_trajectory.py` and
`test_server_agents_activity_jobs.py`. Every script here runs in a real child process."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from textwrap import dedent
from typing import Any

import pytest

from my_agent_crew import texts
from my_agent_crew import texts_script as t
from my_agent_crew import texts_script_delegate as words
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.turn_context import (
    calling_as,
    job_context,
    set_tool_call_id,
    set_turn_conversation,
    tool_call_id,
)
from my_agent_crew.config import SCRIPT_GATED, SCRIPT_READ_ONLY, Route
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.script.limits import RAW_LIMIT
from my_agent_crew.script.scope import SCRIPT_TOOL
from my_agent_crew.script.tool import script_tool
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store import Store
from my_agent_crew.store.runs import DONE
from my_agent_crew.tools.delegate import DELEGATE_TOOL_NAME, MAX_DELEGATES
from my_agent_crew.tools.output_read import build_output_read_tool
from my_agent_crew.tools.output_spill import Spill
from my_agent_crew.tools.registry import Tool, ToolRegistry
from my_agent_crew.tools.result import NestedCall, ToolResult
from tests.conftest import collect
from tests.queue_helpers import GatedProvider, Served, settle_loop, until
from tests.restart_helpers import history, stored_run
from tests.test_mcp_turns import say
from tests.test_script_batch_run import answered, batch, one
from tests.test_script_gated_turns import KEPT, an_app, left_to_itself, stored_calls, working
from tests.test_script_kept_answer import told
from tests.test_script_tool import Reads, halted, unfinished
from tests.test_script_turns import the_result, the_step
from tests.test_tools_delegate import agent, wait_until_paused

ROW = {"type": "object", "properties": {"row": {"type": "integer"}}}
TASK = {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]}
# What a script is told of a tool kept from scripts, `delegate` among them where it is.
NOT_A_SCRIPTS = t.SCRIPT_NOT_FROM_SCRIPT.format(
    name=DELEGATE_TOOL_NAME, instead=t.SCRIPT_CALL_DIRECTLY
)
# Line 2 reads, so the two tasks are the script's second call and its third.
TWO = """
    print(tools.row_read(row=1))
    print(tools.delegate(task="việc một", agent="worker"))
    print(tools.delegate(task="việc hai"))
    """
# Would carry on past a call that only failed.
HANDS_ON = """
    print("trước")
    try:
        tools.delegate(task="việc", agent="worker")
    except Exception:
        print("bắt được")
    print("sau")
    """


def row_tool() -> Tool:
    async def row_read(arguments: dict[str, Any]) -> str:
        return f"dòng {arguments.get('row', 0)}"

    return Tool("row_read", "Đọc một dòng.", ROW, row_read, replay_safe=True)


def a_crew(deps_factory, store: Store, provider: Any = None, **settings: Any) -> Runtime:
    """A boss that may hand a task to `worker` or to itself, holding a tool that reads. Its
    scripts change things unless `settings` says not. Both agents answer through
    `provider`, or echo the task they were handed."""
    own = {"script_calls": SCRIPT_GATED, **settings}
    if provider is None:
        own["routes"] = (Route("fake", "echo"),)
    providers = None if provider is None else {"scripted": provider}
    base = deps_factory(providers=providers, extra_tools=[row_tool()], **own)
    agents = {"boss": agent(base, "boss", delegates=("worker",)), "worker": agent(base, "worker")}
    crew = Runtime(base.settings, store, agents, ActivityHub(store))
    crew.wire_delegation()
    return crew


async def played(
    tools: ToolRegistry, conv_id: str, source: str, call_id: str = "p1", depth: int = 0
) -> ToolResult:
    """The script as one call of a turn: in the conversation, under the id of the model's
    call, `depth` away from the person. The turn is set in a task of its own, so nothing of
    it is left for the next test."""

    async def turn() -> ToolResult:
        set_turn_conversation(conv_id, depth)
        set_tool_call_id(call_id)
        return await tools.execute(SCRIPT_TOOL, {"script": dedent(source)})

    return await asyncio.create_task(turn())


def opened(store: Store, call_id: str = "p1") -> list[str]:
    """The conversations the script run by this call opened, oldest first."""
    return [child.id for child in store.children_of((), (call_id,))]


class Handed:
    """Stands in for `delegate` under its own name. A task waits until it is let go, and
    what is kept says which were under way together and the call id each went by."""

    def __init__(self, spent: dict[str, float] | None = None, answers: int = 0) -> None:
        self.spent, self.answers = spent or {}, answers
        self.began: list[str] = []
        self.under_way: list[str] = []
        self.ids: dict[str, str] = {}
        self._gates: dict[str, asyncio.Event] = {}
        self._all = False
        self.tool = Tool(
            DELEGATE_TOOL_NAME, "Giao việc.", TASK, self._run, parallel=True, replay_safe=True
        )

    def _gate(self, task: str) -> asyncio.Event:
        return self._gates.setdefault(task, asyncio.Event())

    def let_go(self, *tasks: str) -> None:
        for task in tasks:
            self._gate(task).set()

    def let_all_go(self) -> None:
        self._all = True
        self.let_go(*self._gates)

    async def _run(self, arguments: dict[str, Any]) -> ToolResult:
        task = arguments["task"]
        self.ids[task] = tool_call_id()
        self.began.append(task)
        self.under_way.append(task)
        try:
            if not self._all:
                await self._gate(task).wait()
        finally:
            self.under_way.remove(task)
        said = f"xong {task}" + "." * self.answers
        spent = self.spent.get(task, 0.0)
        return ToolResult(ok=True, output=said, reply=f"lời của {task}", child_spent_usd=spent)


def handing(*tools: Tool, gated: bool = True) -> ToolRegistry:
    """An agent's tools with the script tool over them. Its scripts change things, and the
    gate lets every call run, unless `gated` says not."""
    registry = ToolRegistry(list(tools))
    gate = (lambda name, arguments: None) if gated else None
    registry.register(script_tool(lambda: registry, [], gate))
    return registry


@asynccontextmanager
async def under_way(handed: Handed, tools: ToolRegistry, source: str) -> AsyncIterator:
    """The script running while the test looks at what it has handed on. Whatever the test
    made of it, every task is let go at the end, so no script is left waiting."""
    running = asyncio.create_task(played(tools, "c1", source))
    try:
        yield running
    finally:
        handed.let_all_go()
        await asyncio.wait([running], timeout=10)


# --- a call of its own for each task ---


async def test_each_task_a_script_hands_on_opens_a_conversation_under_an_id_of_its_own(
    deps_factory, store
):
    crew = a_crew(deps_factory, store)
    parent = store.create(agent_id="boss", autonomous=True)

    result = await played(crew.deps_for("boss").tools, parent.id, TWO)

    assert result.ok, result.output
    # Numbered as the calls of the script are, the one that read among them.
    first, second = store.for_parent_call("p1:2"), store.for_parent_call("p1:3")
    assert (first.agent_id, second.agent_id) == ("worker", "boss")
    assert opened(store) == [first.id, second.id]
    assert store.for_parent_call("p1") is None and store.for_parent_call("p1:1") is None
    for child in (first, second):
        run = store.runs.latest_for_conversation(child.id)
        assert (run.source, run.status) == (f"delegate:{parent.id}", DONE)
    read, one_task, other = result.calls
    assert [call.name for call in result.calls] == ["row_read", "delegate", "delegate"]
    assert one_task.arguments == {"task": "việc một", "agent": "worker"}
    assert one_task.output.startswith(f"conversation={first.id} status=done spent=$")
    assert other.output.startswith(f"conversation={second.id} status=done spent=$")
    assert result.output.startswith(f"dòng 1\nconversation={first.id} status=done")
    assert "(echo) việc một" in result.output and "(echo) việc hai" in result.output


async def test_the_same_script_run_again_under_the_same_id_finds_what_it_opened(
    deps_factory, store
):
    """A second conversation for a task would be the task done, and paid for, twice."""
    crew = a_crew(deps_factory, store)
    tools = crew.deps_for("boss").tools
    parent = store.create(agent_id="boss", autonomous=True)
    first = await played(tools, parent.id, TWO)
    children = opened(store)
    turns = [len(store.history(child)) for child in children]

    again = await played(tools, parent.id, TWO)

    assert again.ok and again.output == first.output
    assert opened(store) == children and len(children) == 2
    assert [len(store.history(child)) for child in children] == turns
    # Another call of the model's is another script, and its tasks are its own.
    await played(tools, parent.id, TWO, call_id="p2")
    assert len(opened(store, "p2")) == 2 and opened(store) == children
    assert len(store.list()) == 5


async def test_a_script_with_no_id_to_go_by_takes_no_other_scripts_conversations(
    deps_factory, store
):
    """Two such scripts would number their tasks alike under no id at all, and the second
    would be answered with what the tasks of the first had said."""
    crew = a_crew(deps_factory, store)
    tools = crew.deps_for("boss").tools
    parent = store.create(agent_id="boss", autonomous=True)

    first = await played(tools, parent.id, TWO, call_id="")
    again = await played(tools, parent.id, TWO, call_id="")

    assert first.ok and again.ok and again.output != first.output
    assert len(store.list()) == 5


async def test_the_call_id_is_put_back_when_a_task_has_been_handed_on():
    """Three calls made one after the other in the same task, since the first changes
    things: what comes after a task reads the script's own id again."""

    async def whoami(arguments: dict[str, Any]) -> str:
        return tool_call_id()

    handed = Handed()
    handed.let_all_go()
    asking = Tool("whoami_read", "Đọc.", ROW, whoami, replay_safe=True)
    writes = Reads("notes_write", "đã ghi", replay_safe=False)
    calls = (one("notes_write"), one("delegate", task="a"), one("whoami_read"))

    result = await played(handing(writes.tool, handed.tool, asking), "c1", batch(*calls))

    assert [answer["output"] for answer in answered(result)] == ["đã ghi", "xong a", "p1"]
    assert handed.ids == {"a": "p1:2"}


def test_an_id_a_call_goes_by_is_put_back_however_the_call_ended():
    set_tool_call_id("p1")
    try:
        with calling_as("p1:4"):
            assert tool_call_id() == "p1:4"
        assert tool_call_id() == "p1"
        with pytest.raises(RuntimeError), calling_as("p1:5"):
            raise RuntimeError("hỏng")
        assert tool_call_id() == "p1"
    finally:
        set_tool_call_id("")


async def test_a_long_answer_of_a_task_is_kept_under_the_scripts_own_id(tmp_path, store):
    """The id a task went by is the conversation's link, not where its answer is kept: that
    is the script's id and the number of the call, as for any other call."""
    handed, spill = Handed(answers=RAW_LIMIT), Spill(tmp_path)
    handed.let_all_go()
    held = [Reads("rows_read").tool, handed.tool, build_output_read_tool(store, spill, 8000)]
    registry = ToolRegistry(held, 8000, None, None, spill)
    registry.register(script_tool(lambda: registry, [], lambda name, arguments: None))
    conv = store.create()
    source = """
        tools.rows_read()
        got = tools.delegate(task="a")
        print(got[-120:])
        """

    result = await played(registry, conv.id, source)

    whole = "xong a" + "." * RAW_LIMIT
    assert result.ok and result.output == (whole[:RAW_LIMIT] + told(6, "p1.2"))[-120:]
    assert spill.read(conv.id, "p1.2") == whole
    assert handed.ids == {"a": "p1:2"} and spill.read(conv.id, "p1:2.2") is None


# --- where a script may hand a task on ---


@pytest.mark.parametrize("where", ["its scripts only read", "a task it was handed", "a schedule"])
async def test_a_script_that_may_not_hand_a_task_on_is_told_to_call_delegate_directly(
    deps_factory, store, where
):
    """The agent holds `delegate` in each: what keeps its script from it is where the
    script runs. A task it was handed could hand on in its turn, and a schedule's script
    has no conversation to be the parent."""
    settings = {"script_calls": SCRIPT_READ_ONLY} if where == "its scripts only read" else {}
    crew = a_crew(deps_factory, store, **settings)
    parent = store.create(agent_id="boss", autonomous=True)
    assert crew.deps_for("boss").tools.get(DELEGATE_TOOL_NAME) is not None

    if where == "a schedule":
        with job_context("job-1"):
            script = {"script": dedent(HANDS_ON)}
            result = await crew.deps_for("boss").tools.execute(SCRIPT_TOOL, script)
    elif where == "a task it was handed":
        result = await played(crew.deps_for_child("boss").tools, parent.id, HANDS_ON, depth=1)
    else:
        result = await played(crew.deps_for("boss").tools, parent.id, HANDS_ON)

    assert "gọi trực tiếp" in NOT_A_SCRIPTS
    assert (result.ok, result.output) == (False, unfinished("trước", halted(4, NOT_A_SCRIPTS)))
    assert result.calls == () and [conv.id for conv in store.list()] == [parent.id]


@pytest.mark.parametrize(
    ("depth", "listed"), [(0, True), (1, False)], ids=["its own turn", "a task it was handed"]
)
async def test_a_script_finds_delegate_among_its_tools_only_where_it_may_call_it(
    deps_factory, store, depth, listed
):
    crew = a_crew(deps_factory, store)
    parent = store.create(agent_id="boss", autonomous=True)
    tools = crew.deps_for_child("boss").tools if depth else crew.deps_for("boss").tools
    source = """
        print("delegate" in tools.names())
        try:
            print(tools.describe("delegate")[:8])
        except Exception:
            print("không có")
        """

    result = await played(tools, parent.id, source, depth=depth)

    shown = "True\ndelegate" if listed else "False\nkhông có"
    assert (result.ok, result.output) == (True, shown)


async def test_an_agent_that_holds_no_delegate_has_none_for_its_scripts(deps_factory, store):
    """As before a script could hand anything on: no tool of that name, which is a slip a
    script may catch."""
    crew = a_crew(deps_factory, store)
    boss = crew.deps_for("boss")
    boss.tools = boss.tools.without(DELEGATE_TOOL_NAME)
    parent = store.create(agent_id="boss", autonomous=True)

    result = await played(boss.tools, parent.id, HANDS_ON)

    assert (result.ok, result.output) == (True, "trước\nbắt được\nsau")
    assert [conv.id for conv in store.list()] == [parent.id]


# --- who a task may go to ---


async def test_a_task_for_an_agent_it_may_not_hand_to_ends_the_script_and_names_who_it_may(
    deps_factory, store
):
    crew = a_crew(deps_factory, store)
    parent = store.create(agent_id="boss", autonomous=True)
    source = """
        print(tools.row_read(row=1))
        try:
            tools.delegate(task="việc", agent="stranger")
        except Exception:
            print("bắt được")
        print("sau")
        """

    result = await played(crew.deps_for("boss").tools, parent.id, source)

    wrong = words.DELEGATE_WRONG_AGENT.format(name=DELEGATE_TOOL_NAME, allowed="boss, worker")
    assert (result.ok, result.output) == (False, unfinished("dòng 1", halted(4, wrong)))
    assert "stranger" not in result.output
    assert [call.name for call in result.calls] == ["row_read"]
    assert [conv.id for conv in store.list()] == [parent.id]


async def test_one_task_for_the_wrong_agent_and_no_call_of_the_batch_is_made(deps_factory, store):
    """Known of the whole batch before any of it runs: the task written first, which the
    agent may hand on, opened nothing."""
    crew = a_crew(deps_factory, store)
    parent = store.create(agent_id="boss", autonomous=True)
    calls = (
        one("delegate", task="việc một", agent="worker"),
        one("delegate", task="việc hai", agent="stranger"),
        one("row_read", row=1),
    )

    result = await played(crew.deps_for("boss").tools, parent.id, batch(*calls))

    wrong = words.DELEGATE_WRONG_AGENT.format(name=DELEGATE_TOOL_NAME, allowed="boss, worker")
    assert (result.ok, result.output) == (False, unfinished(halted(1, wrong)))
    assert result.calls == () and [conv.id for conv in store.list()] == [parent.id]


async def test_only_a_task_handed_on_is_judged_by_the_agent_it_names():
    """Another tool may take an `agent` of its own, with its own list of them. A name off
    that list is that tool's to answer, and the script's to catch: no task was handed on."""
    owners = {
        "type": "object",
        "properties": {"agent": {"type": "string", "enum": ["an", "binh"]}},
    }

    async def owner_read(arguments: dict[str, Any]) -> str:
        return f"của {arguments.get('agent')}"

    reads = Tool("owner_read", "Đọc theo người giữ.", owners, owner_read, replay_safe=True)
    source = """
        try:
            print(tools.owner_read(agent="stranger"))
        except Exception:
            print("bắt được")
        print("sau")
        """

    result = await played(handing(Handed().tool, reads), "c1", source)

    assert result.ok, result.output
    assert result.output.splitlines()[-1] == "sau"
    assert "delegate" not in result.output


# --- a batch of tasks ---


async def test_the_tasks_of_a_batch_are_handed_on_side_by_side_and_answered_as_written():
    handed = Handed()
    source = batch(one("delegate", task="a"), one("delegate", task="b"))

    async with under_way(handed, handing(handed.tool), source) as running:
        # Both under way before either was answered: a batch of tasks is not made one at
        # a time, as a batch with a call that changes things is.
        await until(lambda: handed.under_way == ["a", "b"])
        handed.let_go("b")
        await until(lambda: handed.under_way == ["a"])
        handed.let_go("a")
        result = await asyncio.wait_for(running, 10)

    assert [answer["output"] for answer in answered(result)] == ["xong a", "xong b"]
    assert [call.arguments for call in result.calls] == [{"task": "a"}, {"task": "b"}]
    assert handed.ids == {"a": "p1:1", "b": "p1:2"}


async def test_a_batch_with_a_call_that_changes_things_hands_its_tasks_on_one_at_a_time():
    handed = Handed()
    writes = Reads("notes_write", "đã ghi", replay_safe=False)
    calls = (one("notes_write"), one("delegate", task="a"), one("delegate", task="b"))

    async with under_way(handed, handing(writes.tool, handed.tool), batch(*calls)) as running:
        await until(lambda: handed.under_way == ["a"])
        await settle_loop()
        assert handed.began == ["a"]
        handed.let_go("a")
        await until(lambda: handed.under_way == ["b"])
        handed.let_go("b")
        result = await asyncio.wait_for(running, 10)

    assert [answer["output"] for answer in answered(result)] == ["đã ghi", "xong a", "xong b"]
    assert handed.ids == {"a": "p1:2", "b": "p1:3"}


async def test_tasks_handed_on_together_count_toward_the_most_a_conversation_may_hand_on(
    deps_factory, store
):
    """Three tasks of one batch with room for two, all under way at once: the room is
    counted and taken in one stretch, so the third finds the two before it."""
    provider = GatedProvider([completion("xong")] * 3, held=(0, 1, 2))
    crew = a_crew(deps_factory, store, provider)
    parent = store.create(agent_id="boss", autonomous=True)
    earlier = [f"d{n}" for n in range(MAX_DELEGATES - 2)]
    for call_id in earlier:
        asked = ToolCall(call_id, DELEGATE_TOOL_NAME, {"task": "việc cũ"})
        store.append(parent.id, Message(role="assistant", tool_calls=(asked,)))
        store.create(agent_id="worker", parent_call_id=call_id)
    asked = ToolCall("p1", SCRIPT_TOOL, {"script": "…"})
    store.append(parent.id, Message(role="assistant", tool_calls=(asked,)))
    source = batch(*(one("delegate", task=f"việc {n}", agent="worker") for n in range(3)))

    running = asyncio.create_task(played(crew.deps_for("boss").tools, parent.id, source))
    try:
        await asyncio.wait_for(provider.started(1).wait(), 10)
        await settle_loop()
        # Neither of the two has answered, and the third opened nothing.
        assert not running.done() and provider.calls == 2
        assert [store.get(child).parent_call_id for child in opened(store)] == ["p1:1", "p1:2"]
    finally:
        for index in range(3):
            provider.release(index)
    result = await asyncio.wait_for(running, 10)

    first, second, third = answered(result)
    assert first["ok"] and second["ok"]
    full = texts.DELEGATE_TOO_MANY.format(limit=MAX_DELEGATES)
    assert third == {"ok": False, "error": texts.TOOL_FAILED.format(error=full)}
    assert len(opened(store)) == 2 and store.for_parent_call("p1:3") is None


# --- what the tasks spent, and whose answer the turn gives ---


async def test_what_the_tasks_of_a_script_spent_is_on_its_result_and_on_each_call_kept():
    handed = Handed(spent={"a": 0.25, "b": 0.5})
    handed.let_all_go()
    rows = Reads("rows_read")
    source = """
        tools.rows_read()
        tools.delegate(task="a")
        tools.delegate(task="b")
        tools.delegate(task="c")
        """

    result = await played(handing(rows.tool, handed.tool), "c1", source)

    assert result.ok and result.child_spent_usd == 0.75
    read, first, second, free = result.calls
    assert [call.child_spent_usd for call in result.calls] == [0.0, 0.25, 0.5, 0.0]
    # Not what a model was paid for the call: nothing here is metered, on a call or on the
    # script's own result.
    assert (first.cost_usd, first.metered) == (result.cost_usd, result.metered) == (None, False)
    # Written only where there is something to say: no key rather than a null one.
    assert first.to_dict()["child_spent_usd"] == 0.25
    assert set(first.to_dict()) == set(second.to_dict()) == KEPT | {"child_spent_usd"}
    assert set(read.to_dict()) == set(free.to_dict()) == KEPT


def test_a_call_kept_says_what_a_conversation_spent_only_when_one_spent_something():
    kept = {"name": "delegate", "arguments": {}, "ok": True, "output": "", "ms": 0}

    assert NestedCall(**kept, child_spent_usd=0.1).to_dict()["child_spent_usd"] == 0.1
    for nothing in (0.0, -0.1):
        assert set(NestedCall(**kept, child_spent_usd=nothing).to_dict()) == KEPT
    assert set(NestedCall(**kept).to_dict()) == KEPT


async def test_a_script_that_failed_still_carries_what_its_tasks_spent():
    handed = Handed(spent={"a": 0.25})
    handed.let_all_go()
    source = """
        tools.delegate(task="a")
        nothing_by_this_name()
        """

    result = await played(handing(handed.tool), "c1", source)

    assert not result.ok and result.child_spent_usd == 0.25


async def test_the_answer_of_a_task_is_the_scripts_to_use_and_never_the_turns_reply():
    """`relay` means nothing in a script: with it or without, the script's result carries
    no answer to give the person in the agent's place."""
    handed = Handed()
    handed.let_all_go()
    source = """
        print(tools.delegate(task="a", relay=True))
        print(tools.delegate(task="b", relay=False))
        """

    result = await played(handing(handed.tool), "c1", source)

    assert (result.ok, result.output, result.reply) == (True, "xong a\nxong b", None)


SELF = """
    print(tools.row_read(row=1))
    print(tools.delegate(task="đếm tệp")[:13])
    """


def a_turn(served) -> Served:
    """The app's agent in a turn that runs `SELF`: the model asks for the script, the
    conversation the script opened answers, then the model answers the person."""
    script = [
        completion(tool_calls=[working(SELF)], cost_usd=0.001),
        completion("Có 3 tệp.", cost_usd=0.25),
        completion("Xong.", cost_usd=0.001),
    ]
    app, _ = an_app(served, script)
    return app


async def test_a_turn_is_charged_once_for_what_its_scripts_tasks_spent(served):
    app = a_turn(served)
    await left_to_itself(app)

    events = await say(app)

    store = app.runtime.store
    [child] = opened(store)
    assert store.get(child).parent_call_id == "p1:2"
    assert store.get(child).spent_usd == pytest.approx(0.25)
    # The conversation paid its own two answers and the child's one. The run did not: what
    # a child spent is on the child's own run.
    assert store.get(app.conv.id).spent_usd == pytest.approx(0.252)
    assert stored_run(app).spent_usd == pytest.approx(0.002)
    assert stored_run(app, child).spent_usd == pytest.approx(0.25)
    read, handed_on = the_result(events)["calls"]
    assert handed_on["child_spent_usd"] == pytest.approx(0.25)
    assert (handed_on["cost_usd"], handed_on["metered"]) == (None, False)
    assert set(handed_on) == KEPT | {"child_spent_usd"} and set(read) == KEPT
    assert handed_on["output"].startswith(f"conversation={child} status=done spent=$0.25")
    # As each call ended, on the run, and beside the result the conversation keeps.
    assert [event["call"] for event in events if event["type"] == "nested_call"] == [
        read,
        handed_on,
    ]
    assert the_step(app)["calls"] == stored_calls(app) == [read, handed_on]


async def test_a_turn_whose_script_handed_a_task_on_answers_in_the_agents_own_words(served):
    """A task the model hands on itself, alone in its turn, is answered to the person in
    the child's words with no further call of the model. A script's task never is."""
    app = a_turn(served)
    await left_to_itself(app)

    await say(app)

    assert app.provider.calls == 3
    printed = "dòng 1\nconversation="
    assert history(app)[-2:] == [("tool", printed), ("assistant", "Xong.")]


# --- a child that asks a person ---


async def test_a_task_whose_agent_stops_to_ask_a_person_holds_the_script_until_answered(
    deps_factory, store
):
    """As it holds a call the model made itself: the script asks nobody, and waits on the
    conversation that does."""
    crew = a_crew(deps_factory, store)
    parent = store.create(agent_id="boss", autonomous=False)
    write = '/tool workspace_write {"path": "x.txt", "content": "1"}'
    source = f"print(tools.delegate(task={write!r}, agent='worker'))"

    running = asyncio.create_task(played(crew.deps_for("boss").tools, parent.id, source))
    await wait_until_paused(crew)
    await settle_loop()
    assert not running.done()
    [child] = opened(store)
    await collect(crew.inbound.decide(child, store.approvals.pending(child).id, True))
    result = await asyncio.wait_for(running, 10)

    assert result.ok and result.output.startswith(f"conversation={child} status=done")
    assert (crew.deps_for("worker").agent.workspace / "x.txt").read_text() == "1"


# --- what the model is told ---


def test_only_an_agent_whose_scripts_hand_tasks_on_is_told_they_do(deps_factory, store):
    told_of = words.DELEGATE_DESCRIPTION.format(most=3)
    assert "tools.delegate(" in told_of and "tools.batch" in told_of and "3" in told_of

    gated = a_crew(deps_factory, store).deps_for("boss").tools
    assert gated.get(SCRIPT_TOOL).description.endswith(told_of)
    # Told once, and not also listed among the tools a script calls by name.
    assert gated.get(SCRIPT_TOOL).description.count("delegate(") == 1

    reading = a_crew(deps_factory, Store(":memory:"), script_calls=SCRIPT_READ_ONLY)
    assert "delegate" not in reading.deps_for("boss").tools.get(SCRIPT_TOOL).description
    alone = handing(Reads("rows_read").tool)
    assert "delegate" not in alone.get(SCRIPT_TOOL).description
