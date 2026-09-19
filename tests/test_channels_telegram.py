"""The Telegram channel against a fake Bot API: inbound messages become tracked turns of
a per-day conversation, replies and `MEDIA:` photos go back to the one allowed chat, and
scheduled results are delivered through the same path."""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl

import httpx
import pytest

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.channels import TelegramApi, TelegramChannel
from my_agent_crew.channels.telegram_api import (
    TelegramError,
    plain_text,
    split_message,
    split_reply,
)
from my_agent_crew.config import Route
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.types import Message
from my_agent_crew.store.models import AWAITING_APPROVAL

TOKEN = "123:secret-token"
CHAT = 42


class FakeTelegram:
    def __init__(self):
        self.updates: list[dict] = []
        self.sent: list[str] = []
        self.photos: list[bytes] = []
        self.calls: list[str] = []
        self.reject_actions = False
        self.status: int | None = None
        self.raise_connect = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert f"/bot{TOKEN}/" in str(request.url)
        method = request.url.path.rsplit("/", 1)[-1]
        self.calls.append(method)
        if self.raise_connect:
            raise httpx.ConnectError(f"cannot reach {request.url}", request=request)
        if self.status:
            return httpx.Response(self.status, json={"ok": False, "description": "Conflict"})
        if method == "getUpdates":
            form = dict(parse_qsl(request.content.decode()))
            pending = [u for u in self.updates if u["update_id"] >= int(form["offset"])]
            return httpx.Response(200, json={"ok": True, "result": pending})
        if method == "sendMessage":
            form = dict(parse_qsl(request.content.decode()))
            assert form["chat_id"] == str(CHAT)
            self.sent.append(form["text"])
        elif method == "sendPhoto":
            self.photos.append(request.content)
        elif method == "sendChatAction":
            form = dict(parse_qsl(request.content.decode()))
            assert form["chat_id"] == str(CHAT) and form["action"] == "typing"
            if self.reject_actions:
                return httpx.Response(400, json={"ok": False, "description": "Bad Request"})
        return httpx.Response(200, json={"ok": True, "result": {}})


def message(update_id: int, text: str, chat: int = CHAT) -> dict:
    return {"update_id": update_id, "message": {"chat": {"id": chat}, "text": text}}


@pytest.fixture
def fake() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture
def make_channel(deps_factory, fake, tmp_path: Path):
    def factory(deps=None, clock=datetime.now) -> TelegramChannel:
        deps = deps or deps_factory(routes=(Route("fake", "echo"),))
        client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
        api = TelegramApi(TOKEN, client)
        hub = ActivityHub(deps.store)
        return TelegramChannel(deps, hub, api, CHAT, tmp_path / "telegram.offset", clock=clock)

    return factory


async def test_inbound_message_runs_a_tracked_turn_and_replies(make_channel, fake, tmp_path):
    channel = make_channel()
    fake.updates = [message(7, "xin chào")]
    assert await channel.poll_once() == 1
    assert fake.sent == ["(echo) xin chào"]
    [conv] = channel._deps.store.list()
    assert conv.channel == f"telegram:{CHAT}" and conv.agent_id == "default"
    assert conv.title == texts.TELEGRAM_CONVERSATION_TITLE.format(date=datetime.now().date())
    [run] = channel._hub.recent()
    assert run.source == "telegram" and run.conversation_id == conv.id and run.status == "done"
    assert (tmp_path / "telegram.offset").read_text() == "8"
    assert await channel.poll_once() == 0  # offset moved past the handled update
    assert fake.calls.index("sendChatAction") < fake.calls.index("sendMessage")


async def test_typing_indicator_is_kept_alive_and_never_breaks_the_turn(make_channel, fake, caplog):
    channel = make_channel()
    async with channel._outbound.typing(interval=0.01):
        await asyncio.sleep(0.05)
    assert fake.calls.count("sendChatAction") >= 3
    assert "sendMessage" not in fake.calls
    fake.calls.clear()
    fake.reject_actions = True
    fake.updates = [message(1, "a")]
    with caplog.at_level(logging.WARNING, logger="my_agent_crew.channels"):
        await channel.poll_once()
    assert fake.sent == ["(echo) a"]
    assert "typing indicator" in caplog.text and "sendChatAction" in caplog.text


async def test_messages_from_other_chats_are_ignored(make_channel, fake):
    channel = make_channel()
    fake.updates = [message(1, "hi", chat=99), {"update_id": 2, "message": {"chat": {"id": CHAT}}}]
    assert await channel.poll_once() == 2
    assert fake.sent == [] and channel._deps.store.list() == []


async def test_same_day_messages_share_one_conversation_and_a_new_day_opens_another(
    make_channel, fake
):
    clock = [datetime.now()]
    channel = make_channel(clock=lambda: clock[0])
    fake.updates = [message(1, "a"), message(2, "b")]
    await channel.poll_once()
    assert len(channel._deps.store.list()) == 1
    clock[0] += timedelta(days=1)
    fake.updates = [message(3, "c")]
    await channel.poll_once()
    assert len(channel._deps.store.list()) == 2


async def test_new_command_opens_a_fresh_conversation(make_channel, fake):
    channel = make_channel()
    fake.updates = [message(1, "a"), message(2, "/new"), message(3, "b")]
    await channel.poll_once()
    assert fake.sent == ["(echo) a", texts.TELEGRAM_NEW_CONVERSATION, "(echo) b"]
    assert len(channel._deps.store.list()) == 2


async def test_provider_failure_and_pending_approval_become_notices(
    make_channel, fake, deps_factory
):
    channel = make_channel(deps_factory(script=[ProviderError("model down")]))
    fake.updates = [message(1, "a")]
    await channel.poll_once()
    [notice] = fake.sent
    assert notice.startswith(texts.TELEGRAM_ERROR.format(message="")) and "model down" in notice
    conv = channel.conversation()
    channel._deps.store.update(conv.id, status=AWAITING_APPROVAL)
    fake.updates = [message(2, "b")]
    await channel.poll_once()
    assert fake.sent[-1] == texts.TELEGRAM_BUSY


async def test_deliver_sends_prose_and_media_lines_as_photos(make_channel, fake):
    channel = make_channel()
    workspace = channel._deps.agent.workspace
    (workspace / "charts").mkdir()
    (workspace / "charts" / "sleep.png").write_bytes(b"PNGDATA")
    conv = channel._deps.store.create(agent_id="default")
    assert await channel.deliver(conv.id) is False
    channel._deps.store.append(
        conv.id,
        Message(
            role="assistant",
            content="**Ngủ** 5.5h\nMEDIA: charts/sleep.png\nMEDIA: charts/missing.png",
        ),
    )
    assert await channel.deliver(conv.id) is True
    assert fake.sent == ["Ngủ 5.5h", texts.TELEGRAM_MEDIA_MISSING.format(path="charts/missing.png")]
    assert len(fake.photos) == 1 and b"PNGDATA" in fake.photos[0]


async def test_api_errors_and_httpx_request_logs_never_carry_the_token(fake, caplog):
    client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    api = TelegramApi(TOKEN, client)
    with caplog.at_level(logging.INFO, logger="httpx"):
        await api.send_message(CHAT, "hello")
    assert "sendMessage" in caplog.text and "<token>" in caplog.text
    assert TOKEN not in caplog.text
    fake.status = 409
    with pytest.raises(TelegramError) as conflict:
        await api.get_updates(0)
    assert conflict.value.status == 409 and TOKEN not in str(conflict.value)
    fake.status, fake.raise_connect = None, True
    with pytest.raises(TelegramError) as unreachable:
        await api.send_message(CHAT, "x")
    assert TOKEN not in str(unreachable.value) and "<token>" in str(unreachable.value)


def test_message_helpers_split_media_chunk_long_text_and_strip_markdown():
    assert split_reply("a\nMEDIA: x.png\n b \nMEDIA:y.png") == ("a\n b", ["x.png", "y.png"])
    assert split_message("l1\n" + "x" * 4096) == ["l1", "x" * 4096]
    assert split_message("l1\n" + "x" * 4094 + "\nl3") == ["l1", "x" * 4094, "l3"]
    assert split_message("y" * 5000, limit=4096) == ["y" * 4096, "y" * 904]
    assert split_message("") == [""]
    assert plain_text("## Tiêu đề\n**đậm** thường") == "Tiêu đề\nđậm thường"
