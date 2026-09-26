"""A delegated child is told to conclude before its step cap, and given no tools for
that last call, so what comes back is an answer rather than a halted fragment."""

from __future__ import annotations

from my_agent_crew import texts
from my_agent_crew.agent.child_wrap_up import WRAP_UP_AT, wrap_up_due
from my_agent_crew.agent.events import DoneEvent, HaltedEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message, ToolCall
from tests.conftest import collect

LIST = ToolCall("c", "workspace_list", {"path": "."})


def keeps_calling_tools(n: int):
    return [completion(tool_calls=(LIST,)) for _ in range(n)]


async def test_a_child_is_told_to_conclude_one_call_before_its_cap(deps_factory):
    """Cap 4: two working calls, then the wrap-up call with no tools, whose plain answer
    is read as the child's reply — not halted at the cap."""
    script = [*keeps_calling_tools(2), completion("Kết luận: 3 tệp.")]
    deps = deps_factory(script=script, max_steps=4)
    child = deps.store.create(parent_call_id="call-1", autonomous=True)

    events = await collect(run_turn(deps, child.id, "đếm tệp", depth=1))

    requests = deps.chain.providers["scripted"].requests
    assert [len(r.tools) > 0 for r in requests] == [True, True, False]
    assert requests[-1].messages[-1].content == texts.DELEGATE_WRAP_UP
    assert isinstance(events[-1], DoneEvent)
    assert deps.store.history(child.id)[-1].message.content == "Kết luận: 3 tệp."
    # The nudge is part of the child's log, so the conversation shows why it stopped.
    assert texts.DELEGATE_WRAP_UP in [m.message.content for m in deps.store.history(child.id)]


async def test_a_turn_the_person_started_keeps_its_tools_to_the_cap(deps_factory):
    deps = deps_factory(script=keeps_calling_tools(4), max_steps=4)
    conv = deps.store.create(autonomous=True)

    events = await collect(run_turn(deps, conv.id, "đếm tệp"))

    requests = deps.chain.providers["scripted"].requests
    assert all(len(r.tools) > 0 for r in requests) and len(requests) == 4
    assert isinstance(events[-1], HaltedEvent) and events[-1].reason == "max_steps"


async def test_a_child_that_ignores_the_note_is_still_stopped_at_the_cap(deps_factory):
    """The soft cap is a note, not a fence: a model that answers with a tool call anyway
    gets it run, and the hard cap ends the turn as before, with the note appended once."""
    deps = deps_factory(script=keeps_calling_tools(4), max_steps=4)
    child = deps.store.create(parent_call_id="call-1", autonomous=True)

    events = await collect(run_turn(deps, child.id, "đếm tệp", depth=1))

    assert isinstance(events[-1], HaltedEvent)
    notes = [m for m in deps.store.history(child.id) if m.message.content == texts.DELEGATE_WRAP_UP]
    assert len(notes) == 1


def test_the_soft_cap_sits_below_the_hard_cap(store):
    child = store.create(parent_call_id="call-1")
    own = store.create()
    assert not wrap_up_due(own, [], WRAP_UP_AT + 100)
    # A generous hard cap: the soft cap decides, and its last call is the wrap-up one.
    assert not wrap_up_due(child, [], WRAP_UP_AT + 100)
    assert not wrap_up_due(child, made(store, child.id, WRAP_UP_AT - 2), WRAP_UP_AT + 100)
    assert wrap_up_due(child, made(store, child.id, 1), WRAP_UP_AT + 100)
    # A cap of one leaves no room for a wrap-up call at all.
    assert not wrap_up_due(child, [], 1)


def made(store, conv_id: str, calls: int):
    for _ in range(calls):
        store.append(conv_id, Message(role="assistant", content="…"))
    return store.history(conv_id)
