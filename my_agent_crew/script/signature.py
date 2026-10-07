"""A tool as a model reads it before a script calls it: a line to call it by, and in full.

What a tool is called with is its server's to write, and a model reads it as it stands. So
only plain names are shown, and everything written of a parameter is cut to one short line:
nothing a server wrote can start a line of its own.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from itertools import chain
from typing import Any

from my_agent_crew import texts_script as t
from my_agent_crew.mcp.tool_search import MAX_SCHEMA_DEPTH
from my_agent_crew.mcp.tools import summary
from my_agent_crew.tools.registry import Tool

MAX_PARAMS, LISTED_CHARS = 12, 100
# `describe` writes at most this much in all, of which a description and a parameter's own
# words take at most these.
MAX_DESCRIBED, DESCRIBED_CHARS, PARAM_CHARS = 2_000, 600, 120
MAX_ENUM, ENUM_CHARS = 8, 30
JSON_TYPES = frozenset(("string", "number", "integer", "boolean", "array", "object", "null"))
PARAM_NAME = re.compile(r"\w{1,40}")


def _kind(schema: Any) -> str:
    kind = schema.get("type") if isinstance(schema, dict) else None
    return kind if isinstance(kind, str) and kind in JSON_TYPES else "any"


def _properties(schema: Any) -> dict[str, Any]:
    properties = schema.get("properties") if isinstance(schema, dict) else None
    return properties if isinstance(properties, dict) else {}


def _required(schema: Any) -> list[str]:
    required = schema.get("required") if isinstance(schema, dict) else None
    if not isinstance(required, list):
        return []
    return [name for name in required if isinstance(name, str)]


def _cut(text: str, most: int) -> str:
    return text if len(text) <= most else text[: most - 1] + "…"


def call_line(tool: Tool) -> str:
    """`name(a: string, b?: integer)`: a tool as it is called."""
    required = _required(tool.parameters)
    params = [
        f"{name}{'' if name in required else '?'}: {_kind(schema)}"
        for name, schema in _properties(tool.parameters).items()
        if PARAM_NAME.fullmatch(name)
    ]
    shown = ", ".join(params[:MAX_PARAMS]) + (", …" if len(params) > MAX_PARAMS else "")
    return f"{tool.name}({shown})"


def signature(tool: Tool) -> str:
    """One tool as one line a model can call it from: its parameters by name and kind."""
    return f"- {call_line(tool)}: {_cut(summary(tool.description), LISTED_CHARS)}"


def _detail(schema: Any) -> str:
    """A parameter's kind, and what it holds when that is short: an array's items, or the
    values an enum allows."""
    kind = _kind(schema)
    if kind == "array":
        return f"array<{_kind(schema.get('items') if isinstance(schema, dict) else None)}>"
    options = schema.get("enum") if isinstance(schema, dict) else None
    if isinstance(options, list) and 0 < len(options) <= MAX_ENUM:
        plain = [option for option in options if type(option) in (str, int)]
        # Written as JSON, so a value with a line break in it stays on its line.
        shown = [json.dumps(option, ensure_ascii=False) for option in plain]
        if len(shown) == len(options) and all(len(one) <= ENUM_CHARS for one in shown):
            return f"{kind}: {'|'.join(shown)}"
    return kind


def _params(schema: Any, prefix: str = "", depth: int = 0) -> Iterator[str]:
    """One line for each parameter, those inside an object or an array of objects by path
    (`filter.property`, `pages[].title`), no deeper than a schema is read anywhere."""
    if depth >= MAX_SCHEMA_DEPTH:
        return
    required = _required(schema)
    for name, inner in _properties(schema).items():
        if not PARAM_NAME.fullmatch(name):
            continue
        path = f"{prefix}{name}"
        flags = t.SCRIPT_DESCRIBE_REQUIRED if name in required else ""
        said = inner.get("description") if isinstance(inner, dict) else None
        words = _cut(summary(said), PARAM_CHARS) if isinstance(said, str) else ""
        yield f"- {path} ({_detail(inner)}{flags})" + (f": {words}" if words else "")
        yield from _params(inner, f"{path}.", depth + 1)
        if _kind(inner) == "array":
            yield from _params(inner.get("items"), f"{path}[].", depth + 1)


def describe(tool: Tool) -> str:
    """A tool in full: how it is called, what it does, and each of its parameters with its
    kind and what it is for. Cut at `MAX_DESCRIBED` characters, a whole line at a time."""
    params = _params(tool.parameters)
    first = next(params, None)
    tail = (
        [t.SCRIPT_DESCRIBE_NONE]
        if first is None
        else chain([t.SCRIPT_DESCRIBE_PARAMS, first], params)
    )
    lines: list[str] = []
    used = 0
    for line in chain([call_line(tool), _cut(tool.description.strip(), DESCRIBED_CHARS)], tail):
        used += len(line) + 1
        if used > MAX_DESCRIBED:
            lines.append(t.SCRIPT_DESCRIBE_CUT)
            break
        lines.append(line)
    return "\n".join(lines)


def misfits(tool: Tool, arguments: dict[str, Any]) -> bool:
    """Whether a call plainly does not fit the tool: one parameter it requires is left out,
    or one it has no parameter for is given. Asked of a call that has failed, to tell the
    script how the tool is called; the tool's own words for what went wrong stay as they were."""
    properties = _properties(tool.parameters)
    left_out = any(name not in arguments for name in _required(tool.parameters))
    return left_out or (bool(properties) and any(name not in properties for name in arguments))
