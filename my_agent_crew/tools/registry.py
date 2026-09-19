"""Tool registry. A tool is a name, a JSON-schema, an async runner and a flag saying
whether a human confirms it first. Output is capped so one tool cannot flood the context."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from my_agent_crew.llm.types import ToolSpec
from my_agent_crew.texts import OUTPUT_TRUNCATED, TOOL_FAILED, UNKNOWN_TOOL

logger = logging.getLogger(__name__)

MAX_OUTPUT_CHARS = 8000

ToolRunner = Callable[[dict[str, Any]], Awaitable[str]]


class ToolError(Exception):
    """A failure the model should read about and react to, not a bug."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    run: ToolRunner
    requires_approval: bool = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, parameters=self.parameters)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "requires_approval": self.requires_approval,
        }


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    output: str


def truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + OUTPUT_TRUNCATED.format(dropped=len(text) - limit)


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None):
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def describe(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self._tools.values()]

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, output=UNKNOWN_TOOL.format(name=name))
        try:
            output = await tool.run(arguments)
        except ToolError as exc:
            return ToolResult(ok=False, output=TOOL_FAILED.format(error=exc))
        except Exception as exc:  # a bug in a tool must not take the turn down with it
            logger.exception("tool %s crashed", name)
            return ToolResult(ok=False, output=TOOL_FAILED.format(error=type(exc).__name__))
        return ToolResult(ok=True, output=truncate(output))
