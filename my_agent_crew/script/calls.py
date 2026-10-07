"""The calls a script makes: `tools.NAME(...)`, and `tools.batch([...])` for several at once.

Both are checked and counted here, in the process that runs the script, before anything is
asked of the parent. What cannot be sent as it was written is a mistake the script may catch,
and costs it no call. Every call of a batch is looked at before the first is sent, so a batch
is made whole or not at all; each one that is made is one of the script's `MAX_CALLS`, whether
it came back answered or failed.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts_script as t
from my_agent_crew.script.limits import (
    MAX_ARGUMENT_CHARS,
    MAX_BATCH,
    MAX_CALLS,
    Halt,
    ScriptError,
)

if TYPE_CHECKING:
    from my_agent_crew.script.machine import Machine

# What one call of a batch is written with.
CALL_KEYS = frozenset({"tool", "args"})


def _checked(machine: Machine, arguments: dict[str, Any]) -> dict[str, Any]:
    """What a tool is given, if it can be given as written: no longer than it may be, and
    what JSON can carry, the same in a test as over a pipe."""
    if machine.budget.measure(arguments) > MAX_ARGUMENT_CHARS:
        raise ScriptError(t.SCRIPT_ARGS_TOO_BIG.format(most=MAX_ARGUMENT_CHARS))
    try:
        return json.loads(json.dumps(arguments))
    except (TypeError, ValueError) as exc:
        raise ScriptError(t.SCRIPT_TOOL_ARGS_JSON) from exc


def call_one(machine: Machine, name: str, args: list[Any], kwargs: dict[str, Any]) -> str:
    """One call of a tool: its output as text. A tool that failed raises, and the script
    may catch that; a tool it may not call ends the script, where `call_tool` says so."""
    if args and (len(args) != 1 or type(args[0]) is not dict or kwargs):
        raise ScriptError(t.SCRIPT_TOOL_ARGS)
    arguments = _checked(machine, args[0] if args else kwargs)
    machine.budget.calls += 1
    if machine.budget.calls > MAX_CALLS:
        raise Halt(t.SCRIPT_TOO_MANY_CALLS.format(most=MAX_CALLS))
    output = machine.call_tool(name, arguments)
    machine.budget.charge(len(output))
    return output


def _given(args: list[Any], kwargs: dict[str, Any]) -> Any:
    """What `tools.batch` was given, if it was given one thing: by position or as `calls=`."""
    if len(args) == 1 and not kwargs:
        return args[0]
    if not args and kwargs.keys() == {"calls"}:
        return kwargs["calls"]
    return None


def _element(machine: Machine, index: int, item: Any) -> tuple[str, dict[str, Any]]:
    """One call of a batch as the tool and the arguments it is made with."""
    arguments = item.get("args", {}) if type(item) is dict else None
    if (
        type(item) is not dict
        or not item.keys() <= CALL_KEYS
        or type(item.get("tool")) is not str
        or type(arguments) is not dict
    ):
        raise ScriptError(t.SCRIPT_BATCH_ITEM.format(index=index))
    try:
        return item["tool"], _checked(machine, arguments)
    except ScriptError as wrong:
        raise ScriptError(t.SCRIPT_BATCH_AT.format(index=index, error=wrong)) from wrong


def call_batch(machine: Machine, args: list[Any], kwargs: dict[str, Any]) -> list[dict[str, Any]]:
    """Calls made side by side, answered in the order they were written: for each,
    `{"ok": True, "output": ...}` or `{"ok": False, "error": ...}`. A call that failed is its
    own answer and not a failure of the batch; one the script may not make ends the script,
    as it would made alone."""
    given = _given(args, kwargs)
    if type(given) is not list:
        raise ScriptError(t.SCRIPT_BATCH_USAGE)
    if not given:
        raise ScriptError(t.SCRIPT_BATCH_EMPTY)
    if len(given) > MAX_BATCH:
        raise ScriptError(t.SCRIPT_BATCH_TOO_MANY.format(most=MAX_BATCH))
    calls = [_element(machine, index, item) for index, item in enumerate(given)]
    left = MAX_CALLS - machine.budget.calls
    if left <= 0:
        raise Halt(t.SCRIPT_TOO_MANY_CALLS.format(most=MAX_CALLS))
    if len(calls) > left:
        raise ScriptError(t.SCRIPT_BATCH_ROOM.format(count=len(calls), left=left, most=MAX_CALLS))
    machine.budget.calls += len(calls)
    answers = machine.call_tools(calls)
    # Together, as they are held together: each may be too little to be looked at by itself.
    machine.budget.charge(sum(len(output) for _, output in answers))
    return [
        {"ok": True, "output": output} if ok else {"ok": False, "error": output}
        for ok, output in answers
    ]
