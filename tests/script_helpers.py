"""Running a script through the interpreter alone, with the tools a test hands it."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from textwrap import dedent
from typing import Any

from my_agent_crew.script.limits import ScriptError
from my_agent_crew.script.machine import run

Tools = Mapping[str, Callable[[dict[str, Any]], str]]


def play(source: str, tools: Tools | None = None) -> dict[str, Any]:
    """The script run to its end. A tool is `name: (arguments) -> text`; one the script
    names and the test did not hand it fails the way a tool does."""
    asked: list[tuple[str, dict[str, Any]]] = []

    def call_tool(name: str, arguments: dict[str, Any]) -> str:
        asked.append((name, arguments))
        if tools is None or name not in tools:
            raise ScriptError(f"no tool {name}")
        return tools[name](arguments)

    return {**run(dedent(source), call_tool), "asked": asked}


def printed(source: str, tools: Tools | None = None) -> str:
    """What a script that ran to its end printed."""
    ended = play(source, tools)
    assert ended["ok"], ended["error"]
    assert ended["error"] is None
    return ended["output"]


def stopped(source: str, tools: Tools | None = None) -> str:
    """The line a script that did not end well ends with."""
    ended = play(source, tools)
    assert not ended["ok"]
    return ended["error"]
