"""A press on a decision button (`telegram_buttons`): the request it names is settled, and
the message it was pressed under says how, its buttons gone so it cannot be pressed twice.

Only a press in the configured chat counts, on a request the chat is told of
(`telegram_approvals.told_of`): its own, a delegated child's, a job's. A request settled
already, by an earlier press, by `/approve`, on the web or by its expiry, is left as it is
and the press told so: the buttons of an old message stay on the screen long after they
mean anything."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import TELEGRAM
from my_agent_crew.channels.telegram_api import TelegramError
from my_agent_crew.channels.telegram_approvals import resume, told_of
from my_agent_crew.channels.telegram_buttons import Press, read_press
from my_agent_crew.channels.telegram_told import close_message
from my_agent_crew.inbound import InboundBusy
from my_agent_crew.store.approvals import PENDING
from my_agent_crew.store.models import QUESTION

if TYPE_CHECKING:
    from my_agent_crew.channels.telegram_channel import TelegramChannel

logger = logging.getLogger(__name__)


async def handle_press(channel: TelegramChannel, query: dict[str, Any]) -> None:
    message = query.get("message") or {}
    chat = (message.get("chat") or {}).get("id")
    if chat != channel.chat_id:
        logger.info("telegram: ignored a button pressed in chat %s", chat)
        return
    press = read_press(str(query.get("data") or ""))
    said = texts.TELEGRAM_PRESS_SETTLED if press is None else settle(channel, press)
    if press is not None:  # this message is closed here; the sweep closes any other
        channel.told.forget(press.approval_id, message.get("message_id"))
    await _close(channel, str(query.get("id") or ""), message, said)


def settle(channel: TelegramChannel, press: Press) -> str:
    """Decides or answers the request the press names; the line saying what was done."""
    store = channel.store
    try:
        approval = store.approvals.get(press.approval_id)
        conv = store.get(approval.conversation_id)
    except KeyError:
        return texts.TELEGRAM_PRESS_SETTLED
    if approval.status != PENDING or not told_of(channel, conv):
        return texts.TELEGRAM_PRESS_SETTLED
    is_question = approval.kind == QUESTION
    if is_question != bool(press.choice) or press.choice > len(approval.options):
        return texts.TELEGRAM_PRESS_SETTLED  # a press that does not fit its request
    try:
        if is_question:
            answer = approval.options[press.choice - 1]
            events = channel.inbound.answer(conv.id, approval.id, answer, source=TELEGRAM)
            said = texts.TELEGRAM_PRESS_ANSWERED.format(answer=answer)
        else:
            events = channel.inbound.decide(conv.id, approval.id, press.approve, source=TELEGRAM)
            said = texts.TELEGRAM_PRESS_APPROVED if press.approve else texts.TELEGRAM_PRESS_DENIED
    except InboundBusy:  # a decision taken a moment ago holds it, still unapplied
        return texts.TELEGRAM_PRESS_SETTLED
    resume(channel, conv, events)
    return said


async def _close(
    channel: TelegramChannel, query_id: str, message: dict[str, Any], said: str
) -> None:
    """Answers the press (Telegram shows a spinner until then) and rewrites the message it was
    pressed under with what was done instead of its buttons. A message too long to take the
    line keeps its text and only loses the buttons. Each step goes on without the other: a
    press that woke a sleeping host is too old for Telegram to answer, yet its message still
    has to lose its buttons."""
    try:
        answer = {"callback_query_id": query_id, "text": said}
        await channel.api.call("answerCallbackQuery", answer)
    except TelegramError as exc:
        logger.warning("telegram %s: a press was not answered: %s", channel.agent_id, exc)
    message_id = message.get("message_id")
    if message_id is None:
        return
    try:
        text = f"{message.get('text') or ''}\n\n{said}".strip()
        await close_message(channel, message_id, text)
    except TelegramError as exc:
        logger.warning("telegram %s: a pressed message kept its buttons: %s", channel.agent_id, exc)
