"""A fake Telegram Bot API, shared by every test that drives the channel.

It answers the handful of methods the channel calls and records what was sent, so a test
can assert on the messages a person would actually see in the chat.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qsl

import httpx

TOKEN = "123:secret-token"
CHAT = 42


class FakeTelegram:
    def __init__(self):
        self.updates: list[dict] = []
        self.sent: list[str] = []
        self.photos: list[bytes] = []
        self.calls: list[str] = []
        self.menu: list[dict] = []
        self.files: dict[str, str] = {}  # file_id -> remote path Telegram serves it at
        self.reject_actions = False
        self.status: int | None = None
        self.raise_connect = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert f"/bot{TOKEN}/" in str(request.url)
        if request.url.path.startswith("/file/"):
            return self.serve_file(request)
        method = request.url.path.rsplit("/", 1)[-1]
        self.calls.append(method)
        if self.raise_connect:
            raise httpx.ConnectError(f"cannot reach {request.url}", request=request)
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
        elif method == "sendPhoto":
            self.photos.append(request.content)
        elif method == "sendChatAction":
            form = dict(parse_qsl(request.content.decode()))
            assert form["chat_id"] == str(CHAT) and form["action"] == "typing"
            if self.reject_actions:
                return httpx.Response(400, json={"ok": False, "description": "Bad Request"})
        elif method == "setMyCommands":
            form = dict(parse_qsl(request.content.decode()))
            self.menu = json.loads(form["commands"])
        return httpx.Response(200, json={"ok": True, "result": {}})

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
