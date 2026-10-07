"""Running a script through the interpreter alone, with the tools a test hands it."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from textwrap import dedent
from typing import Any

from my_agent_crew.script.limits import ScriptError
from my_agent_crew.script.machine import run

Tools = Mapping[str, Callable[[dict[str, Any]], str]]
Lookups = Mapping[str, Callable[[dict[str, Any]], Any]]
Calls = list[tuple[str, dict[str, Any]]]


def play(
    source: str,
    tools: Tools | None = None,
    lookups: Lookups | None = None,
    *,
    batches: list[Calls] | None = None,
) -> dict[str, Any]:
    """The script run to its end. A tool is `name: (arguments) -> text`; one the script
    names and the test did not hand it fails the way a tool does. A lookup (`names`,
    `search`, `describe`) is `kind: (arguments) -> value`, refused in the same way. A batch
    is made call by call, each one asked in `asked` like any other, and handed whole to
    `batches` when a test wants to see what was sent together."""
    asked: Calls = []

    def call_tool(name: str, arguments: dict[str, Any]) -> str:
        asked.append((name, arguments))
        if tools is None or name not in tools:
            raise ScriptError(f"no tool {name}")
        return tools[name](arguments)

    def call_tools(calls: Calls) -> list[tuple[bool, str]]:
        if batches is not None:
            batches.append(calls)
        answered = []
        for name, arguments in calls:
            try:
                answered.append((True, call_tool(name, arguments)))
            except ScriptError as failed:
                answered.append((False, str(failed)))
        return answered

    def ask(kind: str, arguments: dict[str, Any]) -> Any:
        if lookups is None or kind not in lookups:
            raise ScriptError(f"no lookup {kind}")
        return lookups[kind](arguments)

    return {**run(dedent(source), call_tool, ask, call_tools), "asked": asked}


def printed(source: str, tools: Tools | None = None, lookups: Lookups | None = None) -> str:
    """What a script that ran to its end printed."""
    ended = play(source, tools, lookups)
    assert ended["ok"], ended["error"]
    assert ended["error"] is None
    return ended["output"]


def stopped(source: str, tools: Tools | None = None, lookups: Lookups | None = None) -> str:
    """The line a script that did not end well ends with."""
    ended = play(source, tools, lookups)
    assert not ended["ok"]
    return ended["error"]
