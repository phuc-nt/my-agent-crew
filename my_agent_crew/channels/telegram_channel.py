"""One agent's Telegram channel. Messages from the configured chat become turns of a
per-day conversation (`channel = "telegram:<chat_id>"`), so the web UI shows them like
any other run; `deliver` pushes the last reply of a conversation (a scheduled brief) to
the same chat. Only one process may poll a bot: a 409 means another poller is alive."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    AssistantMessageEvent,
    ErrorEvent,
    HaltedEvent,
)
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.channels.telegram_api import (
    CONFLICT_STATUS,
    TelegramApi,
    TelegramError,
    split_reply,
)
from my_agent_crew.store import Conversation
from my_agent_crew.store.models import AWAITING_APPROVAL
from my_agent_crew.tools.registry import ToolError
from my_agent_crew.tools.workspace import resolve_inside

logger = logging.getLogger(__name__)
SOURCE = "telegram"
RETRY_SECONDS = 5
NEW_CONVERSATION_COMMANDS = ("/new", "/start")


def channel_key(chat_id: int) -> str:
    return f"telegram:{chat_id}"


class TelegramChannel:
    def __init__(
        self,
        deps: AgentDeps,
        hub: ActivityHub,
        api: TelegramApi,
        chat_id: int,
        offset_path: Path,
        clock: Any = datetime.now,
    ):
        self._deps = deps
        self._hub = hub
        self._api = api
        self.chat_id = chat_id
        self._offset_path = offset_path
        self._clock = clock
        self._offset = self._load_offset()
        self._task: asyncio.Task[None] | None = None

    @property
    def agent_id(self) -> str:
        return self._deps.agent.id

    # --- polling -------------------------------------------------------------------------

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.poll_once()
                continue
            except TelegramError as exc:
                if exc.status == CONFLICT_STATUS:
                    logger.warning("telegram %s: another poller holds this bot", self.agent_id)
                else:
                    logger.warning("telegram %s: %s", self.agent_id, exc)
            except Exception:
                logger.exception("telegram %s: update failed", self.agent_id)
            await asyncio.sleep(RETRY_SECONDS)

    async def poll_once(self) -> int:
        """Fetches pending updates and handles each; the offset moves before handling so a
        message that crashes the handler is not replayed forever."""
        updates = await self._api.get_updates(self._offset)
        for update in updates:
            self._offset = int(update["update_id"]) + 1
            self._save_offset()
            await self.handle(update)
        return len(updates)

    def _load_offset(self) -> int:
        try:
            return int(self._offset_path.read_text().strip() or 0)
        except (OSError, ValueError):
            return 0

    def _save_offset(self) -> None:
        self._offset_path.parent.mkdir(parents=True, exist_ok=True)
        self._offset_path.write_text(str(self._offset))

    # --- inbound ---------------------------------------------------------------------------

    async def handle(self, update: dict[str, Any]) -> None:
        message = update.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        text = message.get("text")
        if chat_id != self.chat_id or not text:
            logger.info("telegram %s: ignored update from chat %s", self.agent_id, chat_id)
            return
        logger.info("telegram %s: message of %d chars", self.agent_id, len(text))
        if text.strip() in NEW_CONVERSATION_COMMANDS:
            self._open()
            await self._api.send_message(self.chat_id, texts.TELEGRAM_NEW_CONVERSATION)
            return
        conv = self.conversation()
        if conv.status == AWAITING_APPROVAL:
            await self._api.send_message(self.chat_id, texts.TELEGRAM_BUSY)
            return
        await self._send(await self._run(conv, text))

    def conversation(self) -> Conversation:
        """Today's conversation on this chat, opened on first use each day."""
        latest = self._deps.store.latest_for_channel(self.agent_id, channel_key(self.chat_id))
        today = self._clock().date()
        if latest is None or datetime.fromisoformat(latest.created_at).astimezone().date() != today:
            return self._open()
        return latest

    def _open(self) -> Conversation:
        settings = self._deps.settings
        return self._deps.store.create(
            title=texts.TELEGRAM_CONVERSATION_TITLE.format(date=self._clock().date().isoformat()),
            autonomous=settings.autonomous_default,
            cost_cap_usd=settings.cost_cap_usd,
            agent_id=self.agent_id,
            channel=channel_key(self.chat_id),
        )

    async def _run(self, conv: Conversation, text: str) -> str:
        events = run_turn(self._deps, conv.id, text)
        reply, notices = "", []
        async for event in tracked(self._hub, events, self.agent_id, SOURCE, conv.title, conv.id):
            if isinstance(event, AssistantMessageEvent) and not event.tool_calls:
                reply = event.content
            elif isinstance(event, HaltedEvent):
                notices.append(
                    texts.TELEGRAM_HALTED.format(reason=event.reason, spent=event.spent_usd)
                )
            elif isinstance(event, ErrorEvent):
                notices.append(texts.TELEGRAM_ERROR.format(message=event.message))
            elif isinstance(event, ApprovalRequiredEvent):
                notices.append(texts.TELEGRAM_APPROVAL.format(name=event.name))
        return "\n".join(part for part in (reply, *notices) if part)

    # --- outbound --------------------------------------------------------------------------

    async def deliver(self, conv_id: str) -> bool:
        """Sends the last final reply of a conversation; False when there is none yet."""
        for stored in reversed(self._deps.store.history(conv_id)):
            message = stored.message
            if message.role == "assistant" and not message.tool_calls:
                await self._send(message.content)
                return True
        return False

    async def _send(self, text: str) -> None:
        prose, media = split_reply(text)
        if prose:
            await self._api.send_message(self.chat_id, prose)
            logger.info("telegram %s: sent %d chars", self.agent_id, len(prose))
        for relative in media:
            try:
                path = resolve_inside(self._deps.agent.workspace, relative)
                if not path.is_file():
                    raise ToolError(texts.WORKSPACE_NOT_FOUND.format(path=relative))
                await self._api.send_photo(self.chat_id, path)
                logger.info("telegram %s: sent photo %s", self.agent_id, relative)
            except (ToolError, OSError, TelegramError) as exc:
                logger.warning("telegram %s: photo %s: %s", self.agent_id, relative, exc)
                await self._api.send_message(
                    self.chat_id, texts.TELEGRAM_MEDIA_MISSING.format(path=relative)
                )
