"""What of an event's text and arguments a timeline row keeps: previews cut short,
because a run's steps are written to the store and re-broadcast with every later step."""

from __future__ import annotations

import json
from typing import Any

PREVIEW_CHARS = 160


def preview(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= PREVIEW_CHARS else text[:PREVIEW_CHARS] + "…"


def _argument_value(value: Any) -> Any:
    """One argument, cut to something a timeline row can show.

    Text is cut as text. Anything else is kept as it is while it is small, because the
    web renders a number or a flag better than it renders a string of one — but a list
    or a mapping has no size limit of its own, and this preview is written to the store
    and re-broadcast with every later step of the same run. One big argument would
    otherwise be paid for again on each of them.
    """
    if isinstance(value, str):
        return preview(value)
    if isinstance(value, list | dict):
        return preview(json.dumps(value, ensure_ascii=False))
    return value


def argument_preview(arguments: dict[str, Any]) -> dict[str, Any]:
    """Tool arguments kept as the mapping they are, with only long values cut down.

    Stringifying the whole mapping would have been shorter to write, but the web reads
    these as a mapping of name to value: given a string it walks the characters and shows
    one row per character. Keeping the shape means a run read back from the store renders
    the same way as one watched live.
    """
    return {key: _argument_value(value) for key, value in arguments.items()}
