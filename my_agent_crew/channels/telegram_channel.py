"""One agent's Telegram channel. Messages from the configured chat become turns of a
per-day conversation (`channel = "telegram:<chat_id>"`), so the web UI shows them like
any other run; the chat shows "typing…" while the turn runs. Slash commands are answered
by `telegram_commands` without a model call. `deliver` pushes the last reply of a
conversation (a scheduled brief) to the same chat. Only one process may poll a bot: a 409
means another poller is alive."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    AssistantMessageEvent,
    ErrorEvent,
    Event,
    HaltedEvent,
)
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.channels.telegram_api import CONFLICT_STATUS, TelegramApi, TelegramError
from my_agent_crew.channels.telegram_commands import MENU, answer_command, parse_command
from my_agent_crew.channels.telegram_outbound import TelegramOutbound
from my_agent_crew.store import Conversation
from my_agent_crew.store.models import AWAITING_APPROVAL

logger = logging.getLogger(__name__)
SOURCE = "telegram"
RETRY_SECONDS = 5


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
        self.deps = deps
        self.hub = hub
        self._api = api
        self.chat_id = chat_id
        self._offset_path = offset_path
        self._clock = clock
        self._outbound = TelegramOutbound(deps, api, chat_id)
        self._offset = self._load_offset()
        self._menu_registered = False
        self._task: asyncio.Task[None] | None = None

    @property
    def agent_id(self) -> str:
        return self.deps.agent.id

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
                await self.register_menu()
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

    async def register_menu(self) -> None:
        """Publishes the slash-command menu once per process; retried with the poll loop."""
        if not self._menu_registered:
            await self._api.set_my_commands(list(MENU))
            self._menu_registered = True
            logger.info("telegram %s: command menu registered", self.agent_id)

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
        command = parse_command(text)
        if command is not None:
            await self._outbound.send(await answer_command(self, command))
            return
        conv = self.conversation()
        if conv.status == AWAITING_APPROVAL:
            await self._api.send_message(self.chat_id, texts.TELEGRAM_BUSY)
            return
        await self._outbound.send(await self.turn(conv, run_turn(self.deps, conv.id, text)))

    def conversation(self) -> Conversation:
        """Today's conversation on this chat, opened on first use each day."""
        latest = self.deps.store.latest_for_channel(self.agent_id, channel_key(self.chat_id))
        today = self._clock().date()
        if latest is None or datetime.fromisoformat(latest.created_at).astimezone().date() != today:
            return self.open_conversation()
        return latest

    def open_conversation(self) -> Conversation:
        settings = self.deps.settings
        return self.deps.store.create(
            title=texts.TELEGRAM_CONVERSATION_TITLE.format(date=self._clock().date().isoformat()),
            autonomous=settings.autonomous_default,
            cost_cap_usd=settings.cost_cap_usd,
            agent_id=self.agent_id,
            channel=channel_key(self.chat_id),
        )

    async def turn(self, conv: Conversation, events: AsyncIterator[Event]) -> str:
        """Runs a turn's events with "typing…" showing and returns what the user should
        read: every piece of assistant text, including text written next to a tool call
        (models often put the answer there and finish with a bare `MEDIA:` line), plus the
        halt/error/approval notices."""
        parts: list[str] = []
        async with self._outbound.typing():
            async for event in tracked(
                self.hub, events, self.agent_id, SOURCE, conv.title, conv.id
            ):
                if isinstance(event, AssistantMessageEvent):
                    parts.append(event.content.strip())
                elif isinstance(event, HaltedEvent):
                    parts.append(
                        texts.TELEGRAM_HALTED.format(reason=event.reason, spent=event.spent_usd)
                    )
                elif isinstance(event, ErrorEvent):
                    parts.append(texts.TELEGRAM_ERROR.format(message=event.message))
                elif isinstance(event, ApprovalRequiredEvent):
                    parts.append(texts.TELEGRAM_APPROVAL.format(name=event.name))
        return "\n\n".join(part for part in parts if part)

    # --- outbound --------------------------------------------------------------------------

    async def deliver(self, conv_id: str) -> bool:
        """Sends the assistant text of a conversation's last turn; False when there is none."""
        return await self._outbound.deliver(conv_id)
