"""Reading a Telegram voice note or audio file: what it is, whether it is worth
downloading, and what a transcription model says it heard.

Kept apart from `telegram_inbound` (which imports this module) so nothing here needs to
import back into it — `find_voice` and the checks below run before any file is fetched.
`audio_chain` is built here rather than in `server/agent_assembly` for the same reason a
channel never imports `server/`: it reads straight off the deps a running channel already
holds, so a route added after startup (`use_agents`) takes effect on the next voice note
with no wiring anywhere else.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from my_agent_crew.config import Route, Settings
from my_agent_crew.llm.provider import Provider, ProviderChain, ProviderError
from my_agent_crew.llm.types import AudioPart, Completion, Message
from my_agent_crew.texts_telegram import (
    TELEGRAM_VOICE_FORMAT,
    TELEGRAM_VOICE_TOO_BIG,
    TELEGRAM_VOICE_TOO_LONG,
    TRANSCRIBE_SYSTEM,
    VOICE_REASON_ROUTE_ERROR,
    VOICE_REASON_TIMEOUT,
    VOICE_REASON_UNCLEAR,
)

logger = logging.getLogger(__name__)

# A voice note past this many seconds is refused before it is downloaded: metadata gives
# the duration for free, and a long clip is likely a recording, not a message.
MAX_VOICE_SECONDS = 300
# The Bot API's own file cap is 20 MB; this is a tighter, private one so a clip that does
# get downloaded still fits an `input_audio` part after base64 grows it by roughly 4/3.
MAX_VOICE_BYTES = 10 * 1024 * 1024
# Below the provider's own 120s (`llm/runtime.py`) and the channel's 30s stop grace
# (`telegram_polling.py`), so a stuck transcription is cut off before either would be.
TRANSCRIBE_TIMEOUT_SECONDS = 25.0
NOT_HEARD = "[không nghe rõ]"

# `message.audio`'s mime type, then its file name's suffix, mapped to the OpenRouter
# `input_audio` format string. `message.voice` is always OGG/Opus and needs no lookup.
_AUDIO_MIME_FORMATS = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/flac": "flac",
    "audio/aac": "aac",
}
_AUDIO_SUFFIX_FORMATS = {
    ".mp3": "mp3",
    ".m4a": "m4a",
    ".oga": "ogg",
    ".ogg": "ogg",
    ".opus": "ogg",
    ".wav": "wav",
    ".flac": "flac",
    ".aac": "aac",
}


@dataclass(frozen=True)
class VoicePart:
    """One voice note or audio file from a Telegram message, before it is downloaded.
    `format` is the OpenRouter `input_audio` format, or None when it could not be told
    from the message's mime type or file name."""

    file_id: str
    duration: float
    size: int
    format: str | None
    name: str


def _audio_format(audio: dict[str, Any]) -> str | None:
    mime = str(audio.get("mime_type") or "").lower()
    if mime in _AUDIO_MIME_FORMATS:
        return _AUDIO_MIME_FORMATS[mime]
    suffix = Path(str(audio.get("file_name") or "")).suffix.lower()
    return _AUDIO_SUFFIX_FORMATS.get(suffix)


def find_voice(message: dict[str, Any]) -> VoicePart | None:
    """The one voice note or audio file of a message, or None for a message with neither
    (a photo, a document, plain text) or one missing the `file_id` a real message always
    carries."""
    voice = message.get("voice") or {}
    if voice.get("file_id"):
        return VoicePart(
            file_id=str(voice["file_id"]),
            duration=float(voice.get("duration") or 0),
            size=int(voice.get("file_size") or 0),
            format="ogg",
            name="",
        )
    audio = message.get("audio") or {}
    if audio.get("file_id"):
        return VoicePart(
            file_id=str(audio["file_id"]),
            duration=float(audio.get("duration") or 0),
            size=int(audio.get("file_size") or 0),
            format=_audio_format(audio),
            name=str(audio.get("file_name") or ""),
        )
    return None


def refusal(voice: VoicePart) -> str | None:
    """Why this voice note is not worth downloading, from its metadata alone — or None
    when it passes every cheap check. A missing duration or size (Telegram does not
    always send them) reads as zero, which never trips these, so the real gate against an
    oversized file with no size metadata is the download-time check in `receive_voices`."""
    if voice.duration > MAX_VOICE_SECONDS:
        return TELEGRAM_VOICE_TOO_LONG.format(seconds=voice.duration, limit=MAX_VOICE_SECONDS)
    if voice.size > MAX_VOICE_BYTES:
        mb = 1024 * 1024
        return TELEGRAM_VOICE_TOO_BIG.format(size=voice.size / mb, limit=MAX_VOICE_BYTES / mb)
    if voice.format is None:
        return TELEGRAM_VOICE_FORMAT
    return None


def audio_chain(settings: Settings, providers: dict[str, Provider]) -> ProviderChain | None:
    """The chain a voice note's audio is sent to for transcription, or None when no
    configured audio route has its provider built (no key, or the setting was emptied on
    purpose) — the same rule `agent_assembly.vision_chain` applies to pictures."""
    routes: list[Route] = [r for r in settings.audio_routes if r.provider in providers]
    if not routes:
        if settings.audio_routes:
            logger.warning("no usable audio route among %s", list(settings.audio_routes))
        return None
    return ProviderChain(providers, routes)


async def transcribe(chain: ProviderChain, path: Path, fmt: str) -> str:
    """What the transcription model heard in this clip, verbatim."""
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    messages = [
        Message(role="system", content=TRANSCRIBE_SYSTEM),
        Message(role="user", content="", audio=(AudioPart(data=data, format=fmt),)),
    ]
    text = ""
    async for item in chain.stream(messages, ()):
        if isinstance(item, Completion):
            text = item.message.content
    return text.strip()


async def listen(chain: ProviderChain, path: Path, fmt: str) -> tuple[str, str | None]:
    """The transcript, and a fixed reason it failed when it did — a timeout, every route
    down, or a model that says outright it could not make out the speech. None of these
    ever carry the provider's own error text: that may quote a request or a key."""
    try:
        text = await asyncio.wait_for(
            transcribe(chain, path, fmt), timeout=TRANSCRIBE_TIMEOUT_SECONDS
        )
    except TimeoutError:
        return "", VOICE_REASON_TIMEOUT
    except ProviderError as exc:
        logger.warning("voice transcription route failed: %s", type(exc).__name__)
        return "", VOICE_REASON_ROUTE_ERROR
    if not text or text == NOT_HEARD:
        return "", VOICE_REASON_UNCLEAR
    return text, None
