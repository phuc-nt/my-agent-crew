"""An MCP server and the authorization server in front of it, answered in process.

Nothing here opens a socket: the client under test is given a transport that hands every
request to `FakeMcp.handle`. The server keeps what it was asked, so a test can say what
reached it and what never did.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx

from my_agent_crew.mcp.config import McpServer
from my_agent_crew.mcp.config_parse import parse_server
from my_agent_crew.mcp.hub import McpHub
from my_agent_crew.mcp.tokens import TokenStore

MCP_URL = "https://mcp.example.test/mcp"
AUTH = "https://auth.example.test"
RESOURCE_DOC = "https://mcp.example.test/.well-known/oauth-protected-resource/mcp"
AUTH_DOC = f"{AUTH}/.well-known/oauth-authorization-server"
REDIRECT = "http://127.0.0.1:8765/api/mcp/oauth/callback"
PUBLIC_ADDRESS = "93.184.216.34"

SEARCH = {
    "name": "search",
    "description": "Find pages by words.",
    "inputSchema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    "annotations": {"readOnlyHint": True},
}
CREATE = {
    "name": "create-page",
    "description": "Make a page.",
    "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}}},
}
TOOLS = (SEARCH, CREATE)


def public(host: str) -> list[str]:
    """Every name resolves to an address on the open internet."""
    return [PUBLIC_ADDRESS]


def server(name: str = "notion", **settings: Any) -> McpServer:
    return parse_server(name, {"url": MCP_URL, **settings})


@dataclass
class Seen:
    headers: dict[str, str]
    message: dict[str, Any]

    @property
    def method(self) -> str | None:
        return self.message.get("method")


def s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class FakeMcp:
    def __init__(self, tools=TOOLS, *, sse: bool = False, oauth: bool = False):
        self.tools: list[Any] = list(tools)
        self.sse = sse
        self.version = "2025-06-18"
        self.page_size = 0  # tools per `tools/list` page; 0 lists them all at once
        self.ping = False  # ask the client whether it is there before answering a call
        self.delay = 0.0
        # Called with each MCP request before the server looks at it; what it returns is
        # the answer, and None lets the server answer as it would.
        self.before: Callable[[httpx.Request, dict[str, Any]], httpx.Response | None] | None = None
        self.results: dict[str, Any] = {}
        self.seen: list[Seen] = []
        self.fetched: list[tuple[str, str]] = []
        self.calls: list[tuple[str, Any]] = []
        self.answers: list[dict[str, Any]] = []
        self.sessions: list[str] = []
        self.live: set[str] = set()
        # The bearer token the MCP endpoint wants, or None when it wants nothing.
        self.required: str | None = "not-signed-in-yet" if oauth else None
        self.documents: dict[str, Any] = {}
        self.registered: list[dict[str, Any]] = []
        self.codes: dict[str, dict[str, str]] = {}
        self.refresh_tokens: set[str] = set()
        self.token_requests: list[dict[str, str]] = []
        self.issued = 0
        if oauth:
            self.documents[RESOURCE_DOC] = {
                "resource": "https://mcp.example.test",
                "authorization_servers": [AUTH],
                "scopes_supported": ["default"],
            }
            self.documents[AUTH_DOC] = {
                "issuer": AUTH,
                "authorization_endpoint": f"{AUTH}/authorize",
                "token_endpoint": f"{AUTH}/token",
                "registration_endpoint": f"{AUTH}/register",
                "code_challenge_methods_supported": ["plain", "S256"],
            }

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    def methods(self) -> list[str | None]:
        return [seen.method for seen in self.seen]

    async def handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.fetched.append((request.method, url))
        if url == MCP_URL and request.method == "POST":
            if self.delay:
                await asyncio.sleep(self.delay)
            return self._mcp(request)
        if request.method == "GET" and url in self.documents:
            return httpx.Response(200, json=self.documents[url])
        if request.method == "POST" and url == f"{AUTH}/register":
            self.registered.append(json.loads(request.content))
            return httpx.Response(201, json={"client_id": f"client-{len(self.registered)}"})
        if request.method == "POST" and url == f"{AUTH}/token":
            return self._token(dict(parse_qsl(request.content.decode("utf-8"))))
        return httpx.Response(404, text="nothing here")

    def _mcp(self, request: httpx.Request) -> httpx.Response:
        message = json.loads(request.content)
        self.seen.append(Seen(dict(request.headers), message))
        early = self.before(request, message) if self.before else None
        if early is not None:
            return early
        if self.required is not None:
            if request.headers.get("authorization") != f"Bearer {self.required}":
                challenge = f'Bearer realm="OAuth", resource_metadata="{RESOURCE_DOC}"'
                return httpx.Response(401, headers={"www-authenticate": challenge})
        method = message.get("method")
        if method is None:
            self.answers.append(message)
            return httpx.Response(202)
        if method == "initialize":
            session = f"s{len(self.sessions) + 1}"
            self.sessions.append(session)
            self.live = {session}
            opened = {"protocolVersion": self.version, "capabilities": {"tools": {}}}
            return self._answer(message, opened, session)
        if request.headers.get("mcp-session-id") not in self.live:
            return httpx.Response(404, text="no such session")
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            return self._answer(message, self._page((message.get("params") or {}).get("cursor")))
        if method == "tools/call":
            params = message["params"]
            name, arguments = params["name"], params.get("arguments")
            self.calls.append((name, arguments))
            result = self.results.get(name, {"content": [{"type": "text", "text": f"ran {name}"}]})
            if isinstance(result, dict) and "rpc_error" in result:
                return self._answer(message, error=result["rpc_error"])
            return self._answer(message, result)
        return self._answer(message, error={"code": -32601, "message": "Method not found"})

    def _page(self, cursor: str | None) -> dict[str, Any]:
        if not self.page_size:
            return {"tools": self.tools}
        start = int(cursor or 0)
        end = start + self.page_size
        page: dict[str, Any] = {"tools": self.tools[start:end]}
        if end < len(self.tools):
            page["nextCursor"] = str(end)
        return page

    def _answer(
        self, message: dict[str, Any], result: Any = None, session: str = "", error: Any = None
    ) -> httpx.Response:
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": message["id"]}
        body.update({"error": error} if error is not None else {"result": result})
        headers = {"Mcp-Session-Id": session} if session else {}
        if not self.sse:
            return httpx.Response(200, json=body, headers=headers)
        events = [": keep-alive", ""]
        if self.ping and message.get("method") == "tools/call":
            asked = {"jsonrpc": "2.0", "id": "server-1", "method": "ping"}
            events += ["event: message", f"data: {json.dumps(asked)}", ""]
        events += ["event: message", "id: 7", f"data: {json.dumps(body)}", "", ""]
        headers["Content-Type"] = "text/event-stream"
        return httpx.Response(200, content="\n".join(events).encode("utf-8"), headers=headers)

    def approve(self, authorize_url: str) -> tuple[str, str]:
        """The person saying yes in their browser: (the code they are sent back with, the
        state that came with them)."""
        asked = dict(parse_qsl(urlsplit(authorize_url).query))
        code = f"code-{len(self.codes) + 1}"
        self.codes[code] = asked
        return code, asked["state"]

    def _token(self, form: dict[str, str]) -> httpx.Response:
        self.token_requests.append(form)
        refused = httpx.Response(400, json={"error": "invalid_grant"})
        if form.get("grant_type") == "authorization_code":
            asked = self.codes.pop(form.get("code", ""), None)
            if asked is None or asked["client_id"] != form.get("client_id"):
                return refused
            if asked["redirect_uri"] != form.get("redirect_uri"):
                return refused
            if asked["code_challenge"] != s256(form.get("code_verifier", "")):
                return refused
        elif form.get("grant_type") == "refresh_token":
            if form.get("refresh_token") not in self.refresh_tokens:
                return refused
            self.refresh_tokens.discard(form["refresh_token"])
        else:
            return httpx.Response(400, json={"error": "unsupported_grant_type"})
        self.issued += 1
        access, refresh = f"access-{self.issued}", f"refresh-{self.issued}"
        self.refresh_tokens.add(refresh)
        # Only the newest access token opens the MCP endpoint.
        self.required = access
        granted = {"access_token": access, "token_type": "Bearer", "refresh_token": refresh}
        return httpx.Response(200, json=granted)


def make_hub(
    fake: FakeMcp,
    *servers: McpServer,
    environ: MutableMapping[str, str] | None = None,
    home: Path | None = None,
) -> McpHub:
    environ = {} if environ is None else environ
    tokens = TokenStore(home, environ)
    return McpHub(servers or (server(),), fake.client(), tokens, public, environ)
