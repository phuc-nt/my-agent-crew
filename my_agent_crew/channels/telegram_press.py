"""A press on a decision button (`telegram_buttons`): the request it names is settled, and
the message it was pressed under says how, its buttons gone so it cannot be pressed twice.

Only a press in the configured chat counts, on a request of the chat's own conversations or
of one they delegated to (`telegram_approvals.in_chat`). A request settled already, by an
earlier press, by `/approve`, on the web or by its expiry, is left as it is and the press
told so: the buttons of an old message stay on the screen long after they mean anything."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import TELEGRAM
from my_agent_crew.channels.telegram_api import TelegramError
from my_agent_crew.channels.telegram_approvals import in_chat, resume
from my_agent_crew.channels.telegram_buttons import Press, read_press
from my_agent_crew.inbound import InboundBusy
from my_agent_crew.store.approvals import PENDING
from my_agent_crew.store.models import QUESTION

if TYPE_CHECKING:
    from my_agent_crew.channels.telegram_channel import TelegramChannel

logger = logging.getLogger(__name__)
NO_BUTTONS = '{"inline_keyboard": []}'


async def handle_press(channel: TelegramChannel, query: dict[str, Any]) -> None:
    message = query.get("message") or {}
    chat = (message.get("chat") or {}).get("id")
    if chat != channel.chat_id:
        logger.info("telegram: ignored a button pressed in chat %s", chat)
        return
    press = read_press(str(query.get("data") or ""))
    said = texts.TELEGRAM_PRESS_SETTLED if press is None else settle(channel, press)
    await _close(channel, str(query.get("id") or ""), message, said)


def settle(channel: TelegramChannel, press: Press) -> str:
    """Decides or answers the request the press names; the line saying what was done."""
    store = channel.store
    try:
        approval = store.approvals.get(press.approval_id)
        conv = store.get(approval.conversation_id)
    except KeyError:
        return texts.TELEGRAM_PRESS_SETTLED
    if approval.status != PENDING or not in_chat(channel, conv):
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
    line keeps its text and only loses the buttons."""
    api, chat, message_id = channel.api, channel.chat_id, message.get("message_id")
    try:
        await api.call("answerCallbackQuery", {"callback_query_id": query_id, "text": said})
        if message_id is None:
            return
        where = {"chat_id": chat, "message_id": message_id}
        text = f"{message.get('text') or ''}\n\n{said}".strip()
        try:
            await api.call("editMessageText", {**where, "text": text})
        except TelegramError:
            await api.call("editMessageReplyMarkup", {**where, "reply_markup": NO_BUTTONS})
    except TelegramError as exc:
        logger.warning("telegram %s: a press was not answered: %s", channel.agent_id, exc)
