"""A fake Telegram Bot API, shared by every test that drives the channel.

It answers the handful of methods the channel calls and records what was sent, so a test
can assert on the messages a person would actually see in the chat. A test can also make a
method fail, or hold one call unanswered while it changes something behind the channel's back.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable
from typing import NamedTuple
from urllib.parse import parse_qsl

import httpx

TOKEN = "123:secret-token"
CHAT = 42
_FIELD = re.compile(r'name="([^"]*)"(?:; filename="([^"]*)")?')


class Upload(NamedTuple):
    """A photo or a document as the chat received it."""

    method: str
    name: str
    caption: str
    data: bytes


def multipart(request: httpx.Request) -> dict[str, tuple[str, bytes]]:
    """The parts of an upload by field: the file name ("" for a plain field) and the bytes."""
    boundary = request.headers["content-type"].split("boundary=", 1)[1].encode()
    parts: dict[str, tuple[str, bytes]] = {}
    for chunk in request.content.split(b"--" + boundary)[1:-1]:
        head, _, body = chunk[2:-2].partition(b"\r\n\r\n")  # each part sits between two CRLF
        field = _FIELD.search(head.decode())
        assert field is not None, head
        parts[field[1]] = (field[2] or "", body)
    return parts


class FakeTelegram:
    def __init__(self):
        self.updates: list[dict] = []
        self.sent: list[str] = []
        self.photos: list[bytes] = []
        self.documents: list[bytes] = []
        self.uploads: list[Upload] = []
        self.calls: list[str] = []
        self.menu: list[dict] = []
        self.files: dict[str, str] = {}  # file_id -> remote path Telegram serves it at
        self.reject_actions = False
        self.status: int | None = None
        self.raise_connect = False
        self.fail: dict[str, int] = {}  # method -> the HTTP status it is refused with
        self._held: dict[str, asyncio.Event] = {}

    def hold(self, method: str) -> asyncio.Event:
        """The next call of `method` shows in `calls` and then waits, unanswered, until the
        returned event is set."""
        gate = self._held[method] = asyncio.Event()
        return gate

    def handler(self, request: httpx.Request) -> httpx.Response | Awaitable[httpx.Response]:
        assert f"/bot{TOKEN}/" in str(request.url)
        if request.url.path.startswith("/file/"):
            return self.serve_file(request)
        method = request.url.path.rsplit("/", 1)[-1]
        self.calls.append(method)
        if self.raise_connect:
            raise httpx.ConnectError(f"cannot reach {request.url}", request=request)
        gate = self._held.pop(method, None)
        return self.answer(request, method) if gate is None else self.late(gate, request, method)

    async def late(self, gate: asyncio.Event, request: httpx.Request, method: str):
        await gate.wait()
        return self.answer(request, method)

    def answer(self, request: httpx.Request, method: str) -> httpx.Response:
        if method in self.fail:
            refusal = {"ok": False, "description": "refused by the fake"}
            return httpx.Response(self.fail[method], json=refusal)
        if method == "getFile":
            form = dict(parse_qsl(request.content.decode()))
            remote = self.files.get(form["file_id"])
            if remote is None:
                return httpx.Response(400, json={"ok": False, "description": "file not found"})
            return httpx.Response(200, json={"ok": True, "result": {"file_path": remote}})
        if self.status and method == "getUpdates":
            return httpx.Response(self.status, json={"ok": False, "description": "Conflict"})
        if method == "getUpdates":
            form = dict(parse_qsl(request.content.decode()))
            pending = [u for u in self.updates if u["update_id"] >= int(form["offset"])]
            return httpx.Response(200, json={"ok": True, "result": pending})
        if method == "sendMessage":
            form = dict(parse_qsl(request.content.decode()))
            assert form["chat_id"] == str(CHAT)
            self.sent.append(form["text"])
        elif method in ("sendPhoto", "sendDocument"):
            self.receive(request, method)
        elif method == "sendChatAction":
            form = dict(parse_qsl(request.content.decode()))
            assert form["chat_id"] == str(CHAT) and form["action"] == "typing"
            if self.reject_actions:
                return httpx.Response(400, json={"ok": False, "description": "Bad Request"})
        elif method == "setMyCommands":
            form = dict(parse_qsl(request.content.decode()))
            self.menu = json.loads(form["commands"])
        return httpx.Response(200, json={"ok": True, "result": {}})

    def receive(self, request: httpx.Request, method: str) -> None:
        """An upload to the one chat, in the field its method reads the file from."""
        parts = multipart(request)
        assert parts["chat_id"] == ("", str(CHAT).encode())
        name, data = parts["photo" if method == "sendPhoto" else "document"]
        caption = parts.get("caption", ("", b""))[1].decode()
        self.uploads.append(Upload(method, name, caption, data))
        (self.photos if method == "sendPhoto" else self.documents).append(request.content)

    def serve_file(self, request: httpx.Request) -> httpx.Response:
        """`GET /file/bot<token>/<remote path>`: the bytes of a file the person sent."""
        assert request.method == "GET"
        self.calls.append("download")
        remote = request.url.path.split(f"/file/bot{TOKEN}/", 1)[1]
        if remote not in self.files.values():
            return httpx.Response(404, text="Not Found")
        return httpx.Response(200, content=b"BYTES:" + remote.encode())


def message(update_id: int, text: str, chat: int = CHAT) -> dict:
    return {"update_id": update_id, "message": {"chat": {"id": chat}, "text": text}}


def photo(update_id: int, file_id: str, caption: str = "", chat: int = CHAT) -> dict:
    sizes = [{"file_id": "small", "width": 90}, {"file_id": file_id, "width": 1280}]
    body = {"chat": {"id": chat}, "photo": sizes, **({"caption": caption} if caption else {})}
    return {"update_id": update_id, "message": body}


def document(update_id: int, file_id: str, name: str, caption: str = "") -> dict:
    body = {"chat": {"id": CHAT}, "document": {"file_id": file_id, "file_name": name}}
    if caption:
        body["caption"] = caption
    return {"update_id": update_id, "message": body}


def voice(update_id: int, file_id: str, duration: float = 3, caption: str = "") -> dict:
    """A `message.voice`, always OGG/Opus by Telegram's own rule."""
    body = {
        "chat": {"id": CHAT},
        "voice": {"file_id": file_id, "duration": duration, "mime_type": "audio/ogg"},
    }
    if caption:
        body["caption"] = caption
    return {"update_id": update_id, "message": body}


def audio(
    update_id: int,
    file_id: str,
    duration: float = 3,
    mime_type: str = "",
    file_name: str = "",
    caption: str = "",
) -> dict:
    """A `message.audio`: an uploaded audio file rather than a recorded voice note, told
    apart by mime type first and its file name's suffix second."""
    entry: dict = {"file_id": file_id, "duration": duration}
    if mime_type:
        entry["mime_type"] = mime_type
    if file_name:
        entry["file_name"] = file_name
    body = {"chat": {"id": CHAT}, "audio": entry}
    if caption:
        body["caption"] = caption
    return {"update_id": update_id, "message": body}


async def settle(channel, drain=None, timeout: float = 5.0) -> None:
    """Waits for the turns a channel runs in the background, and for any turn they or the
    drain start after them, so a test reads the chat once everything it set off is done."""
    async with asyncio.timeout(timeout):
        while True:
            tasks = [*channel.turns, *(drain._tasks if drain is not None else ())]
            running = [task for task in tasks if not task.done()]
            if not running:
                return
            await asyncio.gather(*running, return_exceptions=True)


async def poll_each(channel, fake: FakeTelegram, *updates: dict) -> None:
    """One poll per update, each answered before the next is sent: a person who waits for
    the reply. Updates of one poll that find a turn running wait in its line instead."""
    for update in updates:
        fake.updates = [update]
        await channel.poll_once()
        await settle(channel)
