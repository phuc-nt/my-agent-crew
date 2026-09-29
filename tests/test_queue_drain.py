"""The drain that answers what waited: it wakes when a conversation stops being busy, hands
the waiting messages over only when nothing holds the conversation, lets a Telegram chat
hear its answer from its bot, and stops with the server without losing what still waits."""

from __future__ import annotations

import asyncio
import logging

from my_agent_crew import texts
from my_agent_crew.activity.busy import Busy
from my_agent_crew.agent.events import DoneEvent
from my_agent_crew.agent.turn_context import CHAT, TELEGRAM
from my_agent_crew.inbound_queue import Runner
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store.queue import FOLLOW_UP
from tests.conftest import collect
from tests.queue_helpers import settle_loop, until, while_the_tool_runs
from tests.test_interrupted_calls import assert_every_call_answered, left_open

SLOW = ToolCall("c1", "slow", {})
GUARDED = ToolCall("g1", "guarded", {})


def recording(heard: list[tuple[str, str]]) -> Runner:
    async def runner(conv_id: str, source: str) -> None:
        heard.append((conv_id, source))

    return runner


def test_a_claim_is_dropped_only_by_its_own_token_and_goes_stale_after_its_grace():
    running: set[str] = set()
    woken: list[str] = []
    busy = Busy(running.__contains__, grace=60)
    busy.on_idle = woken.append
    first = busy.claim("c")
    second = busy.claim("c")  # a later claim replaces the first...
    busy.release("c", first)  # ...so the first one's token drops nothing now
    busy.settle("c")
    assert busy.busy("c") and woken == []
    busy.release("c", second)
    busy.settle("c")
    assert not busy.busy("c") and woken == ["c"]
    busy.claim("c")
    busy.release("c")  # without a token: whatever claim there is
    assert not busy.busy("c")
    running.add("c")  # a run under way holds the conversation with no claim at all
    busy.settle("c")
    assert busy.busy("c") and woken == ["c"]
    running.clear()
    busy.grace = 0
    busy.claim("c")
    assert not busy.busy("c")  # past its grace, a claim holds nothing


async def test_what_waits_when_the_drain_stops_is_answered_after_the_next_start(rigs):
    rig = rigs([completion(tool_calls=[SLOW]), completion("xong"), completion("đã đọc")])
    first = asyncio.create_task(collect(rig.inbound.stream(rig.conv.id, "việc 1")))
    await asyncio.wait_for(rig.slow.started.wait(), 2)
    await collect(rig.inbound.stream(rig.conv.id, "tin 2"))
    await rig.drain.stop()  # shutting down: the drain stops first
    rig.slow.release.set()
    await asyncio.wait_for(first, 2)
    await settle_loop()
    assert rig.statuses() == ["done"]
    assert [item.text for item in rig.store.queue.peek_all(rig.conv.id)] == ["tin 2"]
    rig.drain.start()
    await until(lambda: rig.statuses() == ["done", "done"])
    assert rig.history()[-2:] == [("user", "tin 2"), ("assistant", "đã đọc")]


async def test_start_drains_every_line_but_one_whose_call_awaits_a_decision(rigs):
    rig = rigs([completion(tool_calls=[GUARDED]), completion("đã đọc")])
    await collect(rig.inbound.stream(rig.conv.id, "làm đi"))  # waits for a decision
    other = rig.store.create("Khác", agent_id=rig.deps.agent.id)
    rig.store.queue.add(rig.conv.id, FOLLOW_UP, "chờ quyết định", CHAT)
    rig.store.queue.add("gone", FOLLOW_UP, "của hội thoại đã xoá", CHAT)
    rig.store.queue.add(other.id, FOLLOW_UP, "tin khác", CHAT)
    rig.drain.start()
    await until(lambda: rig.statuses(other.id) == ["done"])
    assert rig.history(other.id) == [("user", "tin khác"), ("assistant", "đã đọc")]
    # The decision's turn drains that line when it ends.
    assert [item.text for item in rig.store.queue.peek_all(rig.conv.id)] == ["chờ quyết định"]
    assert rig.store.queue.count("gone") == 0  # the conversation is gone, so is its line


async def test_what_waited_through_a_restart_comes_after_the_calls_it_cut_short(rigs):
    rig = rigs([completion("đã hiểu")])
    left_open(rig.store, rig.conv.id, SLOW)  # the server went down while the call ran
    rig.store.queue.add(rig.conv.id, FOLLOW_UP, "tin", CHAT)
    rig.drain.start()
    await until(lambda: rig.statuses() == ["done"])
    assert rig.history() == [
        ("user", "làm đi"),
        ("assistant", ""),
        ("tool", texts.INTERRUPTED_TOOL),
        ("user", "tin"),
        ("assistant", "đã hiểu"),
    ]
    assert rig.slow.runs == 0
    assert_every_call_answered(rig.provider.requests[0].messages)


async def test_a_claim_nobody_reads_lapses_and_what_waited_behind_it_is_answered(rigs):
    rig = rigs([completion("trả lời tin 2")])
    rig.hub.busy.grace = 0.05
    abandoned = rig.inbound.stream(rig.conv.id, "bị bỏ")  # a request that dropped
    [queued] = await collect(rig.inbound.stream(rig.conv.id, "tin 2"))
    assert queued.kind == FOLLOW_UP
    await until(lambda: rig.statuses() == ["done"])
    # What the dropped request said was never read, so it is not in the conversation.
    assert rig.history() == [("user", "tin 2"), ("assistant", "trả lời tin 2")]
    await abandoned.aclose()


async def test_a_telegram_chat_hears_its_answer_from_its_bot_and_waits_while_there_is_none(
    rigs,
):
    rig = rigs([], channel="telegram:42")
    rig.store.queue.add(rig.conv.id, FOLLOW_UP, "tin", TELEGRAM)
    rig.drain.schedule(rig.conv.id)
    await settle_loop()
    assert rig.store.queue.count(rig.conv.id) == 1 and rig.history() == []
    heard: list[tuple[str, str]] = []
    rig.drain.register(TELEGRAM, recording(heard))  # the bot comes up
    await until(lambda: heard == [(rig.conv.id, TELEGRAM)])
    # Written into the chat before the bot was asked to answer it.
    assert rig.history() == [("user", "tin")] and rig.store.queue.count(rig.conv.id) == 0
    await settle_loop()
    # The bot's runner returns once it has started its turn, before that turn's run takes
    # the conversation over, so the drain's claim holds it meanwhile: a message sent in
    # between waits instead of starting a second turn.
    assert rig.hub.busy.busy(rig.conv.id)
    rig.hub.busy.release(rig.conv.id)  # what the run does when it starts
    rig.drain.unregister(TELEGRAM)
    rig.store.queue.add(rig.conv.id, FOLLOW_UP, "tin sau", TELEGRAM)
    rig.drain.schedule(rig.conv.id)
    await settle_loop()
    assert heard == [(rig.conv.id, TELEGRAM)] and rig.store.queue.count(rig.conv.id) == 1


async def test_what_the_web_sends_to_a_telegram_chat_is_answered_here(rigs):
    rig = rigs([completion("trả lời")], channel="telegram:42")
    heard: list[tuple[str, str]] = []
    rig.drain.register(TELEGRAM, recording(heard))
    rig.store.queue.add(rig.conv.id, FOLLOW_UP, "từ web", CHAT)
    rig.drain.schedule(rig.conv.id)
    await until(lambda: rig.statuses() == ["done"])
    assert heard == [] and rig.history() == [("user", "từ web"), ("assistant", "trả lời")]


async def test_a_runner_that_fails_lets_go_of_the_conversation(rigs, caplog):
    rig = rigs([completion("trả lời tin sau")], channel="telegram:42")

    async def broken(conv_id: str, source: str) -> None:
        raise RuntimeError("bot gone")

    rig.drain.register(TELEGRAM, broken)
    with caplog.at_level(logging.ERROR, logger="my_agent_crew.inbound_queue"):
        rig.store.queue.add(rig.conv.id, FOLLOW_UP, "tin", TELEGRAM)
        rig.drain.schedule(rig.conv.id)
        await until(lambda: rig.store.queue.count(rig.conv.id) == 0)
        await settle_loop()
    assert "the turn answering it failed" in caplog.text
    assert rig.history() == [("user", "tin")]  # written, left unanswered
    # Nothing holds the conversation: the next message starts a turn at once.
    events = await collect(rig.inbound.stream(rig.conv.id, "tin sau", source=TELEGRAM))
    assert isinstance(events[-1], DoneEvent)


async def test_cancel_stops_the_turn_the_drain_runs(rigs):
    rig = rigs(
        [completion(tool_calls=[SLOW]), completion("xong 1"), completion("trả lời 2")], held=(2,)
    )
    await while_the_tool_runs(rig, "tin 2")
    await asyncio.wait_for(rig.provider.started(2).wait(), 2)
    assert rig.drain.cancel(rig.conv.id) is True
    await until(lambda: rig.statuses() == ["done", "error"])
    assert rig.runs()[1].summary == "interrupted"
    assert rig.drain.cancel(rig.conv.id) is False
    await settle_loop()
    assert rig.provider.calls == 3 and not rig.hub.busy.busy(rig.conv.id)
    assert rig.history()[-1] == ("user", "tin 2")


async def test_cancel_leaves_a_turn_someone_else_reads_to_them(rigs):
    rig = rigs([completion("một")], held=(0,))
    first = asyncio.create_task(collect(rig.inbound.stream(rig.conv.id, "tin 1")))
    await asyncio.wait_for(rig.provider.started(0).wait(), 2)
    assert rig.drain.cancel(rig.conv.id) is False
    rig.provider.release(0)
    events = await asyncio.wait_for(first, 2)
    assert isinstance(events[-1], DoneEvent) and rig.statuses() == ["done"]
