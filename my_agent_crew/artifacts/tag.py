"""The tag that opens the result of every successful canvas write. Whatever reads results
back, the payload trim and the web chat, recognises a write by this pattern alone."""

from __future__ import annotations

import re

TAG_RE = re.compile(r"^\[artifact ([0-9a-f]{12}) v(\d+)( unchanged)?\]")


def artifact_tag(artifact_id: str, version: int, unchanged: bool = False) -> str:
    return f"[artifact {artifact_id} v{version}{' unchanged' if unchanged else ''}]"
