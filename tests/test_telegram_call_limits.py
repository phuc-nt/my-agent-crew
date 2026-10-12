"""Every call to Telegram is one that ends (`channels/telegram_api.py`).

The bot speaks through the crew's one HTTP client, and that client's own limit is what ends
a call on a line gone quiet: a connection half open answers nothing and closes nothing. A
call that names a limit of its own is held to that one, as the long poll and an upload from
memory are. A call that names none is held to the client's. It is never held to nothing: a
send that waits for ever holds whoever awaits it, and the clock of the schedules awaits the
message of a job before it runs the next. That the client a server start makes has a limit is
pinned in `test_app_wiring.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from my_agent_crew.channels.telegram_api import (
    POLL_TIMEOUT_SECONDS,
    SEND_TIMEOUT_SECONDS,
    TelegramApi,
)
from tests.telegram_fake import CHAT, TOKEN

# Unlike in each of its four parts, so a limit that reached the wire is told from another.
OWN = httpx.Timeout(7.0, connect=3.0, pool=2.0)
ANSWERS: dict[str, Any] = {"getUpdates": [], "getFile": {"file_path": "photos/a.jpg"}}


class Wire:
    """What reached Telegram: each call's method with the limits its request carried."""

    def __init__(self) -> None:
        self.limits: list[tuple[str, dict[str, float | None]]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        self.limits.append((method, dict(request.extensions["timeout"])))
        return httpx.Response(200, json={"ok": True, "result": ANSWERS.get(method, {})})


@pytest.fixture
def wire() -> Wire:
    return Wire()


@pytest.fixture
def api(wire: Wire) -> TelegramApi:
    client = httpx.AsyncClient(transport=httpx.MockTransport(wire.handler), timeout=OWN)
    return TelegramApi(TOKEN, client)


@pytest.fixture
def chart(tmp_path: Path) -> Path:
    path = tmp_path / "chart.png"
    path.write_bytes(b"\x89PNG")
    return path


SENDS = {
    "sendMessage": lambda api, chart: api.send_message(CHAT, "Lịch hỏng."),
    "sendChatAction": lambda api, chart: api.send_chat_action(CHAT),
    "setMyCommands": lambda api, chart: api.set_my_commands([("new", "Cuộc mới")]),
    "getFile": lambda api, chart: api.file_path("file-1"),
    "sendPhoto": lambda api, chart: api.send_photo(CHAT, chart),
    "sendDocument": lambda api, chart: api.send_document(CHAT, chart),
}


@pytest.mark.parametrize("method", SENDS)
async def test_a_call_that_names_no_limit_is_held_to_the_clients_own(api, wire, chart, method):
    await SENDS[method](api, chart)

    [(called, limits)] = wire.limits
    assert called == method
    assert limits == OWN.as_dict()
    # Not one part of it is left to wait for ever.
    assert None not in limits.values()


async def test_a_message_sent_in_pieces_holds_each_piece_to_the_clients_own(api, wire):
    await api.send_message(CHAT, "a" * 5000)

    assert wire.limits == [("sendMessage", OWN.as_dict())] * 2


async def test_the_long_poll_keeps_the_limit_it_names(api, wire):
    await api.get_updates(0)

    # Longer than the wait Telegram is asked to hold the poll open for, and its own.
    assert wire.limits == [("getUpdates", httpx.Timeout(POLL_TIMEOUT_SECONDS + 10).as_dict())]
    assert wire.limits[0][1] != OWN.as_dict()


async def test_an_upload_from_memory_keeps_the_limit_it_names(api, wire):
    await api.send_bytes(CHAT, "chart.png", b"\x89PNG")

    assert wire.limits == [("sendDocument", httpx.Timeout(SEND_TIMEOUT_SECONDS).as_dict())]

