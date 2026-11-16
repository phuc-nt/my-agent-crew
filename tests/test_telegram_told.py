"""The requests the chat may decide: its own and those of the children it delegated, never
a job's, nor one of a conversation begun on the web or by a job and its children; the
deadline and the reminder, the messages closed when a request is settled elsewhere, and
`/pending`."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import CHAT, JOB
from my_agent_crew.channels.telegram_approvals import watch_children
from my_agent_crew.channels.telegram_told import REMIND_AFTER, ToldRequests
from my_agent_crew.llm.fake import completion
from my_agent_crew.store.approvals import EXPIRED, PENDING
from tests.lapse_helpers import WRITE
from tests.telegram_fake import asks_for, message, poll_each, press, settle

ASKS_THEN_DONE = [completion(tool_calls=(WRITE,)), completion("Đã ghi.")]


async def paused(channel, source: str = CHAT, **opened):
    """A conversation of the agent opened outside the chat, run until it asks."""
    conv = channel.store.create(agent_id=channel.agent_id, **opened)
    async for _ in channel.inbound.stream(conv.id, "ghi file", source=source):
        pass
    return conv, channel.store.approvals.pending(conv.id)


async def until_sent(fake, count: int = 1) -> None:
    for _ in range(100):
        if len(fake.sent) >= count:
            return
        await asyncio.sleep(0.01)


@pytest.mark.parametrize("root_source", [None, f"{JOB}:default/brief"], ids=["web", "job"])
async def test_a_child_of_a_conversation_not_the_chats_is_not_told_and_a_press_is_refused(
    make_channel, deps_factory, fake, root_source
):
    """A child delegated from the web or from a job is decided on the web, as its root is."""
    root_turn = [completion("Đã chạy.")] if root_source else []
    channel = make_channel(deps_factory(script=[*root_turn, *ASKS_THEN_DONE]))
    watching = asyncio.create_task(watch_children(channel))
    await asyncio.sleep(0)
    root = channel.store.create(agent_id=channel.agent_id)
    if root_source:
        async for _ in channel.inbound.stream(root.id, "chạy", source=root_source):
            pass
    _, asked = await paused(channel, root_id=root.id, parent_call_id="d1")
    await until_sent(fake)
    watching.cancel()
    assert fake.sent == [] and asked.id not in channel.told
    await poll_each(channel, fake, press(1, f"y:{asked.id}"))
    assert fake.answered == [texts.TELEGRAM_PRESS_SETTLED]
    assert channel.store.approvals.get(asked.id).status == PENDING


async def test_a_jobs_request_is_not_settled_by_a_press(make_channel, deps_factory, fake):
    channel = make_channel(deps_factory(script=ASKS_THEN_DONE))
    _, asked = await paused(channel, source=f"{JOB}:default/brief")
    await poll_each(channel, fake, press(1, f"y:{asked.id}"))
    await settle(channel)
    assert fake.answered == [texts.TELEGRAM_PRESS_SETTLED]
    assert channel.store.approvals.get(asked.id).status == PENDING
    assert fake.sent == [], "nothing of the job reaches the chat"


async def test_a_press_on_a_web_conversations_own_request_settles_nothing(
    make_channel, deps_factory, fake
):
    channel = make_channel(deps_factory(script=ASKS_THEN_DONE))
    _, asked = await paused(channel)
    await poll_each(channel, fake, press(1, f"y:{asked.id}"))
    assert fake.answered == [texts.TELEGRAM_PRESS_SETTLED]
    assert channel.store.approvals.get(asked.id).status == PENDING


async def test_a_request_says_when_it_runs_out_and_is_reminded_of_once(
    make_channel, deps_factory, fake
):
    channel = make_channel(deps_factory(script=ASKS_THEN_DONE))
    clock = [datetime.now(UTC)]
    channel.told = ToldRequests(clock=lambda: clock[0])
    await poll_each(channel, fake, message(1, "ghi file"))
    rid = channel.store.approvals.pending(channel.conversation().id).id
    assert "⏳" in fake.raw[0]["text"] and rid in channel.told
    await channel.told.sweep(channel)
    assert len(fake.raw) == 1, "not yet"
    clock[0] += REMIND_AFTER
    await channel.told.sweep(channel)
    await channel.told.sweep(channel)
    [reminder] = fake.raw[1:]
    assert reminder["text"].startswith("⏰") and WRITE.name in reminder["text"]
    assert reminder["reply_to_message_id"] == "1"


async def test_a_request_settled_on_the_web_loses_its_buttons_in_the_chat(
    make_channel, deps_factory, fake
):
    channel = make_channel(deps_factory(script=ASKS_THEN_DONE))
    await poll_each(channel, fake, message(1, "ghi file"))
    conv = channel.conversation()
    rid = channel.store.approvals.pending(conv.id).id
    async for _ in channel.inbound.decide(conv.id, rid, True):  # on the web
        pass
    await channel.told.sweep(channel)
    [edit] = fake.edits
    assert edit["message_id"] == "1"
    assert edit["text"].endswith(texts.TELEGRAM_SETTLED_APPROVED.format(via=" trên web"))
    assert rid not in channel.told
    await channel.told.sweep(channel)
    assert len(fake.edits) == 1


async def test_a_request_that_ran_out_says_so_and_a_pressed_one_is_not_closed_twice(
    make_channel, deps_factory, fake
):
    channel = make_channel(deps_factory(script=ASKS_THEN_DONE))
    await poll_each(channel, fake, message(1, "ghi file"))
    rid = channel.store.approvals.pending(channel.conversation().id).id
    channel.store.approvals.resolve(rid, False, status=EXPIRED)
    await channel.told.sweep(channel)
    assert fake.edits[-1]["text"].endswith(texts.TELEGRAM_SETTLED_EXPIRED)
    assert "⏳" in fake.edits[-1]["text"], "the message keeps what it said"


async def test_pending_lists_neither_a_jobs_request_nor_a_web_childs(
    make_channel, deps_factory, fake
):
    asks = completion(tool_calls=(WRITE,))
    channel = make_channel(deps_factory(script=[asks, asks, asks]))
    _, job = await paused(channel, source=f"{JOB}:default/brief")
    _, web = await paused(channel)  # the web's own: it is decided there
    root = channel.store.create(agent_id=channel.agent_id)
    _, child = await paused(channel, root_id=root.id, parent_call_id="d1")
    assert None not in (job, web, child)
    await poll_each(channel, fake, message(1, "/pending"))
    assert fake.sent == [texts.TELEGRAM_PENDING_NONE]
    assert all(asked.id not in channel.told for asked in (job, web, child))


async def test_pending_says_again_the_chats_own_request(make_channel, deps_factory, fake):
    channel = make_channel(deps_factory(script=ASKS_THEN_DONE))
    await poll_each(channel, fake, message(1, "ghi file"))
    await poll_each(channel, fake, message(2, "/pending"))
    assert fake.sent[1:] == [texts.TELEGRAM_PENDING.format(count=1), asks_for(WRITE)]
