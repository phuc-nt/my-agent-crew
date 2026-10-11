"""What a script keeps from one run to the next: `store(key, value)` and `load(key)`.

Both are questions put to the parent, as a lookup is (`replies.py`). The parent holds what is
kept and decides where (`store_session.py`); a script names a key and never a place.

This module is the part both sides read: the process that runs the script, and the server
that answers it. What a key and a value must be is said once, here. The process checks
before it asks, so a value that could not be written on the line is a mistake the script can
catch and not the end of the process; the server checks again, since nothing the process
sends is taken on trust for having been checked there.
"""

from __future__ import annotations

import json
from typing import Any

from my_agent_crew import texts_script_store as t
from my_agent_crew.script import limits
from my_agent_crew.script.limits import ScriptError

STORE, LOAD = "store", "load"
# The kinds of question that are about what is kept, not about the tools.
KINDS = (STORE, LOAD)


def nowhere(kind: str, arguments: dict[str, Any]) -> Any:
    """Answers both where a script has no place to keep anything."""
    raise ScriptError(t.STORE_NOWHERE)


def checked_key(key: Any) -> str:
    most = limits.MAX_STORE_KEY_CHARS
    try:
        fits = type(key) is str and 0 < len(key) <= most and key.encode("utf-8") is not None
    except UnicodeEncodeError:  # half a character pair: no text the table can hold
        fits = False
    if not fits:
        raise ScriptError(t.STORE_BAD_KEY.format(most=most))
    return key


def _keys_are_text(value: Any) -> bool:
    """JSON has only text for a key. Python writes a number as one all the same, and the
    script would read back a key it never wrote: `3 in seen` true today, false tomorrow."""
    waiting = [value]
    while waiting:
        item = waiting.pop()
        if isinstance(item, dict):
            if not all(type(key) is str for key in item):
                return False
            waiting.extend(item.values())
        elif isinstance(item, (list, tuple)):
            waiting.extend(item)
    return True


def as_text(value: Any) -> str:
    """The value as the JSON text that is kept, or a `ScriptError` for one that is not JSON
    or is too long. `NaN` is refused with the rest: it is no JSON another reader takes."""
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        text.encode("utf-8")
        plain = _keys_are_text(value)  # after the writing, which has refused what holds itself
    except (TypeError, ValueError, RecursionError) as exc:
        raise ScriptError(t.STORE_NOT_JSON) from exc
    if not plain:
        raise ScriptError(t.STORE_NOT_JSON)
    most = limits.MAX_STORE_VALUE_CHARS
    if len(text) > most:
        raise ScriptError(t.STORE_VALUE_TOO_LONG.format(size=len(text), most=most))
    return text
