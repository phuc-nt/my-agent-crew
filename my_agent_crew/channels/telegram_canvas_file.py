"""Sending a canvas to the chat as a file: what an attachment line of a reply asks for when
its path is `artifact:<id>` rather than a file in the workspace.

The line is the model's text, so the canvas is held to what the agent's own canvas tools
would let it read, and one out of reach is answered like one that is not there. The file is
built in memory and nothing of it is written to disk. Text leaves with the secrets this
process knows covered, as a trajectory does; a picture cannot be searched and leaves as it is.

Nothing here raises. A canvas is the tail of a reply whose prose has already gone out, so
whatever goes wrong is one line in the chat and the next canvas is still sent.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from contextlib import suppress

from my_agent_crew import texts
from my_agent_crew.activity.redact import env_secrets, redact
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.artifacts.filenames import filename_for
from my_agent_crew.channels.telegram_api import TelegramApi, TelegramError
from my_agent_crew.channels.telegram_attachments import MAX_DOCUMENT_BYTES, document_suffix_allowed
from my_agent_crew.channels.telegram_files import tell
from my_agent_crew.store.artifact_models import ArtifactSummary, ArtifactVersion
from my_agent_crew.tools.artifact_scope import in_scope
from my_agent_crew.tools.artifact_source import SourceError, infer_kind
from my_agent_crew.tools.artifact_source_ref import parse_source

logger = logging.getLogger(__name__)
CAPTION_LIMIT = 1024  # Telegram's, for a photo and a document alike
BAD_REQUEST = 400  # how Telegram refuses a picture it will not show as a photo
# The kinds whose own extension is safe as the last one: a phone opens the first as text and
# the second as a picture, and neither runs anything.
_KEEP_EXTENSION = ("markdown", "image")


def telegram_filename(title: str, kind: str, language: str = "", data: bytes | None = None) -> str:
    """The name a canvas arrives under: the one it is saved under on the web, ending in
    `.txt` unless it is markdown or a picture, so the chat offers to read it and not to run it."""
    name = filename_for(title, kind, language, data)
    return name if kind in _KEEP_EXTENSION or name.endswith(".txt") else f"{name}.txt"


def canvas_link(web_url: str, artifact_id: str) -> str:
    """Where the web shows the canvas on a page of its own; empty when the web has no address."""
    return f"{web_url}/#/manage/canvas/{artifact_id}" if web_url else ""


def _caption(title: str, version: int, link: str) -> str:
    """The link is dropped whole when it would take the caption past Telegram's limit, which
    refuses the file along with it: half an address opens nothing."""
    caption = texts.TELEGRAM_CANVAS_CAPTION.format(title=title, version=version)
    linked = f"{caption}\n{link}"
    return linked if link and len(linked) <= CAPTION_LIMIT else caption


def _may_leave(summary: ArtifactSummary) -> bool:
    """False for text imported from a workspace file whose suffix names neither a format a
    `FILE:` line sends nor a kind of canvas. Importing as code takes any text file, a key file
    among them, and the canvas made from it is that file under another name. A picture is let
    through: importing one takes only bytes that are a picture."""
    named = parse_source(summary.source)
    if summary.kind == "image" or named is None:
        return True
    path = named[1]
    if document_suffix_allowed(path):
        return True
    try:
        infer_kind(path)
    except SourceError:
        return False
    return True


async def _upload(
    api: TelegramApi, chat_id: int, name: str, data: bytes, caption: str, as_photo: bool
) -> None:
    """A picture Telegram refuses as a photo, for its size or its shape, is sent once more as
    a document, which takes the same bytes as they are."""
    try:
        await api.send_bytes(chat_id, name, data, caption, as_photo=as_photo)
    except TelegramError as exc:
        if not as_photo or exc.status != BAD_REQUEST:
            raise
        await api.send_bytes(chat_id, name, data, caption)


def _read(
    deps: AgentDeps, artifact_id: str, conv_id: str | None
) -> tuple[ArtifactSummary, ArtifactVersion] | None:
    """The canvas and its newest version, when the agent reaches it from the conversation the
    reply belongs to. None both for a canvas out of reach and for one that is not there, so
    the chat is told the same of each and a reply cannot find out which ids exist."""
    store, agent = deps.store, deps.agent
    conversation_id = root_id = ""
    if conv_id is not None:
        with suppress(KeyError):  # deleted while the reply was on its way
            conv = store.get(conv_id)
            conversation_id, root_id = conv.id, conv.root_id
    reached = in_scope(
        store,
        artifact_id,
        agent_id=agent.id,
        is_master=agent.is_master,
        conversation_id=conversation_id,
        root_id=root_id,
    )
    if not reached:
        return None
    try:
        return store.artifacts.get(artifact_id), store.artifacts.head(artifact_id)
    except KeyError:
        return None


async def send_canvas(
    deps: AgentDeps, api: TelegramApi, chat_id: int, artifact_id: str, conv_id: str | None
) -> None:
    """Sends the newest version of one canvas, or says in the chat that it did not arrive.
    With `conv_id` None, or naming a conversation deleted since, an agent other than the
    master is left with the canvases it made itself."""
    agent_id = deps.agent.id
    found = _read(deps, artifact_id, conv_id)
    if found is None:
        await tell(api, chat_id, texts.TELEGRAM_CANVAS_MISSING.format(id=artifact_id))
        return
    summary, head = found
    if not _may_leave(summary):
        logger.warning("telegram %s: canvas %s not sent: its source file", agent_id, artifact_id)
        await tell(api, chat_id, texts.TELEGRAM_CANVAS_SOURCE.format(id=artifact_id))
        return
    secrets = env_secrets(os.environ)
    if summary.kind == "image":
        data = head.data or b""
    else:
        data = redact(head.content or "", secrets).encode("utf-8")
    title = redact(summary.title, secrets)
    name = telegram_filename(title, summary.kind, summary.language, data)
    caption = _caption(title, head.version, canvas_link(deps.settings.web_url, artifact_id))
    refusal = ""
    if len(data) > MAX_DOCUMENT_BYTES:
        refusal = f"{len(data)} bytes is over the {MAX_DOCUMENT_BYTES} a chat takes"
    else:
        try:
            await _upload(api, chat_id, name, data, caption, summary.kind == "image")
        except TelegramError as exc:
            refusal = str(exc)
    sent = f"canvas {artifact_id} v{head.version}"
    if refusal:
        # The reason stays in the log: the person is told which canvas, and where to see it.
        logger.warning("telegram %s: %s not sent: %s", agent_id, sent, refusal)
        await tell(api, chat_id, texts.TELEGRAM_CANVAS_FAILED.format(id=artifact_id))
        return
    logger.info("telegram %s: sent %s (%d bytes)", agent_id, sent, len(data))


async def send_canvases(
    deps: AgentDeps, api: TelegramApi, chat_id: int, refs: Iterable[str], conv_id: str | None
) -> None:
    """`refs` is what `artifact_ref` read from each line of one reply that names a canvas.
    A canvas named more than once is sent once. The lines that named none ("") get one notice
    between them, which repeats nothing of what they said."""
    named = list(refs)
    for artifact_id in dict.fromkeys(ref for ref in named if ref):
        await send_canvas(deps, api, chat_id, artifact_id, conv_id)
    if "" in named:
        await tell(api, chat_id, texts.TELEGRAM_CANVAS_BAD_REF)
