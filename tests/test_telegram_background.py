"""A Telegram turn runs in the background: the chat is read while it runs, what is sent
meanwhile waits in line or steers it, and a stop waits for it before cutting it off."""

import asyncio
import logging
from datetime import datetime, timedelta

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import TELEGRAM
from my_agent_crew.channels import telegram_outbound, telegram_polling
from my_agent_crew.channels.telegram_outbound import TelegramOutbound
from my_agent_crew.inbound_queue import QueueDrain
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store.queue import FOLLOW_UP
from tests.queue_helpers import GatedProvider, SlowTool, settle_loop, until
from tests.telegram_fake import message, poll_each, settle

SLOW = ToolCall("c1", "slow", {})


def build(make_channel, deps_factory, script, clock=datetime.now):
    slow = SlowTool()
    provider = GatedProvider(script)
    deps = deps_factory(providers={"scripted": provider}, extra_tools=[slow.tool])
    channel = make_channel(deps, clock=clock)
    drain = QueueDrain(deps.store, channel.hub, channel.inbound)
    channel.set_drain(drain)
    drain.register(TELEGRAM, channel.run_delivered)  # what the channel's start does
    return channel, drain, slow, deps


def history(deps, conv_id: str) -> list[tuple[str, str]]:
    return [(m.message.role, m.message.content) for m in deps.store.history(conv_id)]


async def start_long_turn(channel, fake, slow) -> str:
    fake.updates = [message(1, "việc dài")]
    await channel.poll_once()
    await asyncio.wait_for(slow.started.wait(), 2)
    return channel.conversation().id


async def test_the_chat_is_read_while_a_turn_runs_and_what_waits_is_answered_apart(
    make_channel, deps_factory, fake
):
    script = [completion(tool_calls=[SLOW]), completion("xong"), completion("đã đọc")]
    channel, drain, slow, deps = build(make_channel, deps_factory, script)
    conv_id = await start_long_turn(channel, fake, slow)
    typing = fake.calls.count("sendChatAction")
    fake.updates = [message(2, "/status"), message(3, "tin 2"), message(4, "/new")]
    await channel.poll_once()
    assert texts.TELEGRAM_STATE_RUNNING.format(queued=0) in fake.sent[0]
    # Queued, said at once, with no "typing…" for a turn that has not begun; and no new
    # conversation beside the one still being written.
    assert fake.sent[1:] == [texts.QUEUED_FOLLOW_UP, texts.TELEGRAM_NEW_BUSY]
    assert fake.calls.count("sendChatAction") == typing
    assert channel.conversation().id == conv_id
    slow.release.set()
    await settle(channel, drain)
    assert fake.sent[3:] == ["xong", "đã đọc"]
    assert history(deps, conv_id)[-2:] == [("user", "tin 2"), ("assistant", "đã đọc")]


async def test_a_steer_reaches_the_running_turn_and_one_without_text_is_refused(
    make_channel, deps_factory, fake
):
    channel, drain, slow, deps = build(
        make_channel, deps_factory, [completion(tool_calls=[SLOW]), completion("xong")]
    )
    conv_id = await start_long_turn(channel, fake, slow)
    fake.updates = [message(2, "/steer"), message(3, "/steer tập trung vào chi phí")]
    await channel.poll_once()
    assert fake.sent == [texts.STEER_NEEDS_TEXT, texts.QUEUED_STEER]
    assert [item.text for item in deps.store.queue.peek_all(conv_id)] == ["tập trung vào chi phí"]
    slow.release.set()
    await settle(channel, drain)
    assert ("user", "tập trung vào chi phí") in history(deps, conv_id)
    assert fake.sent[2:] == ["xong"] and deps.store.queue.count(conv_id) == 0


async def test_a_turn_that_crosses_midnight_keeps_its_conversation(
    make_channel, deps_factory, fake
):
    now = [datetime(2026, 9, 30, 23, 59)]
    script = [completion(tool_calls=[SLOW]), completion("xong"), completion("đã đọc")]
    channel, drain, slow, deps = build(make_channel, deps_factory, script, clock=lambda: now[0])
    replaced: list = []
    channel.set_on_replaced(lambda *args: replaced.append(args))
    conv_id = await start_long_turn(channel, fake, slow)
    now[0] += timedelta(minutes=5)
    fake.updates = [message(2, "tin sau nửa đêm")]
    await channel.poll_once()
    assert fake.sent == [texts.QUEUED_FOLLOW_UP] and channel.conversation().id == conv_id
    slow.release.set()
    await settle(channel, drain)
    assert history(deps, conv_id)[-1] == ("assistant", "đã đọc") and replaced == []


async def stop_during_long_turn(make_channel, deps_factory, fake, release_after=None):
    script = [completion(tool_calls=[SLOW]), completion("xong")]
    channel, _, slow, _ = build(make_channel, deps_factory, script)
    await start_long_turn(channel, fake, slow)
    fake.status = 409  # the loop backs off instead of spinning on an empty fake
    channel.start()
    if release_after is not None:
        asyncio.get_running_loop().call_later(release_after, slow.release.set)
    await channel.stop()
    return channel


async def test_a_stop_waits_for_a_turn_that_ends_within_its_grace(
    make_channel, deps_factory, fake, monkeypatch
):
    monkeypatch.setattr(telegram_polling, "STOP_GRACE_SECONDS", 0.5)
    channel = await stop_during_long_turn(make_channel, deps_factory, fake, release_after=0.05)
    assert fake.sent == ["xong"] and not channel.turns  # answered, nothing cut off


async def test_a_stop_cuts_off_a_turn_past_its_grace_and_says_so_once(
    make_channel, deps_factory, fake, monkeypatch
):
    monkeypatch.setattr(telegram_polling, "STOP_GRACE_SECONDS", 0.05)
    channel = await stop_during_long_turn(make_channel, deps_factory, fake)
    assert fake.sent == [texts.TELEGRAM_CUT_OFF] and not channel.turns


async def test_a_broken_turn_is_logged_and_the_chat_hears_only_its_kind(
    make_channel, deps_factory, fake, caplog
):
    channel, *_ = build(make_channel, deps_factory, [])

    async def broken():
        raise RuntimeError("request quoting sk-secret")
        yield  # an async generator, like a turn's events

    with caplog.at_level(logging.ERROR):
        await channel.reply_to(broken(), channel.conversation().id)
    assert fake.sent == [texts.TELEGRAM_TURN_FAILED.format(error="RuntimeError")]
    assert "a turn failed" in caplog.text


async def test_a_chat_that_cannot_be_told_a_turn_broke_leaves_it_ended_and_logged(
    make_channel, deps_factory, fake, caplog
):
    """Telegram refuses every message, the one telling of the break among them. A turn is a
    task nobody awaits: nothing escapes it, and the log is where what broke it is found."""
    channel, *_ = build(make_channel, deps_factory, [])

    async def broken():
        raise RuntimeError("model down")
        yield  # an async generator, like a turn's events

    fake.fail["sendMessage"] = 500
    with caplog.at_level(logging.ERROR):
        await channel.reply_to(broken(), channel.conversation().id)
    assert fake.sent == [] and "sendMessage" in fake.calls
    assert caplog.text.count("a turn failed") == 1 and "model down" in caplog.text


async def test_the_bot_answers_what_waited_for_it_from_its_start_until_its_stop(
    make_channel, deps_factory, fake
):
    channel, drain, _, deps = build(make_channel, deps_factory, [completion("đã đọc")])
    drain.unregister(TELEGRAM)
    conv = channel.conversation()
    deps.store.queue.add(conv.id, FOLLOW_UP, "tin chờ bot", TELEGRAM)
    drain.schedule(conv.id)
    await settle_loop()
    assert deps.store.queue.count(conv.id) == 1  # no bot yet: it waits
    fake.status = 409  # the loop backs off instead of spinning on an empty fake
    channel.start()
    await until(lambda: fake.sent == ["đã đọc"])
    await channel.stop()
    deps.store.queue.add(conv.id, FOLLOW_UP, "tin sau khi dừng", TELEGRAM)
    drain.schedule(conv.id)
    await settle_loop()
    assert deps.store.queue.count(conv.id) == 1 and fake.sent == ["đã đọc"]


async def test_a_typing_indicator_that_hangs_does_not_hold_the_answer(
    make_channel, deps_factory, fake, monkeypatch, caplog
):
    monkeypatch.setattr(telegram_outbound, "TYPING_FIRST_TIMEOUT_SECONDS", 0.05)

    async def hangs(self):
        await asyncio.Event().wait()

    monkeypatch.setattr(TelegramOutbound, "_show_typing", hangs)
    channel, drain, _, _ = build(make_channel, deps_factory, [completion("xong")])
    fake.updates = [message(1, "chào")]
    await channel.poll_once()
    await settle(channel, drain, timeout=2)
    assert fake.sent == ["xong"] and "typing indicator did not answer" in caplog.text


async def test_approve_reaches_a_waiting_conversation_behind_a_newer_one(
    make_channel, deps_factory, fake
):
    guarded = SlowTool("guarded", requires_approval=True)
    guarded.release.set()
    call = ToolCall("g1", "guarded", {})
    provider = GatedProvider([completion(tool_calls=[call]), completion("đã chạy")])
    deps = deps_factory(providers={"scripted": provider}, extra_tools=[guarded.tool])
    channel = make_channel(deps)
    await poll_each(channel, fake, message(1, "làm đi"))
    waiting = channel.conversation().id
    # Only waiting on a decision, nothing runs or waits in line: `/new` opens another.
    await poll_each(channel, fake, message(2, "/new"))
    sent = len(fake.sent)
    fake.updates = [message(3, "/approve"), message(4, "/approve")]  # one decision, sent twice
    await channel.poll_once()
    await settle(channel)
    assert channel.conversation().id != waiting and guarded.runs == 1
    assert fake.sent[sent:] == [texts.TELEGRAM_NO_APPROVAL, "đã chạy"]
    assert history(deps, waiting)[-1] == ("assistant", "đã chạy")
