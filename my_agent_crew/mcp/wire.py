"""One JSON-RPC message to an MCP server over streamable HTTP, and the answer to it.

The server answers a request either with one JSON body or with a stream of events that
ends in the answer. Anything else it sends on the way is a message of its own: a request
is handed to `reply`, a notification is dropped. A redirect is never followed, since where
a request goes is the owner's to say; an answer larger than the cap is refused before it
is held; and nothing here tries a message twice, because the server may already have done
what it was asked.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from my_agent_crew import texts_mcp as t
from my_agent_crew.mcp.answer_body import read_body, read_events
from my_agent_crew.mcp.errors import McpError, SessionGone, Unauthorized

CONNECT_SECONDS = 10.0
SESSION_HEADER = "Mcp-Session-Id"
ERROR_SNIPPET_CHARS = 200

Reply = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class Answer:
    # The answer to the request sent; None for a notification, which has none.
    message: dict[str, Any] | None
    session_id: str


def _pick(payload: Any, wanted: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """(the answer to `wanted`, the requests the server made) among what one body held."""
    items = payload if isinstance(payload, list) else [payload]
    answer, asked = None, []
    for item in items:
        if not isinstance(item, dict):
            continue
        if "method" in item:
            if "id" in item:
                asked.append(item)
        elif item.get("id") == wanted and ("result" in item or "error" in item):
            answer = item
    return answer, asked


async def _read(
    response: httpx.Response, server: str, wanted: Any, reply: Reply | None
) -> dict[str, Any]:
    if "text/event-stream" in response.headers.get("content-type", ""):
        payloads = read_events(response, server)
    else:
        try:
            parsed = json.loads(await read_body(response, server))
        except ValueError:
            raise McpError(t.MCP_BAD_ANSWER.format(server=server)) from None

        async def one() -> Any:
            yield parsed

        payloads = one()
    async for payload in payloads:
        answer, asked = _pick(payload, wanted)
        for request in asked if reply else ():
            await reply(request)
        if answer is not None:
            return answer
    raise McpError(t.MCP_NO_ANSWER.format(server=server))


async def _refuse(response: httpx.Response, server: str, sent: httpx.Headers) -> None:
    status = response.status_code
    if status == 401:
        challenge = response.headers.get("www-authenticate", "")
        said = t.MCP_UNAUTHORIZED.format(server=server)
        raise Unauthorized(said, challenge, sent.get("authorization", ""))
    if status == 404 and SESSION_HEADER in sent:
        raise SessionGone(t.MCP_SESSION_GONE.format(server=server))
    if 300 <= status < 400:
        raise McpError(t.MCP_REDIRECT.format(server=server))
    if status >= 400:
        text = (await read_body(response, server)).decode("utf-8", "replace").strip()
        detail = f": {text[:ERROR_SNIPPET_CHARS]}" if text else ""
        raise McpError(t.MCP_HTTP_STATUS.format(server=server, status=status, detail=detail))


async def exchange(
    client: httpx.AsyncClient,
    server: str,
    url: str,
    headers: Mapping[str, str],
    message: dict[str, Any],
    timeout: float,
    reply: Reply | None = None,
) -> Answer:
    """Send `message` and wait for what answers it, for at most `timeout` seconds in all."""
    # Only a request is answered: a notification has no id, and an answer to something
    # the server asked carries the server's id, not one of ours.
    wanted = message.get("id") if "method" in message else None
    sent = {
        **headers,
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    limits = httpx.Timeout(timeout, connect=min(CONNECT_SECONDS, timeout))
    try:
        async with asyncio.timeout(timeout):
            request = client.build_request("POST", url, json=message, headers=sent, timeout=limits)
            response = await client.send(request, stream=True, follow_redirects=False)
            try:
                await _refuse(response, server, request.headers)
                session_id = response.headers.get(SESSION_HEADER, "")
                if wanted is None:
                    return Answer(None, session_id)
                return Answer(await _read(response, server, wanted, reply), session_id)
            finally:
                await response.aclose()
    except TimeoutError:
        raise McpError(t.MCP_TIMEOUT.format(server=server, seconds=timeout)) from None
    except httpx.LocalProtocolError:
        # What the writer says of a header it will not write quotes the header's value.
        raise McpError(t.MCP_BAD_HEADER.format(server=server)) from None
    except httpx.HTTPError as exc:
        error = str(exc) or type(exc).__name__
        raise McpError(t.MCP_UNREACHABLE.format(server=server, error=error)) from exc
