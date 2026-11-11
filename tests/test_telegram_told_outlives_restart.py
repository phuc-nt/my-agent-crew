"""The messages a chat was sent with a request's buttons are followed across a restart
(`channels/telegram_told.py`, `store/telegram_told.py`).

Kept in memory alone, a request told before the process went was never closed in the chat
once it was settled elsewhere, and was never reminded of. Here the restart is a second
channel over the store the first one wrote to.
"""

from __future__ import annotations

from datetime import UTC, datetime

from my_agent_crew import texts
from my_agent_crew.channels.telegram_told import REMIND_AFTER, ToldRequests
from my_agent_crew.store.db import Store
from tests.telegram_fake import message, poll_each, press, settle
from tests.test_telegram_told import ASKS_THEN_DONE


async def asked_in_chat(make_channel, deps_factory, fake):
    """A channel whose chat was shown one request with its buttons: the two, and its deps."""
    deps = deps_factory(script=ASKS_THEN_DONE)
    channel = make_channel(deps)
    await poll_each(channel, fake, message(1, "ghi file"))
    rid = channel.store.approvals.pending(channel.conversation().id).id
    assert rid in channel.told
    return channel, rid, deps


async def test_a_request_settled_on_the_web_after_a_restart_loses_its_buttons_in_the_chat(
    make_channel, deps_factory, fake
):
    channel, rid, deps = await asked_in_chat(make_channel, deps_factory, fake)

    woken = make_channel(deps)  # the process begun again over the same store
    assert rid in woken.told
    await woken.told.sweep(woken)
    assert fake.edits == [], "still waiting: nothing to close"
    async for _ in woken.inbound.decide(woken.conversation().id, rid, True):  # on the web
        pass
    await woken.told.sweep(woken)

    [edit] = fake.edits
    assert edit["message_id"] == "1"
    assert edit["text"].endswith(texts.TELEGRAM_SETTLED_APPROVED.format(via=" trên web"))
    assert rid not in woken.told and rid not in make_channel(deps).told


async def test_a_press_after_a_restart_settles_the_request_and_leaves_nothing_to_close(
    make_channel, deps_factory, fake
):
    _, rid, deps = await asked_in_chat(make_channel, deps_factory, fake)

    woken = make_channel(deps)
    pressed = press(2, f"y:{rid}")
    pressed["callback_query"]["message"]["message_id"] = 1  # under the request's own message
    await poll_each(woken, fake, pressed)
    await settle(woken)

    assert fake.answered == [texts.TELEGRAM_PRESS_APPROVED]
    assert rid not in woken.told and deps.store.told.all(woken.agent_id) == []
    edits = len(fake.edits)
    await make_channel(deps).told.sweep(woken)
    assert len(fake.edits) == edits, "the pressed message is not closed a second time"


async def test_the_reminder_counts_from_when_the_request_was_first_told_and_comes_once(
    make_channel, deps_factory, fake
):
    deps = deps_factory(script=ASKS_THEN_DONE)
    channel = make_channel(deps)
    clock = [datetime.now(UTC)]

    def following() -> ToldRequests:
        return ToldRequests(lambda: clock[0], deps.store.told, channel.agent_id)

    channel.told = following()
    await poll_each(channel, fake, message(1, "ghi file"))
    clock[0] += REMIND_AFTER

    channel.told = following()  # restarted before the reminder was due to be looked at
    await channel.told.sweep(channel)
    [reminder] = fake.raw[1:]
    assert reminder["text"].startswith("⏰") and reminder["reply_to_message_id"] == "1"

    channel.told = following()  # and again after it was sent
    await channel.told.sweep(channel)
    assert len(fake.raw) == 2, "reminded of once, however often the process starts"


def test_each_chat_follows_its_own_messages_and_a_message_is_forgotten_by_itself(tmp_path):
    kept = Store(tmp_path / "agent.sqlite3").told
    kept.put("default", "r1", 7, "ghi file?", "2026-09-19T07:05:00+00:00")
    kept.put("default", "r1", 8, "ghi file? (nhắc lại)", "2026-09-19T07:05:00+00:00")
    kept.put("coach", "r1", 9, "của chat khác", "2026-09-19T07:05:00+00:00")

    told = ToldRequests(kept=kept, owner="default")
    told.forget("r1", 7)

    assert [row["message_id"] for row in kept.all("default")] == [8]
    assert "r1" in ToldRequests(kept=kept, owner="default")
    told.forget("r1", 8)
    assert kept.all("default") == [] and "r1" not in ToldRequests(kept=kept, owner="default")
    assert [row["message_id"] for row in kept.all("coach")] == [9]
