"""The requests the chat was shown with buttons, followed until they are settled.

A request can be settled away from its message: on the web, by `/approve`, or by its own
deadline. Its buttons would then stay on the screen, inviting a press that can only be told
"settled already". Every message sent with a request's buttons is kept here by the request's
id, and a sweep rewrites it once the request no longer waits: the message says how it was
settled, and its buttons go. A request still waiting a while after it was first told is
reminded of once, in reply to its message, with the time it runs out.

What is kept is written to the store too (`store/telegram_told.py`) and read back when the
channel starts: a host that sleeps when idle starts the process again on every wake, and a
request told before the sleep is still closed, and reminded of once, after it."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts
from my_agent_crew.channels.telegram_api import TelegramError
from my_agent_crew.channels.telegram_buttons import local_time, pressed_request
from my_agent_crew.store.approvals import ANSWERED, APPROVED, DENIED, EXPIRED, PENDING
from my_agent_crew.store.models import Approval
from my_agent_crew.store.telegram_told import ToldStore
from my_agent_crew.texts_approval import DECIDED_VIA

if TYPE_CHECKING:
    from my_agent_crew.channels.telegram_channel import TelegramChannel

logger = logging.getLogger(__name__)
SWEEP_SECONDS = 15.0
REMIND_AFTER = timedelta(minutes=3)
NO_BUTTONS = '{"inline_keyboard": []}'
REMINDER_NAME_CHARS = 80
_SETTLED = {
    APPROVED: texts.TELEGRAM_SETTLED_APPROVED,
    DENIED: texts.TELEGRAM_SETTLED_DENIED,
    ANSWERED: texts.TELEGRAM_SETTLED_ANSWERED,
    EXPIRED: texts.TELEGRAM_SETTLED_EXPIRED,
}


@dataclass
class Told:
    """The messages one request was told in, and when it was first told."""

    at: datetime
    messages: dict[int, str] = field(default_factory=dict)  # message id -> its text
    reminded: bool = False


class ToldRequests:
    def __init__(self, clock: Any = None, kept: ToldStore | None = None, owner: str = ""):
        """`kept` is where the messages outlive the process, under `owner`: the agent the
        chat talks to. Without it they live as long as this object does."""
        self._told: dict[str, Told] = {}
        self._clock = clock or (lambda: datetime.now(UTC))
        self._kept, self._owner = kept, owner
        for row in kept.all(owner) if kept is not None else ():
            at = datetime.fromisoformat(row["told_at"])
            told = self._told.setdefault(row["approval_id"], Told(at))
            told.messages[row["message_id"]] = row["text"]
            told.reminded = told.reminded or bool(row["reminded"])

    def record(self, buttons: dict[str, Any] | None, sent: dict[str, Any], text: str) -> None:
        """A message just sent with a request's buttons. Telegram's copy of the text is kept
        when it gives one: a long message was split, and the buttons sit under the last part."""
        rid, message_id = pressed_request(buttons), sent.get("message_id")
        if not rid or not isinstance(message_id, int):
            return
        told = self._told.setdefault(rid, Told(self._clock()))
        told.messages[message_id] = str(sent.get("text") or text)
        if self._kept is not None:
            at, kept = told.at.isoformat(), told.messages[message_id]
            self._kept.put(self._owner, rid, message_id, kept, at)
            if told.reminded:  # a message told after the reminder is of a reminded request
                self._kept.reminded(self._owner, rid)

    def forget(self, approval_id: str, message_id: int | None = None) -> None:
        """One message of a request closed by a press under it, or all of them."""
        told = self._told.get(approval_id)
        if told is not None and message_id is not None:
            told.messages.pop(message_id, None)
        whole = told is None or message_id is None or not told.messages
        if whole:
            self._told.pop(approval_id, None)
        if self._kept is not None:
            self._kept.forget(self._owner, approval_id, None if whole else message_id)

    def __contains__(self, approval_id: str) -> bool:
        return approval_id in self._told

    async def sweep(self, channel: TelegramChannel) -> None:
        """Closes the messages of every request settled since, and reminds of the ones still
        waiting long enough. What Telegram refuses is logged and not tried again."""
        for rid, told in list(self._told.items()):
            try:
                approval = channel.store.approvals.get(rid)
            except KeyError:
                self.forget(rid)
                continue
            try:
                if approval.status != PENDING:
                    self.forget(rid)
                    line = settled_line(approval)
                    for message_id, text in told.messages.items():
                        await close_message(channel, message_id, f"{text}\n\n{line}".strip())
                elif not told.reminded and self._clock() - told.at >= REMIND_AFTER:
                    told.reminded = True
                    if self._kept is not None:
                        self._kept.reminded(self._owner, rid)
                    await remind(channel, approval, max(told.messages))
            except TelegramError as exc:
                logger.warning(
                    "telegram %s: request %s not followed: %s", channel.agent_id, rid, exc
                )


def settled_line(approval: Approval) -> str:
    """How a request stopped waiting, and where, when a person settled it."""
    words = DECIDED_VIA.get(approval.decided_via, "")
    via = f" {words}" if words else ""
    template = _SETTLED.get(approval.status, texts.TELEGRAM_PRESS_SETTLED)
    return template.format(via=via, answer=approval.answer or "")


async def close_message(channel: TelegramChannel, message_id: int, text: str) -> None:
    """Rewrites a request's message with what came of it, its buttons gone. One too long to
    take the line keeps its text and only loses the buttons."""
    where = {"chat_id": channel.chat_id, "message_id": message_id}
    try:
        await channel.api.call("editMessageText", {**where, "text": text})
    except TelegramError:
        await channel.api.call("editMessageReplyMarkup", {**where, "reply_markup": NO_BUTTONS})


async def remind(channel: TelegramChannel, approval: Approval, message_id: int) -> None:
    """Once, under the request's latest message: it still waits, and until when."""
    if not approval.expires_at:
        return
    name = approval.question or approval.tool_name
    if len(name) > REMINDER_NAME_CHARS:
        name = name[: REMINDER_NAME_CHARS - 1] + "…"
    when = local_time(approval.expires_at, channel.deps.settings.zone)
    text = texts.TELEGRAM_APPROVAL_REMINDER.format(name=name, time=when)
    await channel.api.send_message(channel.chat_id, text, reply_to_message_id=message_id)


async def sweep_forever(channel: TelegramChannel, every: float = SWEEP_SECONDS) -> None:
    """Runs while the channel does."""
    while True:
        await asyncio.sleep(every)
        try:
            await channel.told.sweep(channel)
        except Exception:  # a broken sweep must not stop the next one
            logger.exception("telegram %s: request sweep failed", channel.agent_id)
