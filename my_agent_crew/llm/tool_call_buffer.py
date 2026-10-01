"""Tool calls as an OpenAI-compatible stream sends them: in fragments keyed by index, the
id and name in one delta and the arguments spread over many."""

from __future__ import annotations

import json
import uuid
from typing import Any

from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.types import ToolCall


class ToolCallBuffer:
    """Assembles fragmented tool_call deltas keyed by their stream index."""

    def __init__(self) -> None:
        self._parts: dict[int, dict[str, str]] = {}

    def feed(self, deltas: list[dict[str, Any]]) -> None:
        for d in deltas:
            slot = self._parts.setdefault(d.get("index", 0), {"id": "", "name": "", "args": ""})
            slot["id"] = d.get("id") or slot["id"]
            fn = d.get("function") or {}
            slot["name"] = fn.get("name") or slot["name"]
            slot["args"] += fn.get("arguments") or ""

    def calls(self) -> tuple[ToolCall, ...]:
        calls = []
        for index in sorted(self._parts):
            slot = self._parts[index]
            try:
                args = json.loads(slot["args"] or "{}")
            except ValueError as exc:
                raise ProviderError(f"tool call {slot['name']} had malformed arguments") from exc
            if not isinstance(args, dict):
                raise ProviderError(f"tool call {slot['name']} arguments are not an object")
            calls.append(
                ToolCall(
                    id=slot["id"] or f"call_{uuid.uuid4().hex}",
                    name=slot["name"],
                    arguments=args,
                )
            )
        return tuple(calls)
