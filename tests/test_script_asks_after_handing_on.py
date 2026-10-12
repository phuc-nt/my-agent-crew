"""A script that handed tasks on and then asks a model (`script/model_calls.py` over
`script/nested.py`).

What a conversation spent that a script handed a task to is the script's own conversation's
spend too, and is added there once, when the script ends (`agent/tool_calls.py`). Until then
the conversation does not show it. An asking is refused once the conversation has spent the
most it may, so what the script's own tasks spent is counted with it there: each task that
came back, from the moment it did.

How a conversation that spent all it may refuses an asking at all is in
`test_script_model_calls.py`; what a task's spend is, and where it is charged, in
`test_script_delegate.py`. A script here runs in a real child process unless the test says
otherwise.
"""

from __future__ import annotations

import asyncio

import pytest

from my_agent_crew import texts_script as t
from my_agent_crew.agent.events import DoneEvent, HaltedEvent, ToolResultEvent
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.agent.nested_calls import NestedBudget, start_nested_budget
from my_agent_crew.agent.turn_context import set_turn_conversation
from my_agent_crew.config import SCRIPT_GATED
from my_agent_crew.llm.fake import completion
from my_agent_crew.script.limits import Halt
from my_agent_crew.script.model_calls import ModelCalls, agents_model
from my_agent_crew.script.nested import ScriptRun
from my_agent_crew.script.tool import hand_script
from tests.conftest import collect
from tests.test_mcp_turns import say
from tests.test_script_batch_run import one
from tests.test_script_delegate import Handed, opened
from tests.test_script_gated_turns import an_app, left_to_itself, working
from tests.test_script_model_calls import ASKED, OVER, side_calls
from tests.test_script_turn_budget import scripted
from tests.test_script_turns import the_result

# Would carry on past an asking that only failed.
HANDS_ON_THEN_ASKS = """
    tools.delegate(task="a")
    try:
        print(llm.classify("mua ngay", ["rác", "thường"]))
    except Exception:
        print("bắt được")
    print("sau")
    """
ONE_AFTER_ANOTHER = """
    tools.delegate(task="a")
    tools.delegate(task="b")
    print(llm.classify("mua ngay", ["rác", "thường"]))
    """
SIDE_BY_SIDE = f"""
    tools.batch([{one("delegate", task="a")}, {one("delegate", task="b")}])
    print("giao xong")
    print(llm.classify("mua ngay", ["rác", "thường"]))
    """
ASKS_BETWEEN = """
    tools.delegate(task="a")
    print(llm.classify("mua ngay", ["rác", "thường"]))
    tools.delegate(task="b")
    print(llm.classify("họp lúc ba giờ", ["rác", "thường"]))
    """


def refused(line: int, *printed: str) -> str:
    """What a script that printed `printed` and was then refused an asking for the money
    came to."""
    return "\n".join((t.SCRIPT_FAILED, *printed, t.SCRIPT_HALTED.format(line=line, reason=OVER)))


def tasks(**spent: float) -> Handed:
    """Stands in for `delegate`: each task comes back at once, and its conversation spent
    what is said of it here."""
    handed = Handed(spent=spent)
    handed.let_all_go()
    return handed


def a_turn(deps_factory, script, handed: Handed, max_steps: int = 2) -> AgentDeps:
    """Deps whose agent's scripts hand tasks on and ask the agent's own model."""
    deps = deps_factory(
        script=script, extra_tools=[handed.tool], script_calls=SCRIPT_GATED, max_steps=max_steps
    )
    hand_script(deps)
    return deps


def the_script(events: list) -> ToolResultEvent:
    [result] = [event for event in events if isinstance(event, ToolResultEvent)]
    return result


def names(result: ToolResultEvent) -> list[str]:
    return [call["name"] for call in result.calls]


# --- a real task, in a real turn ---


async def test_a_task_that_took_the_conversation_over_its_cap_leaves_its_script_no_asking(served):
    """The turn's first call wrote the script, whose task was answered by the conversation it
    opened at a quarter of a dollar. The conversation may spend a tenth and shows a tenth of
    a cent, since the quarter is added when the script ends. The asking is not made."""
    script = [
        completion(tool_calls=[working(HANDS_ON_THEN_ASKS)], cost_usd=0.001),
        completion("Có 3 tệp.", cost_usd=0.25),
        completion("rác", cost_usd=0.004),
        completion("Xong.", cost_usd=0.001),
    ]
    app, _ = an_app(served, script)
    await left_to_itself(app)
    store = app.runtime.store
    store.update(app.conv.id, cost_cap_usd=0.1)

    events = await say(app)

    [child] = opened(store)
    assert store.get(child).spent_usd == pytest.approx(0.25)
    result = the_result(events)
    assert [call["name"] for call in result["calls"]] == ["delegate"]
    # Ended where it asked, which no `except` of its own caught.
    assert (result["ok"], result["output"]) == (False, refused(4))
    # The turn's call and the task's: no model was asked for the script, and none was paid.
    assert app.provider.calls == 2 and side_calls(store) == []
    # The turn then stops on the money, charged once for what the task spent.
    assert (events[-1]["type"], events[-1]["reason"]) == ("halted", "budget")
    assert store.get(app.conv.id).spent_usd == pytest.approx(0.251)


# --- what is counted ---


async def test_a_script_asks_no_model_once_what_its_task_spent_is_the_most_it_may(deps_factory):
    script = [
        completion(tool_calls=[scripted(HANDS_ON_THEN_ASKS)]),
        completion("rác", cost_usd=0.004),
        completion("Xong."),
    ]
    deps = a_turn(deps_factory, script, tasks(a=0.25))
    conv = deps.store.create(cost_cap_usd=0.1)

    events = await collect(run_turn(deps, conv.id, "lọc thư"))

    result = the_script(events)
    assert names(result) == ["delegate"]
    assert (result.ok, result.output) == (False, refused(4))
    assert len(deps.chain.providers["scripted"].requests) == 1 and side_calls(deps.store) == []
    assert events[-1] == HaltedEvent(reason="budget", spent_usd=pytest.approx(0.251))
    assert deps.store.get(conv.id).spent_usd == pytest.approx(0.251)


async def test_what_the_conversation_spent_and_what_the_task_spent_are_counted_together(
    deps_factory,
):
    """Neither is the most the conversation may spend, and the two together are exactly
    that: spent, as the turn reads it before a call of its own."""
    script = [
        completion(tool_calls=[scripted(HANDS_ON_THEN_ASKS)], cost_usd=0.25),
        completion("rác", cost_usd=0.004),
    ]
    deps = a_turn(deps_factory, script, tasks(a=0.25))
    conv = deps.store.create(cost_cap_usd=0.5)

    events = await collect(run_turn(deps, conv.id, "lọc thư"))

    result = the_script(events)
    assert (result.ok, result.output, names(result)) == (False, refused(4), ["delegate"])
    assert len(deps.chain.providers["scripted"].requests) == 1 and side_calls(deps.store) == []
    assert events[-1] == HaltedEvent(reason="budget", spent_usd=pytest.approx(0.5))


@pytest.mark.parametrize(
    ("source", "line", "printed"),
    [(ONE_AFTER_ANOTHER, 4, ()), (SIDE_BY_SIDE, 4, ("giao xong",))],
    ids=["one after another", "side by side"],
)
async def test_the_tasks_of_a_script_are_counted_together_however_they_were_handed_on(
    deps_factory, source, line, printed
):
    """Each task spent less than the conversation has left, and the two more than that."""
    script = [completion(tool_calls=[scripted(source)]), completion("rác", cost_usd=0.004)]
    deps = a_turn(deps_factory, script, tasks(a=0.006, b=0.006))
    conv = deps.store.create(cost_cap_usd=0.01)

    events = await collect(run_turn(deps, conv.id, "lọc thư"))

    result = the_script(events)
    assert (result.ok, result.output) == (False, refused(line, *printed))
    assert names(result) == ["delegate", "delegate"]
    assert len(deps.chain.providers["scripted"].requests) == 1 and side_calls(deps.store) == []
    assert deps.store.get(conv.id).spent_usd == pytest.approx(0.013)


async def test_a_task_is_counted_from_the_moment_it_came_back(deps_factory):
    """The first asking finds one task back and money left, and is made and paid. The
    second finds two."""
    script = [
        completion(tool_calls=[scripted(ASKS_BETWEEN)]),
        completion("rác", cost_usd=0.004),
        completion("thường", cost_usd=0.004),
    ]
    deps = a_turn(deps_factory, script, tasks(a=0.006, b=0.006))
    conv = deps.store.create(cost_cap_usd=0.012)

    events = await collect(run_turn(deps, conv.id, "lọc thư"))

    result = the_script(events)
    assert (result.ok, result.output) == (False, refused(5, "rác"))
    assert names(result) == ["delegate", "llm.classify", "delegate"]
    assert len(deps.chain.providers["scripted"].requests) == 2
    assert [row[-1] for row in side_calls(deps.store)] == [0.004]
    assert deps.store.get(conv.id).spent_usd == pytest.approx(0.017)


# --- and what is not ---


async def test_a_script_whose_task_left_money_asks_and_each_is_charged_once(deps_factory):
    script = [
        completion(tool_calls=[scripted(HANDS_ON_THEN_ASKS)]),
        completion("rác", cost_usd=0.004),
        completion("Xong."),
    ]
    deps = a_turn(deps_factory, script, tasks(a=0.002))
    conv = deps.store.create(cost_cap_usd=0.05)

    events = await collect(run_turn(deps, conv.id, "lọc thư"))

    result = the_script(events)
    assert (result.ok, result.output) == (True, "rác\nsau")
    assert names(result) == ["delegate", "llm.classify"]
    assert isinstance(events[-1], DoneEvent)
    # The turn's two calls, the asking and the task: 0.001 + 0.001 + 0.004 + 0.002.
    assert deps.store.get(conv.id).spent_usd == pytest.approx(0.008)


async def test_a_conversation_with_no_ceiling_asks_whatever_its_tasks_spent(deps_factory):
    script = [
        completion(tool_calls=[scripted(HANDS_ON_THEN_ASKS)]),
        completion("rác", cost_usd=0.004),
        completion("Xong."),
    ]
    deps = a_turn(deps_factory, script, tasks(a=5.0))
    conv = deps.store.create(cost_cap_usd=0.0)

    events = await collect(run_turn(deps, conv.id, "lọc thư"))

    result = the_script(events)
    assert (result.ok, result.output) == (True, "rác\nsau")
    assert deps.store.get(conv.id).spent_usd == pytest.approx(5.006)


async def test_what_an_earlier_script_handed_on_is_counted_once_by_a_later_script_of_the_turn(
    deps_factory,
):
    """It was added to the conversation when that script ended, and is owed by no script
    after. Counted again, the later script would find nothing left and ask no model."""
    script = [
        completion(tool_calls=[scripted('tools.delegate(task="a")\nprint("giao xong")')]),
        completion(
            tool_calls=[scripted('print(llm.classify("mua ngay", ["rác", "thường"]))', "p2")]
        ),
        completion("rác", cost_usd=0.004),
    ]
    deps = a_turn(deps_factory, script, tasks(a=0.006), max_steps=3)
    conv = deps.store.create(cost_cap_usd=0.01)

    events = await collect(run_turn(deps, conv.id, "lọc thư"))

    first, second = (event for event in events if isinstance(event, ToolResultEvent))
    assert (first.ok, first.output) == (True, "giao xong")
    # The turn's two calls and the task came to 0.008 of the 0.01 it may spend.
    assert (second.ok, second.output, names(second)) == (True, "rác", ["llm.classify"])
    assert deps.store.get(conv.id).spent_usd == pytest.approx(0.012)


async def test_an_asking_refused_for_what_the_tasks_spent_is_no_call_the_script_made(
    deps_factory,
):
    """Not made, so not counted: among what one script may ask, or among the calls the
    scripts of the turn may make between them. The task before it was, and stays."""
    deps = a_turn(deps_factory, [completion("rác")], tasks(a=0.25))
    conv = deps.store.create(cost_cap_usd=0.1)

    async def turn() -> tuple[ModelCalls, NestedBudget]:
        set_turn_conversation(conv.id)
        budget = start_nested_budget(1)
        run = ScriptRun(deps.tools, gate=lambda name, arguments: None)
        calls = ModelCalls(run, agents_model(deps))
        assert (await run.answer("delegate", {"task": "a"})).ok
        with pytest.raises(Halt) as ended:
            await calls.answer(dict(ASKED))
        assert str(ended.value) == OVER
        return calls, budget

    calls, budget = await asyncio.create_task(turn())

    assert (calls.asked, calls.run.made) == (0, 1)
    assert [call.name for call in calls.run.calls] == ["delegate"]
    assert (budget.used, budget.spent) == (1, False)
    assert deps.chain.providers["scripted"].requests == []
    # Nothing is added to the conversation for it here: that is done when the script ends.
    assert deps.store.get(conv.id).spent_usd == 0
