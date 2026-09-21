"""Reading a picture with a vision model.

The chat model on an agent's routes is not expected to see images, so `image_read` sends
the file down a route chain of its own (`vision_routes`) and hands back what that model
said. Any agent gets the tool: the master looks to decide who the picture is for, the
agent it delegates to looks again for the detail it needs. The price of the call lands on
the conversation like any completion.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from my_agent_crew.llm.provider import ProviderChain, ProviderError
from my_agent_crew.llm.types import Completion, Message
from my_agent_crew.texts import (
    IMAGE_DEFAULT_QUESTION,
    IMAGE_EMPTY,
    IMAGE_NOT_FOUND,
    IMAGE_OUTSIDE,
    IMAGE_PARAM_PATH,
    IMAGE_PARAM_QUESTION,
    IMAGE_READ_DESCRIPTION,
    IMAGE_READ_FAILED,
    IMAGE_SYSTEM,
    IMAGE_TOO_LARGE,
    IMAGE_UNSUPPORTED,
)
from my_agent_crew.tools.registry import Tool, ToolError, ToolResult
from my_agent_crew.tools.workspace import resolve_inside

IMAGE_TOOL_NAME = "image_read"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def resolve_image(path: str, roots: Sequence[Path]) -> Path:
    """The first root the path lands in wins: the agent's workspace, then the crew home
    (where the master's inbox keeps what the person sent)."""
    for root in roots:
        try:
            return resolve_inside(root, path)
        except ToolError:
            continue
    raise ToolError(IMAGE_OUTSIDE)


def check_image(path: Path, max_bytes: int = MAX_IMAGE_BYTES) -> str:
    """The MIME type of a readable picture, or a `ToolError` saying why not."""
    if not path.is_file():
        raise ToolError(IMAGE_NOT_FOUND.format(path=path))
    mime = MIME_TYPES.get(path.suffix.lower())
    if mime is None:
        kinds = ", ".join(sorted({s.lstrip(".") for s in MIME_TYPES}))
        raise ToolError(IMAGE_UNSUPPORTED.format(suffix=path.suffix or "?", kinds=kinds))
    size = path.stat().st_size
    if size > max_bytes:
        mb = 1024 * 1024
        raise ToolError(IMAGE_TOO_LARGE.format(size=size / mb, limit=max_bytes / mb))
    return mime


def data_url(path: Path, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


async def describe(chain: ProviderChain, url: str, question: str) -> tuple[str, float | None]:
    """What the vision model says about the picture, and what it charged."""
    messages = [
        Message(role="system", content=IMAGE_SYSTEM),
        Message(role="user", content=question or IMAGE_DEFAULT_QUESTION, images=(url,)),
    ]
    text, cost = "", None
    async for item in chain.stream(messages, ()):
        if isinstance(item, Completion):
            text, cost = item.message.content, item.usage.cost_usd
    return text.strip(), cost


def build_image_tool(
    roots: Sequence[Path], chain: ProviderChain, max_bytes: int = MAX_IMAGE_BYTES
) -> Tool:
    async def run(args: dict[str, Any]) -> ToolResult:
        path = resolve_image(str(args.get("path") or ""), roots)
        mime = check_image(path, max_bytes)
        try:
            text, cost = await describe(
                chain, data_url(path, mime), str(args.get("question") or "")
            )
        except ProviderError as exc:
            raise ToolError(IMAGE_READ_FAILED.format(error=exc)) from exc
        return ToolResult(ok=True, output=text or IMAGE_EMPTY, cost_usd=cost, metered=True)

    return Tool(
        name=IMAGE_TOOL_NAME,
        description=IMAGE_READ_DESCRIPTION,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": IMAGE_PARAM_PATH},
                "question": {"type": "string", "description": IMAGE_PARAM_QUESTION},
            },
            "required": ["path"],
        },
        run=run,
        parallel=True,
    )
