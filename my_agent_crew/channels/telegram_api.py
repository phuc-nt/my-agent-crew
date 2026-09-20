"""Thin Telegram Bot API client: long-poll updates, send text (chunked to Telegram's
limit) and photos. The token sits in the request URL, so every error string that could
carry it is redacted before it reaches a log or an exception."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

API_BASE = "https://api.telegram.org"
MESSAGE_LIMIT = 4096
POLL_TIMEOUT_SECONDS = 25
CONFLICT_STATUS = 409  # another process polls the same bot
MEDIA_PREFIX = "MEDIA:"
TOKEN_PLACEHOLDER = "<token>"

_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)


class TelegramError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def plain_text(text: str) -> str:
    """Telegram shows markdown markers literally without a parse mode; drop the two the
    models use most so the message reads naturally."""
    return _HEADING.sub("", _BOLD.sub(r"\1", text))


def split_reply(text: str) -> tuple[str, list[str]]:
    """Separates `MEDIA:<path>` lines from the prose; the paths become photo uploads."""
    prose, media = [], []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(MEDIA_PREFIX):
            media.append(stripped[len(MEDIA_PREFIX) :].strip())
        else:
            prose.append(line)
    return "\n".join(prose).strip(), media


def split_message(text: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    """Chunks at newlines where possible so a long brief stays readable."""
    chunks: list[str] = []
    rest = text
    while len(rest) > limit:
        cut = rest.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip("\n")
    if rest or not chunks:
        chunks.append(rest)
    return chunks


class RedactingFilter(logging.Filter):
    """httpx logs every request URL at INFO, and Telegram URLs carry the bot token."""

    def __init__(self, token: str):
        super().__init__()
        self._token = token

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = str(record.msg).replace(self._token, TOKEN_PLACEHOLDER)
        if isinstance(record.args, tuple):
            record.args = tuple(
                str(arg).replace(self._token, TOKEN_PLACEHOLDER) if self._token in str(arg) else arg
                for arg in record.args
            )
        return True


class TelegramApi:
    def __init__(self, token: str, client: httpx.AsyncClient, base: str = API_BASE):
        self._token = token
        self._client = client
        self._base = base
        logging.getLogger("httpx").addFilter(RedactingFilter(token))

    def redact(self, text: str) -> str:
        return text.replace(self._token, TOKEN_PLACEHOLDER)

    async def call(
        self,
        method: str,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        url = f"{self._base}/bot{self._token}/{method}"
        try:
            response = await self._client.post(url, data=data, files=files, timeout=timeout)
        except httpx.HTTPError as exc:
            raise TelegramError(f"{method}: {self.redact(str(exc))}") from exc
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not response.is_success or not body.get("ok"):
            # Both the description and the body can be empty; the status alone still has
            # to reach the log, or the failure shows up as a bare method name.
            detail = body.get("description") or self.redact(response.text[:200]).strip()
            message = f"{method}: HTTP {response.status_code}"
            raise TelegramError(f"{message} {detail}" if detail else message, response.status_code)
        return body["result"]

    async def get_updates(
        self, offset: int, timeout: int = POLL_TIMEOUT_SECONDS
    ) -> list[dict[str, Any]]:
        data = {"offset": offset, "timeout": timeout, "allowed_updates": json.dumps(["message"])}
        return await self.call("getUpdates", data, timeout=timeout + 10)

    async def send_message(self, chat_id: int, text: str) -> None:
        for chunk in split_message(plain_text(text)):
            await self.call("sendMessage", {"chat_id": chat_id, "text": chunk})

    async def send_photo(self, chat_id: int, path: Path) -> None:
        with path.open("rb") as handle:
            await self.call("sendPhoto", {"chat_id": chat_id}, files={"photo": (path.name, handle)})

    async def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        """Shows "typing…" in the chat; Telegram clears it after ~5 s or on the next message."""
        await self.call("sendChatAction", {"chat_id": chat_id, "action": action})

    async def set_my_commands(self, commands: list[tuple[str, str]]) -> None:
        """Replaces the bot's command menu (the list clients show after typing "/")."""
        payload = [{"command": name, "description": description} for name, description in commands]
        await self.call("setMyCommands", {"commands": json.dumps(payload)})
