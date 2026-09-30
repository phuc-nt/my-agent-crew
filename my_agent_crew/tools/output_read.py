"""The `tool_output_read` tool: getting back a tool result the model only saw shortened.

It reads the conversation it is called from and no other, even for the master: the id is the
model's to type, so it cannot be what decides whose data is read. The true original comes
from the spill file when one survives, otherwise from the stored message (which may itself be
the shortened text). An id that two results share is refused, because answering for the wrong
call is worse than not answering."""

from __future__ import annotations

from typing import Any

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import turn_conversation_id
from my_agent_crew.store import Store
from my_agent_crew.tools.output_spill import READ_TOOL, Spill
from my_agent_crew.tools.registry import Tool, ToolError

DEFAULT_READ_CHARS = 8000


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _source(store: Store, spill: Spill, conv_id: str, call_id: str) -> tuple[str, str]:
    """The text to read and what to call it."""
    rows = store.messages.tool_results(conv_id, call_id, 2)
    if len(rows) > 1:
        raise ToolError(texts.TOOL_OUTPUT_AMBIGUOUS.format(id=call_id))
    original = spill.read(conv_id, call_id)
    if original is not None:
        return original, texts.TOOL_OUTPUT_SOURCE_ORIGINAL
    if rows:
        return rows[0].message.content, texts.TOOL_OUTPUT_SOURCE_STORED
    raise ToolError(texts.TOOL_OUTPUT_NOT_FOUND.format(id=call_id))


def build_output_read_tool(store: Store, spill: Spill, cap: int) -> Tool:
    """`cap` is the registry's output cap: a segment is sized so the header and the
    "read on" hint fit inside it, because this tool's own output is never spilled."""

    async def run(args: dict[str, Any]) -> str:
        call_id = str(args.get("id", "")).strip()
        conv_id = turn_conversation_id()
        if not call_id or not conv_id:
            raise ToolError(texts.TOOL_OUTPUT_NOT_FOUND.format(id=call_id))
        text, source = _source(store, spill, conv_id, call_id)
        total = len(text)
        offset = min(max(_int(args.get("offset"), 0), 0), total)
        # Sized for the widest header and hint this text can need, so the answer cannot
        # outgrow the cap by the length of its own signposts.
        widest = texts.TOOL_OUTPUT_READ_HEADER.format(
            source=source, offset=total, end=total, total=total
        ) + texts.TOOL_OUTPUT_READ_MORE.format(remaining=total, id=call_id, next_offset=total)
        room = max(cap - len(widest), 1)
        size = min(max(_int(args.get("limit"), DEFAULT_READ_CHARS), 1), room)
        end = min(offset + size, total)
        header = texts.TOOL_OUTPUT_READ_HEADER.format(
            source=source, offset=offset, end=end, total=total
        )
        if end >= total:
            return header + text[offset:end] + texts.TOOL_OUTPUT_READ_DONE
        more = texts.TOOL_OUTPUT_READ_MORE.format(
            remaining=total - end, id=call_id, next_offset=end
        )
        return header + text[offset:end] + more

    return Tool(
        name=READ_TOOL,
        description=texts.TOOL_OUTPUT_READ_DESCRIPTION,
        parameters={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": texts.TOOL_OUTPUT_READ_PARAM_ID},
                "offset": {"type": "integer", "description": texts.TOOL_OUTPUT_READ_PARAM_OFFSET},
                "limit": {"type": "integer", "description": texts.TOOL_OUTPUT_READ_PARAM_LIMIT},
            },
            "required": ["id"],
        },
        run=run,
        parallel=True,
    )
