"""Tool calls as an OpenAI-compatible stream sends them: in fragments keyed by index, the
id and name in one delta and the arguments spread over many."""

from __future__ import annotations

import json
import uuid
from typing import Any

from my_agent_crew.llm.types import ToolCall, ToolCallDelta

# How much of the arguments around the break is quoted back: enough to recognise the spot,
# little enough that a long broken document is never echoed into the history.
_BEFORE, _AFTER = 40, 20
_JSON_TYPES = {list: "array", str: "string", int: "number", float: "number", bool: "boolean"}
# Opens the diagnosis of the call that was still being written when the reply hit the
# model's output limit. Sending that call again word for word breaks at the same place,
# so the agent layer answers it with "split it" rather than "send it again".
CUT_OFF = "cut off at the output limit; "


class ToolCallBuffer:
    """Assembles fragmented tool_call deltas keyed by their stream index."""

    def __init__(self) -> None:
        self._parts: dict[int, dict[str, str]] = {}

    def feed(self, deltas: list[dict[str, Any]]) -> list[ToolCallDelta]:
        """Takes the deltas in and hands back the pieces of arguments they brought, each
        with its call's index and the name assembled for that call so far. A delta that
        brought only an id or a name is no piece. A name or arguments that are not text
        are a broken stream, said as the error the provider already turns into its own."""
        pieces = []
        for d in deltas:
            index = d.get("index", 0)
            slot = self._parts.setdefault(index, {"id": "", "name": "", "args": ""})
            slot["id"] = d.get("id") or slot["id"]
            fn = d.get("function") or {}
            name, chunk = fn.get("name") or "", fn.get("arguments") or ""
            if not isinstance(name, str) or not isinstance(chunk, str):
                raise ValueError("a tool call's name or arguments are not text")
            slot["name"] = name or slot["name"]
            slot["args"] += chunk
            if chunk:
                pieces.append(ToolCallDelta(index=index, name=slot["name"], chunk=chunk))
        return pieces

    def calls(self, cut_off: bool = False) -> tuple[ToolCall, ...]:
        """`cut_off` says the reply stopped at the output limit. Only the last call can have
        been interrupted by that; an earlier one that broke, broke on its own."""
        calls = []
        last = max(self._parts, default=None)
        for index in sorted(self._parts):
            slot = self._parts[index]
            arguments, invalid = parse_arguments(slot["args"] or "{}")
            if invalid and cut_off and index == last:
                invalid = CUT_OFF + invalid
            calls.append(
                ToolCall(
                    id=slot["id"] or f"call_{uuid.uuid4().hex}",
                    name=slot["name"],
                    arguments=arguments,
                    invalid=invalid,
                )
            )
        return tuple(calls)


def parse_arguments(raw: str) -> tuple[dict[str, Any], str]:
    """The arguments as an object, or `{}` and why they are not one. A long document written
    into one argument is where models break JSON most, with a raw line break, an unescaped
    quote or output cut off mid-call; saying where lets the model send the call again
    instead of the whole run failing."""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        n = len(raw)
        if _ran_out(raw, exc):
            return {}, f"{n} chars; cut off at char {n}; ends with {_shown(raw, n)}"
        # Some of Python's messages already end in "at" ("Invalid control character at").
        why = exc.msg.removesuffix(" at")
        return {}, f"{n} chars; {why} at char {exc.pos}; near {_shown(raw, exc.pos + _AFTER)}"
    if not isinstance(value, dict):
        return {}, f"{len(raw)} chars; JSON {_JSON_TYPES.get(type(value), 'null')}, not an object"
    return value, ""


def _ran_out(raw: str, exc: json.JSONDecodeError) -> bool:
    """The text ended before the JSON did. Python names where the unfinished string began,
    which for a cut-off document is thousands of characters before where it stopped."""
    if exc.msg.startswith("Unterminated string") or exc.pos >= len(raw):
        return True
    return exc.msg.startswith("Invalid \\uXXXX") and exc.pos + 5 >= len(raw)


def _shown(text: str, end: int) -> str:
    """The last `_BEFORE + _AFTER` characters before `end`, as sent but with control
    characters spelled out: a raw line break inside a string is what broke the JSON, so it
    must not read like the `\\n` escape it should have been."""
    tail = text[max(0, end - _BEFORE - _AFTER) : end]
    return "".join(f"<U+{ord(ch):04X}>" if ord(ch) < 0x20 else ch for ch in tail)
