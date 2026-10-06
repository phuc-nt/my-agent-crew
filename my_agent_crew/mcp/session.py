"""A session with one MCP server: the handshake, the list of its tools, and calls.

A request is sent once. Two refusals are the exception, because in both the server says it
did not run the request: a session it no longer knows (the session is opened again and the
request sent to the new one) and a sign-in that ran out (it is renewed once, when it can
be). A call that timed out or whose connection dropped is never sent again: the server may
already have done it.
"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, TypeVar

import httpx

from my_agent_crew import __version__
from my_agent_crew import texts_mcp as t
from my_agent_crew.mcp.config import McpServer
from my_agent_crew.mcp.wire import (
    SESSION_HEADER,
    Answer,
    McpError,
    SessionGone,
    Unauthorized,
    exchange,
)

# What this client speaks, newest first; the first is what it asks for.
VERSIONS = ("2025-06-18", "2025-11-25", "2025-03-26")
VERSION_HEADER = "MCP-Protocol-Version"
METHOD_NOT_FOUND = -32601
# A server that kept answering with one more page would hold a turn for ever.
MAX_TOOL_PAGES = 20

T = TypeVar("T")
Headers = Callable[[], Mapping[str, str]]
# Told the authorization that was refused; whether the request is worth sending again.
Renew = Callable[[str], Awaitable[bool]]


class McpSession:
    def __init__(
        self,
        server: McpServer,
        client: httpx.AsyncClient,
        headers: Headers,
        renew: Renew | None = None,
    ):
        self.server = server
        self.client = client
        # Read for every request, so a key or a sign-in changed since is the one sent.
        self._own_headers = headers
        self._renew = renew
        self._session_id = ""
        self._version = ""
        self._ids = itertools.count(1)
        self._opening = asyncio.Lock()

    def _headers(self) -> dict[str, str]:
        headers = dict(self._own_headers())
        if self._session_id:
            headers[SESSION_HEADER] = self._session_id
        if self._version:
            headers[VERSION_HEADER] = self._version
        return headers

    async def _send(self, message: dict[str, Any]) -> Answer:
        return await exchange(
            self.client,
            self.server.name,
            self.server.url,
            self._headers(),
            message,
            self.server.timeout,
            self._reply,
        )

    async def _reply(self, asked: dict[str, Any]) -> None:
        """Answer a request the server made while answering ours. It may ask whether the
        client is still there; this client offers nothing else, and says so."""
        answer: dict[str, Any] = {"jsonrpc": "2.0", "id": asked["id"]}
        if asked.get("method") == "ping":
            answer["result"] = {}
        else:
            answer["error"] = {"code": METHOD_NOT_FOUND, "message": "Method not found"}
        try:
            await self._send(answer)
        except McpError:
            # The call this arrived in is still worth its own answer.
            return

    async def _signed(self, send: Callable[[], Awaitable[T]]) -> T:
        try:
            return await send()
        except Unauthorized as refusal:
            if self._renew is None or not await self._renew(refusal.sent):
                raise
            return await send()

    async def _ask(self, method: str, params: dict[str, Any] | None) -> dict[str, Any]:
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": next(self._ids), "method": method}
        if params is not None:
            message["params"] = params
        answer = (await self._send(message)).message or {}
        return self._result(answer)

    def _result(self, answer: dict[str, Any]) -> dict[str, Any]:
        name = self.server.name
        error = answer.get("error")
        if error is not None:
            said = error.get("message") if isinstance(error, dict) else error
            raise McpError(t.MCP_RPC_ERROR.format(server=name, message=said or "?"))
        result = answer.get("result")
        if not isinstance(result, dict):
            raise McpError(t.MCP_BAD_ANSWER.format(server=name))
        return result

    async def _open(self) -> None:
        self._session_id = self._version = ""
        message = {
            "jsonrpc": "2.0",
            "id": next(self._ids),
            "method": "initialize",
            "params": {
                "protocolVersion": VERSIONS[0],
                "capabilities": {},
                "clientInfo": {"name": "my-agent-crew", "version": __version__},
            },
        }
        answer = await self._send(message)
        version = self._result(answer.message or {}).get("protocolVersion")
        if version not in VERSIONS:
            name = self.server.name
            raise McpError(t.MCP_VERSION.format(server=name, version=version))
        self._session_id, self._version = answer.session_id, version
        try:
            await self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except BaseException:
            # A session the server was never told is ready is not one to send calls to.
            self._session_id = self._version = ""
            raise

    async def start(self) -> None:
        """Open a session, renewing the sign-in once if the server asks for one."""
        async with self._opening:
            await self._signed(self._open)

    async def _reopen(self, gone: str) -> None:
        async with self._opening:
            # Several calls can learn at once that the session is gone; one opens the next,
            # unless that one failed and left none open.
            if self._session_id == gone or not self._version:
                await self._signed(self._open)

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self._opening:
            # Wait for a session that is being opened: sent now, this would name none. And
            # open one when the last opening failed, or the server stays lost for good.
            if not self._version:
                await self._signed(self._open)
            used = self._session_id
        try:
            return await self._signed(lambda: self._ask(method, params))
        except SessionGone:
            await self._reopen(used)
            return await self._signed(lambda: self._ask(method, params))

    async def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        cursor = None
        for _ in range(MAX_TOOL_PAGES):
            page = await self.request("tools/list", {"cursor": cursor} if cursor else None)
            listed = page.get("tools") or []
            if not isinstance(listed, list):
                raise McpError(t.MCP_BAD_ANSWER.format(server=self.server.name))
            tools += [tool for tool in listed if isinstance(tool, dict)]
            cursor = page.get("nextCursor")
            if not cursor:
                break
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self.request("tools/call", {"name": name, "arguments": arguments})
