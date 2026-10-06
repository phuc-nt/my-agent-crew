"""The two names a script reaches out through: `tools` and `json`.

Neither is a value. `tools.NAME(...)` and `json.loads(...)` are read as calls where they
are written, so a script cannot hold either, pass it on or look inside it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts_script as t
from my_agent_crew.script.limits import (
    MAX_ARGUMENT_CHARS,
    MAX_CALLS,
    MAX_INDENT,
    Halt,
    ScriptError,
)

if TYPE_CHECKING:
    from my_agent_crew.script.machine import Machine


def _tool(machine: Machine, name: str, args: list[Any], kwargs: dict[str, Any]) -> str:
    """One call of a tool: its output as text. A tool that failed raises, and the script
    may catch that; a tool it may not call ends the script, where `call_tool` says so."""
    if args and (len(args) != 1 or type(args[0]) is not dict or kwargs):
        raise ScriptError(t.SCRIPT_TOOL_ARGS)
    arguments = args[0] if args else kwargs
    if machine.budget.measure(arguments) > MAX_ARGUMENT_CHARS:
        raise ScriptError(t.SCRIPT_ARGS_TOO_BIG.format(most=MAX_ARGUMENT_CHARS))
    try:
        # What the tool is given is what JSON can carry, the same in a test as over a pipe.
        arguments = json.loads(json.dumps(arguments))
    except (TypeError, ValueError) as exc:
        raise ScriptError(t.SCRIPT_TOOL_ARGS_JSON) from exc
    machine.budget.calls += 1
    if machine.budget.calls > MAX_CALLS:
        raise Halt(t.SCRIPT_TOO_MANY_CALLS.format(most=MAX_CALLS))
    output = machine.call_tool(name, arguments)
    machine.budget.charge(len(output))
    return output


def _loads(machine: Machine, text: Any) -> Any:
    if type(text) is not str:
        raise ScriptError(t.SCRIPT_BAD_CALL.format(name="json.loads"))
    try:
        parsed = json.loads(text)
    except RecursionError as exc:
        raise ScriptError(t.SCRIPT_TOO_NESTED) from exc
    # Parsed, a text is at most a value for each of its characters.
    machine.budget.charge(len(text))
    return parsed


def _dumps(machine: Machine, value: Any, **kwargs: Any) -> str:
    machine.budget.measure(value)
    indent = kwargs.get("indent")
    return machine.budget.made(
        json.dumps(
            value,
            # A small indent only: what it adds is its width for every item, at every depth.
            indent=indent if type(indent) is int and 0 <= indent <= MAX_INDENT else None,
            ensure_ascii=bool(kwargs.get("ensure_ascii", False)),
            sort_keys=bool(kwargs.get("sort_keys", False)),
            # `default=` is honoured as `str`, whatever was named: nothing of the script's
            # is handed to the encoder to call.
            default=str if "default" in kwargs else None,
        )
    )


def _json(machine: Machine, name: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
    if name == "loads" and len(args) == 1:
        return _loads(machine, args[0])
    if name == "dumps" and len(args) == 1:
        return _dumps(machine, args[0], **kwargs)
    raise ScriptError(t.SCRIPT_NO_JSON)


NAMESPACES: dict[str, Callable[..., Any]] = {"tools": _tool, "json": _json}
