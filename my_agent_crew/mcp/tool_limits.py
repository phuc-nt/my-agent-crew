"""How much of what a server lists is taken.

A server is someone else's program. What it lists is held by every agent given it, and a
tool told up front is sent whole with every request to the model. Past these sizes a tool
is left out and named on its server's row, and a server that lists more tools than any
agent could use is not taken at all.

Parameters longer than is taken are first told shorter, with what they repeat said once
(`schema_fold`), and it is that form the size is asked of. Parameters that fit are handed
on as the server wrote them, never folded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from my_agent_crew.mcp.schema_fold import fold

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


@dataclass(frozen=True)
class Folded:
    """A tool's parameters as a model is told them, where the server's own were too long:
    the same schema, and how many letters it was and is."""

    schema: dict[str, Any]
    before: int
    after: int

    def to_dict(self) -> dict[str, int]:
        return {"from": self.before, "to": self.after}


def shown(remote: str) -> str:
    return remote if len(remote) <= MAX_REMOTE_CHARS else remote[: SHOWN_CHARS - 1] + "…"


def _chars(schema: dict[str, Any]) -> int:
    return len(json.dumps(schema, ensure_ascii=False))


def unfit(remote: str, schema: dict[str, Any]) -> tuple[str, Folded | None]:
    """(why a tool is more than is taken, empty when it is not; its parameters folded, when
    it is taken only because they could be)."""
    if len(remote) > MAX_REMOTE_CHARS:
        return NAME_TOO_LONG, None
    try:
        size = _chars(schema)
    except RecursionError:
        # Nested deeper than can be written out again, which sending it would have to do.
        return SCHEMA_TOO_LARGE, None
    if size <= MAX_SCHEMA_CHARS:
        return "", None
    folded = fold(schema)
    if folded is None or (after := _chars(folded)) > MAX_SCHEMA_CHARS:
        return SCHEMA_TOO_LARGE, None
    return "", Folded(folded, size, after)
