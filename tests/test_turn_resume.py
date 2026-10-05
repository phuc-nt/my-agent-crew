"""A turn the server went down under is carried on by the server that starts next
(`turn_resume.py`): as the same run, from what the log holds, once.

What the turn was doing when it was cut decides how it goes on. A call that changes
something is not made again: it is closed with a note and the model looks first. A call
that only reads is made again. A model call that died with the process is asked again."""

from __future__ import annotations

import asyncio

from my_agent_crew import texts
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store.runs import DONE, FAILED, HALTED, RUNNING
from my_agent_crew.turn_resume import resume_cut_turns
from tests.queue_helpers import SlowTool, until
from tests.restart_helpers import (
    carried_on,
    cut_mid_tool,
    go_down,
    history,
    idle,
    next_server,
    stored_run,
)
from tests.test_hosted_turns_api import kinds, read, rest, watching
from tests.test_server_api import parse_sse

SLOW = ToolCall("c1", "slow", {})
PEEK = ToolCall("p1", "peek", {})


def peeking() -> SlowTool:
    """A tool that only reads, so a restart may make its call again."""
    return SlowTool("peek", replay_safe=True)


def steps(run, kind: str) -> list[dict]:
    return [step for step in run.steps if step["kind"] == kind]


async def test_a_turn_cut_mid_tool_goes_on_as_the_same_run_and_the_call_is_not_made_again(served):
    first = served([completion(tool_calls=[SLOW])])
    cut = await cut_mid_tool(first)
    # Left as it was for the server that starts next, not closed by the one going down.
    assert (cut.status, cut.finished_at, cut.resumed) == (RUNNING, None, False)

    second = next_server(served, first, [completion("đã kiểm tra, xong")])
    run = await carried_on(second)

    assert (run.id, run.status, run.resumed) == (cut.id, DONE, True)
    assert run.after_seq == cut.after_seq and run.started_at == cut.started_at
    assert second.slow.runs == 0  # it may have taken effect already: never made twice unseen
    assert history(second) == [
        ("user", "làm đi"),
        ("assistant", ""),
        ("tool", texts.RESTART_CUT_TOOL),
        ("assistant", "đã kiểm tra, xong"),
    ]
    # The model reads why the call has no result, and decides from there.
    [asked] = second.provider.requests
    assert (asked.messages[-1].role, asked.messages[-1].content) == ("tool", texts.RESTART_CUT_TOOL)
    assert [r.id for r in second.runtime.store.runs.recent(conversation_ids=[second.conv.id])] == [
        cut.id
    ]
    [tool] = steps(run, "tool")
    assert tool["tool_call_id"] == SLOW.id and tool["ok"] is False


async def test_a_call_that_only_reads_is_made_again_and_keeps_its_place_on_the_timeline(served):
    peek = peeking()
    first = served([completion(tool_calls=[PEEK])], extra_tools=[peek.tool])
    cut = await cut_mid_tool(first, peek)
    assert [step["ok"] for step in steps(cut, "tool")] == [None]

    again = peeking()
    again.release.set()
    second = next_server(served, first, [completion("đọc xong")], extra_tools=[again.tool])
    run = await carried_on(second)

    assert (run.id, run.status) == (cut.id, DONE) and again.runs == 1
    assert history(second)[-2:] == [("tool", "xong"), ("assistant", "đọc xong")]
    [tool] = steps(run, "tool")
    assert tool["tool_call_id"] == PEEK.id and tool["ok"] is True and tool["duration_ms"] >= 0


async def test_a_model_call_that_died_with_the_server_is_asked_again(served):
    first = served([completion("không bao giờ tới")], held=(0,))
    sender = asyncio.create_task(first.client.post(first.messages, json={"text": "chào"}))
    await asyncio.wait_for(first.provider.started(0).wait(), 2)
    await go_down(first.runtime)
    await asyncio.wait_for(sender, 2)
    cut = stored_run(first)
    assert cut.status == RUNNING

    second = next_server(served, first, [completion("xin chào")])
    run = await carried_on(second)

    assert (run.id, run.status) == (cut.id, DONE)
    assert history(second) == [("user", "chào"), ("assistant", "xin chào")]
    # The call that never answered leaves no step behind: one model step, and it is closed.
    [model] = steps(run, "model")
    assert model["duration_ms"] >= 0


async def test_a_turn_is_taken_up_once_and_never_after_it_was_cut_again(served):
    """The guard against a turn that takes the server down with it: started again at every
    boot, it would keep the server from ever staying up."""
    first = served([completion(tool_calls=[SLOW])])
    cut = await cut_mid_tool(first)
    second = next_server(served, first, [completion(tool_calls=[ToolCall("c2", "slow", {})])])
    assert [run.id for run in resume_cut_turns(second.runtime)] == [cut.id]
    await asyncio.wait_for(second.slow.started.wait(), 2)
    await go_down(second.runtime)
    again = stored_run(second)
    assert (again.status, again.resumed) == (RUNNING, True)

    third = next_server(served, first, [completion("không được hỏi")])

    assert third.runtime.hub.cut == [] and resume_cut_turns(third.runtime) == []
    closed = stored_run(third)
    assert (closed.id, closed.status, closed.summary) == (cut.id, FAILED, "interrupted")
    assert closed.finished_at is not None
    assert third.provider.requests == [] and third.slow.runs == 0
    assert not third.runtime.hub.busy.busy(third.conv.id)
    # The conversation is open to the next message, as after any interrupted turn.
    sent = await third.client.post(third.messages, json={"text": "còn đó không"})
    assert parse_sse(sent.text)[-1]["type"] == "done"


async def test_a_conversation_that_spent_its_budget_is_not_taken_up(served):
    first = served([completion(tool_calls=[SLOW])])
    cut = await cut_mid_tool(first)
    first.runtime.store.add_spend(first.conv.id, first.conv.cost_cap_usd)

    second = next_server(served, first, [completion("không được hỏi")])

    assert resume_cut_turns(second.runtime) == []
    closed = stored_run(second)
    assert (closed.id, closed.status, closed.summary) == (cut.id, FAILED, "interrupted")
    assert second.provider.requests == []


async def test_a_turn_carried_on_stops_at_the_budget_like_any_other(served):
    first = served([completion(tool_calls=[SLOW])])
    await cut_mid_tool(first)
    cap = first.conv.cost_cap_usd
    script = [completion(tool_calls=[ToolCall("c2", "slow", {})], cost_usd=cap), completion("x")]
    second = next_server(served, first, script)
    second.slow.release.set()

    run = await carried_on(second)

    assert run.status == HALTED and len(second.provider.requests) == 1
    assert second.runtime.store.get(second.conv.id).over_budget


async def test_stop_ends_a_turn_that_was_carried_on(served):
    peek = peeking()
    first = served([completion(tool_calls=[PEEK])], extra_tools=[peek.tool])
    cut = await cut_mid_tool(first, peek)
    again = peeking()
    second = next_server(served, first, [completion("không tới")], extra_tools=[again.tool])
    resume_cut_turns(second.runtime)
    await asyncio.wait_for(again.started.wait(), 2)

    stopped = await second.client.post(second.stop)

    assert stopped.json()["cancelled"] is True
    run = await idle(second)
    # Stopped by a person on a server that stays up: closed, not left for a next start.
    assert (run.id, run.status, run.summary) == (cut.id, FAILED, "interrupted")
    assert second.provider.requests == []


async def test_a_tab_can_read_along_with_a_turn_that_was_carried_on(served):
    peek = peeking()
    first = served([completion(tool_calls=[PEEK])], extra_tools=[peek.tool])
    await cut_mid_tool(first, peek)
    again = peeking()
    second = next_server(served, first, [completion("đọc xong")], extra_tools=[again.tool])
    resume_cut_turns(second.runtime)
    await asyncio.wait_for(again.started.wait(), 2)

    stream = watching(second)
    [handed] = await read(stream, 1)
    assert (handed["type"], handed["running"]) == ("watching", True)
    # What it is handed is the turn from its start: the message that began it, and the call.
    assert [m["role"] for m in handed["detail"]["messages"]] == ["user", "assistant"]
    again.release.set()
    assert kinds(await rest(stream))[-2:] == ["assistant_message", "done"]


async def test_what_is_sent_meanwhile_waits_behind_the_turn_that_was_carried_on(served):
    peek = peeking()
    first = served([completion(tool_calls=[PEEK])], extra_tools=[peek.tool])
    await cut_mid_tool(first, peek)
    again = peeking()
    script = [completion("đọc xong"), completion("đã nghe")]
    second = next_server(served, first, script, extra_tools=[again.tool])
    resume_cut_turns(second.runtime)
    await asyncio.wait_for(again.started.wait(), 2)

    sent = await second.client.post(second.messages, json={"text": "tin sau"})
    assert parse_sse(sent.text)[-1]["type"] == "queued"
    again.release.set()
    await until(lambda: history(second)[-1] == ("assistant", "đã nghe"))

    assert history(second)[-4:] == [
        ("tool", "xong"),
        ("assistant", "đọc xong"),
        ("user", "tin sau"),
        ("assistant", "đã nghe"),
    ]
