"""The `getUpdates` offset a bot has confirmed, kept in a small file so a restart does
not replay handled messages. A missing or unreadable file means "start from now".

Telegram numbers updates per bot, so the file names the bot the offset belongs to (the
part of the token before `:`). After the token is swapped for another bot's, the old
offset would make `getUpdates` skip the new bot's messages as already seen; an offset
of another bot reads as 0 instead, which is safe because Telegram forgets every update a
bot has confirmed. A bare number, as written before the bot was recorded, is trusted.
"""

from __future__ import annotations

from pathlib import Path


def read_offset(path: Path, bot: str) -> int:
    try:
        parts = path.read_text().split()
        if len(parts) == 2 and parts[0] != bot:
            return 0
        return int(parts[-1]) if parts else 0
    except (OSError, ValueError):
        return 0


def write_offset(path: Path, offset: int, bot: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{bot} {offset}")
