"""The body of a server's answer, read as it arrives: never more of it than an answer may
hold, and split into the events of a stream when the server answers with one."""

from __future__ import annotations

import json
from typing import Any

import httpx

from my_agent_crew import texts_mcp as t
from my_agent_crew.mcp.errors import McpError

MAX_ANSWER_BYTES = 4_000_000


async def _capped(chunks: Any, server: str) -> Any:
    """The chunks as they come, until they add up to more than an answer may hold."""
    total = 0
    async for chunk in chunks:
        total += len(chunk)
        if total > MAX_ANSWER_BYTES:
            megabytes = MAX_ANSWER_BYTES // 1_000_000
            raise McpError(t.MCP_TOO_LARGE.format(server=server, megabytes=megabytes))
        yield chunk


async def _lines(response: httpx.Response, server: str) -> Any:
    """The lines of the stream. Only CR, LF and the two together end a line of an event
    stream: text may hold whatever else a decoder would take for the end of one."""
    held: list[bytes] = []
    after_cr = False
    async for chunk in _capped(response.aiter_bytes(), server):
        if after_cr and chunk.startswith(b"\n"):
            chunk = chunk[1:]  # The other half of a CRLF whose CR ended the last chunk.
        after_cr = chunk.endswith(b"\r")
        *lines, rest = chunk.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")
        for line in lines:
            yield b"".join([*held, line]).decode("utf-8", "replace")
            held.clear()
        if rest:
            held.append(rest)
    if held:
        yield b"".join(held).decode("utf-8", "replace")


async def read_events(response: httpx.Response, server: str) -> Any:
    """The data of each event in the stream, parsed. A line that is not `data:` (an id, a
    comment kept to hold the connection open) carries nothing this client uses."""
    data: list[str] = []
    async for line in _lines(response, server):
        if line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
        elif not line.strip() and data:
            text, data = "\n".join(data), []
            try:
                yield json.loads(text)
            except ValueError:
                continue
    if data:
        # A stream that closed without the blank line that ends its last event.
        try:
            yield json.loads("\n".join(data))
        except ValueError:
            return


async def read_body(response: httpx.Response, server: str) -> bytes:
    return b"".join([chunk async for chunk in _capped(response.aiter_bytes(), server)])
