"""Sending a file out of the agent's workspace to the chat: the photo a `MEDIA:` line names
and the document a `FILE:` line names."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from my_agent_crew import texts
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.channels.telegram_api import TelegramApi, TelegramError
from my_agent_crew.channels.telegram_attachments import (
    MAX_DOCUMENT_BYTES,
    allowed_suffix_list,
    document_suffix_allowed,
)
from my_agent_crew.tools.registry import ToolError
from my_agent_crew.tools.workspace import resolve_inside

logger = logging.getLogger(__name__)


class TelegramFiles:
    def __init__(self, deps: AgentDeps, api: TelegramApi, chat_id: int):
        self._deps = deps
        self._api = api
        self._chat_id = chat_id

    async def photo(self, relative: str) -> None:
        await self._attach(relative, self._api.send_photo, "photo", texts.TELEGRAM_MEDIA_MISSING)

    async def document(self, relative: str) -> None:
        await self._attach(relative, self._send_document, "file", texts.TELEGRAM_FILE_MISSING)

    async def _attach(
        self,
        relative: str,
        upload: Callable[[int, Path], Awaitable[None]],
        label: str,
        failure: str,
    ) -> None:
        """Resolves the path inside the workspace and uploads it.

        A failure is told to the person, not raised. The attachment is the tail of a reply
        whose prose has already gone out, so an exception here would leave an answer that
        promises a file with no word about why none arrived.
        """
        agent_id = self._deps.agent.id
        try:
            path = resolve_inside(self._deps.agent.workspace, relative)
            if not path.is_file():
                raise ToolError(texts.WORKSPACE_NOT_FOUND.format(path=relative))
            await upload(self._chat_id, path)
            logger.info("telegram %s: sent %s %s", agent_id, label, relative)
        except (ToolError, OSError, TelegramError) as exc:
            logger.warning("telegram %s: %s %s: %s", agent_id, label, relative, exc)
            await self._api.send_message(self._chat_id, failure.format(path=relative))

    async def _send_document(self, chat_id: int, path: Path) -> None:
        """The two guards a photo does not need: the format, because a `FILE:` line can
        name anything the agent can write, and the size, because a chat is not a place to
        receive a hundred megabytes."""
        if not document_suffix_allowed(path.name):
            raise ToolError(texts.TELEGRAM_FILE_SUFFIX.format(kinds=allowed_suffix_list()))
        size = path.stat().st_size
        if size > MAX_DOCUMENT_BYTES:
            raise ToolError(
                texts.TELEGRAM_FILE_TOO_BIG.format(
                    size=size / 1_048_576, cap=MAX_DOCUMENT_BYTES / 1_048_576
                )
            )
        await self._api.send_document(chat_id, path)
