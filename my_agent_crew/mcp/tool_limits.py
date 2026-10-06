"""How much of what a server lists is taken.

A server is someone else's program. What it lists is held by every agent given it, and a
tool told up front is sent whole with every request to the model. Past these sizes a tool
is left out and named on its server's row, and a server that lists more tools than any
agent could use is not taken at all.
"""

from __future__ import annotations

import json
from typing import Any

MAX_TOOLS = 1000
# What the protocol asks of a tool's name. A longer one is no name to show or to send back.
MAX_REMOTE_CHARS = 128
# The JSON of a tool's parameters, in letters.
MAX_SCHEMA_CHARS = 50_000
# A name too long to keep, where it is named as left out.
SHOWN_CHARS = 60

NAME_TAKEN = "its name is taken"
NAME_TOO_LONG = "its name is too long"
SCHEMA_TOO_LARGE = "its parameters are too large"


def shown(remote: str) -> str:
    return remote if len(remote) <= MAX_REMOTE_CHARS else remote[: SHOWN_CHARS - 1] + "…"


def unfit(remote: str, schema: dict[str, Any]) -> str:
    """Why a tool is more than is taken; empty when it is not."""
    if len(remote) > MAX_REMOTE_CHARS:
        return NAME_TOO_LONG
    try:
        size = len(json.dumps(schema, ensure_ascii=False))
    except RecursionError:
        # Nested deeper than can be written out again, which sending it would have to do.
        return SCHEMA_TOO_LARGE
    return SCHEMA_TOO_LARGE if size > MAX_SCHEMA_CHARS else ""
