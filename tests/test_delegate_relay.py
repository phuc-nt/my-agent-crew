"""A turn that was one delegation ends in the child's words: the delegator's model is not
called again to retell them. Anything less clear-cut still goes back through the model."""

from __future__ import annotations

from dataclasses import replace

import pytest

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.delegate_relay import relayable, turn_was_one_delegation
from my_agent_crew.agent.events import AssistantMessageEvent, DoneEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.config import Route
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store import Store
from my_agent_crew.tools.delegate import DELEGATE_TOOL_NAME
from my_agent_crew.tools.progress_note import PROGRESS_NOTE_TOOL_NAME
from my_agent_crew.tools.registry import ToolResult
from tests.conftest import collect
from tests.test_tools_delegate import agent

RETOLD = "Kể lại theo lời của tôi."


def delegation(call_id: str, task: str, **args) -> ToolCall:
    return ToolCall(call_id, DELEGATE_TOOL_NAME, {"task": task, "agent": "worker", **args})


@pytest.fixture
def crew(deps_factory, store: Store):
    """A scripted boss (so the test says what it asks for) over an echo worker (so the
    child's answer is predictable: the task it was given, echoed). Returns a factory
    taking the boss's first message; a retelling is scripted after it either way, so the
    test can tell whether the loop went back for it."""

    def build(first, worker_deps=None) -> tuple[Runtime, str]:
        boss = deps_factory(script=[first, completion(RETOLD)])
        worker = worker_deps or deps_factory(routes=(Route("fake", "echo"),))
        agents = {
            "boss": agent(boss, "boss", delegates=("worker",)),
            "worker": agent(worker, "worker"),
        }
        rt = Runtime(boss.settings, store, agents, ActivityHub(store))
        rt.wire_delegation()
        parent = rt.store.create(agent_id="boss", autonomous=True)
        return rt, parent.id

    return build


async def run(rt: Runtime, parent_id: str):
    deps = rt.deps_for("boss")
    events = await collect(run_turn(deps, parent_id, "nhờ worker"))
    return events, deps.chain.providers["scripted"].requests, rt.store.history(parent_id)


async def test_one_finished_delegation_is_answered_in_the_child_words(crew):
    rt, parent_id = crew(completion(tool_calls=(delegation("d1", "đếm số tệp"),)))
    events, requests, history = await run(rt, parent_id)

    child = rt.store.for_parent_call("d1")
    child_answer = rt.store.history(child.id)[-1].message.content
    assert len(requests) == 1, "the boss's model was asked once: to delegate"
    assert history[-1].message.content == child_answer and "đếm số tệp" in child_answer
    assert history[-1].provider is None and history[-1].model is None
    relayed = [e for e in events if isinstance(e, AssistantMessageEvent)][-1]
    assert relayed.content == child_answer and relayed.provider is None
    assert isinstance(events[-1], DoneEvent)


async def test_the_boss_may_keep_the_last_word_with_relay_false(crew):
    rt, parent_id = crew(completion(tool_calls=(delegation("d1", "đếm số tệp", relay=False),)))
    _, requests, history = await run(rt, parent_id)

    assert len(requests) == 2 and history[-1].message.content == RETOLD


async def test_a_blocked_child_goes_back_through_the_boss(crew):
    rt, parent_id = crew(completion(tool_calls=(delegation("d1", "BLOCKED: cần bạn đồng ý"),)))
    _, requests, history = await run(rt, parent_id)

    assert len(requests) == 2 and history[-1].message.content == RETOLD


async def test_two_delegations_in_one_turn_are_still_summed_up_by_the_boss(crew):
    calls = (delegation("d1", "việc một"), delegation("d2", "việc hai"))
    rt, parent_id = crew(completion(tool_calls=calls))
    _, requests, history = await run(rt, parent_id)

    assert len(requests) == 2 and history[-1].message.content == RETOLD


async def test_a_child_that_stopped_short_goes_back_through_the_boss(crew, deps_factory):
    """No `reply` rides on an unfinished run, so the boss reads the fragment and the
    note of what was already done, as before."""
    write = ToolCall("w", "workspace_write", {"path": "n.md", "content": "x"})
    stubborn = deps_factory(script=[completion(tool_calls=(write,)) for _ in range(3)])
    stubborn = replace(stubborn, settings=replace(stubborn.settings, max_steps=3))
    rt, parent_id = crew(completion(tool_calls=(delegation("d1", "ghi"),)), stubborn)
    _, requests, history = await run(rt, parent_id)

    assert len(requests) == 2 and history[-1].message.content == RETOLD
    assert texts.DELEGATE_UNFINISHED_DONE in history[-2].message.content


def test_what_may_be_handed_on():
    assert relayable(ToolResult(ok=True, output="h\nĐã xong.", reply="Đã xong.")) == "Đã xong."
    assert relayable(ToolResult(ok=True, output="h\nĐã xong.")) is None
    assert relayable(ToolResult(ok=False, output="lỗi", reply="Đã xong.")) is None
    assert relayable(ToolResult(ok=True, output="h", reply=texts.EMPTY_REPLY)) is None
    assert relayable(ToolResult(ok=True, output="h", reply="Status: BLOCKED, cần duyệt")) is None
    assert relayable(ToolResult(ok=True, output="h", reply="  ")) is None


def test_a_progress_note_beside_the_delegation_does_not_count_as_work(store: Store):
    conv = store.create()
    store.append(conv.id, Message(role="user", content="hỏi giúp"))
    note = ToolCall("n1", PROGRESS_NOTE_TOOL_NAME, {"text": "đang hỏi"})
    store.append(conv.id, Message(role="assistant", tool_calls=(note, delegation("d1", "hỏi"))))
    assert turn_was_one_delegation(store.history(conv.id), "d1")

    # A file read earlier in the same turn means the boss meant to combine things.
    other = store.create()
    store.append(other.id, Message(role="user", content="hỏi giúp"))
    read = ToolCall("r1", "workspace_read", {"path": "a.md"})
    store.append(other.id, Message(role="assistant", tool_calls=(read,)))
    store.append(other.id, Message(role="tool", content="…", tool_call_id="r1"))
    store.append(other.id, Message(role="assistant", tool_calls=(delegation("d2", "hỏi"),)))
    assert not turn_was_one_delegation(store.history(other.id), "d2")

    # A delegation in an earlier turn, before the person spoke again, is not this one.
    store.append(other.id, Message(role="user", content="rồi sao"))
    store.append(other.id, Message(role="assistant", tool_calls=(delegation("d3", "hỏi"),)))
    assert turn_was_one_delegation(store.history(other.id), "d3")
