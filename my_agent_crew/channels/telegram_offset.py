"""The `getUpdates` offset a bot has confirmed, kept in a small file so a restart does
not replay handled messages. A missing or unreadable file means "start from now"."""

from __future__ import annotations

from pathlib import Path


def read_offset(path: Path) -> int:
    try:
        return int(path.read_text().strip() or 0)
    except (OSError, ValueError):
        return 0


def write_offset(path: Path, offset: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(offset))
