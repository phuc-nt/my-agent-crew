"""The two names a script reaches out through: `tools` and `json`.

Neither is a value. `tools.NAME(...)` and `json.loads(...)` are read as calls where they
are written, so a script cannot hold either, pass it on or look inside it. Beside a tool's
own name `tools` has four of its own: `names`, `search` and `describe`, which look at the
tools a script may call and run none, and `batch`, which calls several at once (`calls.py`).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts_script as t
from my_agent_crew.script.calls import call_batch, call_one
from my_agent_crew.script.limits import (
    MAX_INDENT,
    MAX_LOOKUP_CHARS,
    MAX_LOOKUPS,
    ScriptError,
)

if TYPE_CHECKING:
    from my_agent_crew.script.machine import Machine

# What a script may look into besides calling a tool: each as it is written, and its
# parameters in order with their type and whether a call needs them. The parent answers (see
# `discovery.py`), so a tool that is given one of these names is not one a script can call.
LOOKUPS: dict[str, tuple[str, dict[str, tuple[type, bool]]]] = {
    "names": ("tools.names()", {}),
    "search": ("tools.search(query, limit=5)", {"query": (str, True), "limit": (int, False)}),
    "describe": ("tools.describe(name)", {"name": (str, True)}),
}
# Every name `tools` answers to itself, which a tool cannot be called as from a script.
RESERVED = frozenset({*LOOKUPS, "batch"})


def _lookup(machine: Machine, kind: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
    """Which tools there are, which fit a job, how one is called: asked of the parent, which
    holds them. No tool runs, so none of it is counted among the calls."""
    shape, params = LOOKUPS[kind]
    asked = {**dict(zip(params, args, strict=False)), **kwargs}
    valid = (
        # Each parameter given once, and only this lookup's own.
        len(asked) == len(args) + len(kwargs)
        and asked.keys() <= params.keys()
        and all(name in asked for name, (_, required) in params.items() if required)
        and all(
            type(value) is params[name][0]
            and (type(value) is not str or len(value) <= MAX_LOOKUP_CHARS)
            for name, value in asked.items()
        )
    )
    if not valid:
        raise ScriptError(t.SCRIPT_LOOKUP_USAGE.format(shape=shape))
    machine.budget.lookups += 1
    if machine.budget.lookups > MAX_LOOKUPS:
        raise ScriptError(t.SCRIPT_TOO_MANY_LOOKUPS.format(most=MAX_LOOKUPS))
    return machine.budget.made(machine.ask(kind, asked))


def _tools(machine: Machine, name: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
    """`tools.names`, `tools.search` and `tools.describe` look, `tools.batch` calls several
    tools at once; any other name is a tool."""
    if name in LOOKUPS:
        return _lookup(machine, name, args, kwargs)
    if name == "batch":
        return call_batch(machine, args, kwargs)
    return call_one(machine, name, args, kwargs)


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


NAMESPACES: dict[str, Callable[..., Any]] = {"tools": _tools, "json": _json}
