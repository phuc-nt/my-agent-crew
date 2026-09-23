"""Stopping a bot while the server keeps running: a message being answered is let
finish, and an idle poll is cut off at once."""

import asyncio

from my_agent_crew.channels import telegram_polling
from my_agent_crew.channels.telegram_offset import read_offset, write_offset
from my_agent_crew.channels.telegram_polling import TelegramPolling
from tests.telegram_fake import message


class Poller(TelegramPolling):
    agent_id = "default"

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.started = asyncio.Event()
        self.finished = False
        self.handle_next = True

    async def register_menu(self) -> None:
        pass

    async def poll_once(self) -> int:
        self.started.set()
        if not self.handle_next:
            await asyncio.sleep(3600)  # a long poll with nothing to fetch
        self._handling = True
        try:
            await self.release.wait()
            self.finished = True
            self.handle_next = False  # nothing more arrives after this message
        finally:
            self._handling = False
        return 1


async def test_a_message_being_answered_is_let_finish() -> None:
    poller = Poller()
    poller.start()
    await poller.started.wait()
    stopping = asyncio.create_task(poller.stop())
    await asyncio.sleep(0.05)
    assert not stopping.done()  # still waiting for the turn

    poller.release.set()
    await asyncio.wait_for(stopping, timeout=1)

    assert poller.finished
    assert poller._task is None


async def test_an_idle_poll_is_cut_off_at_once() -> None:
    poller = Poller()
    poller.handle_next = False
    poller.start()
    await poller.started.wait()

    await asyncio.wait_for(poller.stop(), timeout=1)

    assert not poller.finished


async def test_a_turn_that_never_ends_is_cut_off_after_the_grace(monkeypatch) -> None:
    monkeypatch.setattr(telegram_polling, "STOP_GRACE_SECONDS", 0.05)
    poller = Poller()
    poller.start()
    await poller.started.wait()

    await asyncio.wait_for(poller.stop(), timeout=1)

    assert not poller.finished


async def test_a_stopped_bot_can_be_started_again() -> None:
    poller = Poller()
    poller.start()
    await poller.started.wait()
    poller.release.set()
    await poller.stop()

    poller.started.clear()
    poller.start()  # idle this time: nothing more to answer
    await asyncio.wait_for(poller.started.wait(), timeout=1)
    await poller.stop()


async def test_a_stop_leaves_the_queued_messages_for_the_next_bot(
    make_channel, fake, tmp_path, monkeypatch
) -> None:
    channel = make_channel()
    fake.updates = [message(7, "một"), message(8, "hai")]
    handled = []

    async def handle(ch, group) -> None:
        handled.append(group[0]["update_id"])
        ch._stopping = True  # the stop arrives while the first is being answered

    monkeypatch.setattr(telegram_polling, "handle_updates", handle)
    await channel.poll_once()

    assert handled == [7]
    assert (tmp_path / "telegram.offset").read_text() == "123 8"  # 8 stays unconfirmed


def test_an_offset_belongs_to_the_bot_that_confirmed_it(tmp_path) -> None:
    path = tmp_path / "telegram.offset"
    write_offset(path, 42, "111")
    assert read_offset(path, "111") == 42
    assert read_offset(path, "222") == 0  # a new bot starts from what Telegram still holds
    path.write_text("42")  # written before the bot was recorded
    assert read_offset(path, "222") == 42
    assert read_offset(tmp_path / "missing", "111") == 0
