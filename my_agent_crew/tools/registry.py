"""Tool registry. A tool is a name, a JSON-schema, an async runner and a flag saying
whether a human confirms it first. Output is capped so one tool cannot flood the context."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from my_agent_crew.config import DEFAULT_TOOL_OUTPUT_CHARS
from my_agent_crew.llm.types import ToolSpec
from my_agent_crew.texts import OUTPUT_TRUNCATED, TOOL_BLOCKED_BY_HOOK, TOOL_FAILED, UNKNOWN_TOOL

if TYPE_CHECKING:
    from my_agent_crew.tools.hooks import HookRunner

logger = logging.getLogger(__name__)

# The default cap; a profile's `tool_output_chars` sets its own registry's limit.
MAX_OUTPUT_CHARS = DEFAULT_TOOL_OUTPUT_CHARS


class ToolError(Exception):
    """A failure the model should read about and react to, not a bug."""


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    output: str
    # Set by a tool that paid a model itself (`image_read`): the price, or None when the
    # upstream reported none. `metered` says the call is to be charged at all.
    cost_usd: float | None = None
    metered: bool = False


# A runner returns its text, or a `ToolResult` when it has more to say than text.
ToolRunner = Callable[[dict[str, Any]], Awaitable[str | ToolResult]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    run: ToolRunner
    requires_approval: bool = False
    # Safe to run at the same time as the other parallel calls in the same message. Only
    # for tools that spend most of their time waiting and do not race each other.
    parallel: bool = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, parameters=self.parameters)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "requires_approval": self.requires_approval,
        }


def truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + OUTPUT_TRUNCATED.format(dropped=len(text) - limit)


class ToolRegistry:
    def __init__(
        self,
        tools: list[Tool] | None = None,
        limit: int = MAX_OUTPUT_CHARS,
        hooks: HookRunner | None = None,
    ):
        # The cap is per registry, so an agent whose scripts print long JSON can raise it
        # in its profile without every other agent paying the context for it. The hooks
        # are the agent's kit hooks, asked before and after every call.
        self.limit = limit
        self.hooks = hooks
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

    def without(self, name: str) -> ToolRegistry:
        """A copy missing one tool. How a delegated agent is handed the same toolbox minus
        `delegate`, so the chain stops one level down."""
        kept = [t for t in self._tools.values() if t.name != name]
        return ToolRegistry(kept, self.limit, self.hooks)

    def specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def describe(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self._tools.values()]

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, output=UNKNOWN_TOOL.format(name=name))
        if self.hooks is not None:
            reason = await self.hooks.before(name, arguments)
            if reason is not None:
                blocked = TOOL_BLOCKED_BY_HOOK.format(name=name, reason=reason)
                return ToolResult(ok=False, output=truncate(blocked, self.limit))
        result = await self._run(name, tool, arguments)
        if self.hooks is not None:
            note = await self.hooks.after(name, arguments, result.ok, result.output)
            if note:
                result = replace(result, output=truncate(result.output + note, self.limit))
        return result

    async def _run(self, name: str, tool: Tool, arguments: dict[str, Any]) -> ToolResult:
        try:
            output = await tool.run(arguments)
        except ToolError as exc:
            return ToolResult(ok=False, output=TOOL_FAILED.format(error=exc))
        except Exception as exc:  # a bug in a tool must not take the turn down with it
            logger.exception("tool %s crashed", name)
            return ToolResult(ok=False, output=TOOL_FAILED.format(error=type(exc).__name__))
        if isinstance(output, ToolResult):
            return replace(output, output=truncate(output.output, self.limit))
        return ToolResult(ok=True, output=truncate(output, self.limit))
