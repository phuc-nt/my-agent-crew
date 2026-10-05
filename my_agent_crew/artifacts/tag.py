"""The tag that opens the result of every successful canvas write. Whatever reads results
back, the payload trim, the web chat and the list a Telegram chat is sent of what a turn
wrote, recognises a write by this pattern alone."""

from __future__ import annotations

import re
from dataclasses import dataclass

TAG_RE = re.compile(r"^\[artifact ([0-9a-f]{12}) v(\d+)( unchanged)?\]")


@dataclass(frozen=True)
class Tag:
    """What a tag says: the canvas, the version the write left it at, and whether the write
    changed nothing."""

    id: str
    version: int
    unchanged: bool = False


def artifact_tag(artifact_id: str, version: int, unchanged: bool = False) -> str:
    return f"[artifact {artifact_id} v{version}{' unchanged' if unchanged else ''}]"


def parse_artifact_tag(line: str) -> Tag | None:
    """The tag `line` opens with, read back as `artifact_tag` wrote it; None when it opens
    with none."""
    match = TAG_RE.match(line)
    return Tag(match[1], int(match[2]), match[3] is not None) if match else None
