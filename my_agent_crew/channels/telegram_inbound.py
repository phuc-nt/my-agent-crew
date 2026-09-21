"""Telegram updates, from the wire to the agent: the chat filter, the `@id` mention,
slash commands, and attachments. A photo or a document the person sends is downloaded
into `<workspace>/inbox/` and the agent reads the saved paths in place of the message, with
the caption after them — the model has no eyes here, but a script or a `cp` can take it
from there (a paper into the ledger's inbox, a receipt onto Drive). An album arrives as
several updates handled together (see `telegram_albums`): one message, every photo."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts
from my_agent_crew.channels.telegram_api import TelegramApi, TelegramError
from my_agent_crew.channels.telegram_commands import (
    answer_command,
    bot_answers,
    parse_command,
    route_mention,
)

if TYPE_CHECKING:
    from my_agent_crew.channels.telegram_channel import TelegramChannel

logger = logging.getLogger(__name__)
INBOX_DIR = "inbox"
_UNSAFE = re.compile(r"[^\w.\-]+")


@dataclass(frozen=True)
class Attachment:
    kind: str  # "photo" or "document"
    file_id: str
    name: str  # the sender's file name for a document, empty for a photo


def find_attachment(message: dict[str, Any]) -> Attachment | None:
    """The one file of a message: the largest size of a photo (Telegram lists them
    smallest first), or a document with the name the person gave it."""
    sizes = message.get("photo") or []
    if sizes:
        return Attachment("photo", str(sizes[-1].get("file_id") or ""), "")
    document = message.get("document") or {}
    if document.get("file_id"):
        name = str(document.get("file_name") or "")
        return Attachment("document", str(document["file_id"]), name)
    return None


def message_text(message: dict[str, Any]) -> str:
    return str(message.get("text") or message.get("caption") or "")


def attachment_path(inbox: Path, attachment: Attachment, remote_name: str, now: datetime) -> Path:
    """`inbox/<timestamp>-<name>`: the timestamp keeps two photos from one minute apart,
    the name is the sender's when there is one, else Telegram's own. Both are reduced to
    a plain file name so a crafted `file_name` cannot leave the inbox."""
    plain = _UNSAFE.sub("_", Path(attachment.name or remote_name).name).strip("._")
    return inbox / f"{now:%Y%m%d-%H%M%S}-{plain or attachment.kind}"


async def save_attachment(
    api: TelegramApi, attachment: Attachment, inbox: Path, now: datetime
) -> Path:
    remote = await api.file_path(attachment.file_id)
    path = attachment_path(inbox, attachment, Path(remote).name, now)
    return await api.download_file(remote, path)


async def handle_update(channel: TelegramChannel, update: dict[str, Any]) -> None:
    await handle_updates(channel, [update])


async def handle_updates(channel: TelegramChannel, updates: list[dict[str, Any]]) -> None:
    """One message to the agent: a single update, or the updates of one album, whose
    caption sits on whichever photo carried it."""
    messages = [update.get("message") or {} for update in updates]
    chat_ids = {(message.get("chat") or {}).get("id") for message in messages}
    text = next((t for t in map(message_text, messages) if t), "")
    attachments = [a for a in map(find_attachment, messages) if a is not None]
    if chat_ids != {channel.chat_id} or not (text or attachments):
        logger.info("telegram %s: ignored update from chat %s", channel.label, chat_ids)
        return
    logger.info(
        "telegram %s: message of %d chars, %d files", channel.label, len(text), len(attachments)
    )
    agent_id, text, addressed = await route_mention(channel, text)
    if agent_id is None:
        return
    if attachments:
        return await receive_attachments(channel, agent_id, attachments, text)
    command = parse_command(text)
    if command is None:
        await channel.chat(agent_id, text)
        return
    answer = await answer_command(channel, agent_id, command, addressed)
    if bot_answers(channel, command, addressed):
        await channel.say(answer)
    else:
        await channel.outbound(agent_id).send(answer)


async def receive_attachments(
    channel: TelegramChannel, agent_id: str, attachments: list[Attachment], caption: str
) -> None:
    """Every file saved, then one turn naming them all. A download that fails stops the
    whole message: half an album with no word about the rest would mislead the agent."""
    inbox = channel.agents[agent_id].agent.workspace / INBOX_DIR
    now = channel.now()  # one stamp for the album; the file names still differ
    paths: list[Path] = []
    for attachment in attachments:
        try:
            paths.append(await save_attachment(channel.api, attachment, inbox, now))
        except TelegramError as exc:
            logger.warning(
                "telegram %s: %s download failed: %s", channel.label, attachment.kind, exc
            )
            return await channel.say(texts.TELEGRAM_ATTACHMENT_FAILED.format(error=exc))
        logger.info("telegram %s: %s saved as %s", channel.label, attachment.kind, paths[-1].name)
    files = "\n".join(texts.TELEGRAM_ATTACHMENT_LINE.format(path=path) for path in paths)
    text = texts.TELEGRAM_ATTACHMENT.format(files=files, caption=caption).rstrip()
    await channel.chat(agent_id, text)
