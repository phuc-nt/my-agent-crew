"""What an agent id may look like. An id is a directory name, a URL segment and the tail of a
canvas author ("agent:<id>") at once, so it is kept to the characters that are safe in all of
them rather than escaped at every use."""

from __future__ import annotations

import re

AGENT_ID_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


def is_agent_id(value: str) -> bool:
    """The whole value, so a trailing newline is refused too, which `$` would let through."""
    return AGENT_ID_RE.fullmatch(value) is not None
