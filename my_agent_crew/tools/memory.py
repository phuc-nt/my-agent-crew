"""Notes the agent keeps across conversations."""

from __future__ import annotations

from typing import Any

from my_agent_crew import texts
from my_agent_crew.store import Store
from my_agent_crew.tools.registry import Tool, ToolError


def build_memory_tools(store: Store) -> list[Tool]:
    async def save(args: dict[str, Any]) -> str:
        text = str(args.get("text", "")).strip()
        if not text:
            raise ToolError("ghi chú trống")
        store.notes.add(text)
        return texts.MEMORY_SAVED.format(count=store.notes.count())

    async def search(args: dict[str, Any]) -> str:
        hits = store.notes.search(str(args.get("query", "")))
        if not hits:
            return texts.MEMORY_EMPTY
        return "\n".join(f"[{stamp[:10]}] {text}" for _, text, stamp in hits)

    return [
        Tool(
            name="memory_save",
            description="Ghi nhớ một thông tin để dùng lại ở các cuộc trò chuyện sau.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            run=save,
        ),
        Tool(
            name="memory_search",
            description="Tìm trong các ghi chú đã lưu.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            run=search,
        ),
    ]
