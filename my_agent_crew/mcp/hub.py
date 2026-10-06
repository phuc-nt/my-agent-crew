"""Every MCP server the crew knows, each with its session, its tools and how it stands.

A server that cannot be reached is a row that says why, never a crew that does not start:
connecting catches everything and leaves the reason on the server. Agents are handed the
tools of the servers their profile names, and handed them again whenever a server or a
profile changes, so what an agent holds is always what the servers hold now.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx

from my_agent_crew import texts_mcp as t
from my_agent_crew.mcp import sign_in
from my_agent_crew.mcp.config import McpServer, MissingEnv
from my_agent_crew.mcp.handout import hand_out
from my_agent_crew.mcp.oauth_discovery import AuthServer
from my_agent_crew.mcp.session import McpSession
from my_agent_crew.mcp.tokens import ACCESS, TokenStore, bearer
from my_agent_crew.mcp.tools import McpTool, build_tools, summary
from my_agent_crew.mcp.wire import McpError, Unauthorized
from my_agent_crew.tools.web import Resolver, resolve_host

if TYPE_CHECKING:
    from my_agent_crew.agent.loop import AgentDeps

logger = logging.getLogger(__name__)

# Never tried, working, waiting for the owner to sign in, and tried without success.
IDLE, CONNECTED, SIGNED_OUT, FAILED = "idle", sign_in.CONNECTED, sign_in.SIGNED_OUT, "failed"


@dataclass
class Link:
    server: McpServer
    session: McpSession | None = None
    tools: tuple[McpTool, ...] = ()
    # Tools left out because another took the name they come to.
    skipped: tuple[str, ...] = ()
    status: str = IDLE
    error: str = ""
    # What the server said when it asked for a sign-in: where to learn how.
    challenge: str = ""
    auth: AuthServer | None = None
    renewing: asyncio.Lock = field(default_factory=asyncio.Lock)


class McpHub:
    def __init__(
        self,
        servers: Iterable[McpServer] = (),
        client: httpx.AsyncClient | None = None,
        tokens: TokenStore | None = None,
        resolver: Resolver = resolve_host,
        environ: MutableMapping[str, str] | None = None,
    ):
        self.environ = os.environ if environ is None else environ
        self.client = client
        self.tokens = tokens or TokenStore(None, self.environ)
        self.resolver = resolver
        self.links = {server.name: Link(server) for server in servers}
        self.sign_ins = sign_in.SignIns()
        # Set by whoever thinks a server that is down may answer now (`mcp_lifecycle`).
        self.wake = asyncio.Event()

    def headers_for(self, server: McpServer) -> dict[str, str]:
        """What authorises a request now: the file's headers, or the sign-in kept."""
        headers = server.request_headers(self.environ)
        access = self.tokens.get(server, ACCESS)
        if access and not any(name.lower() == "authorization" for name in headers):
            headers["Authorization"] = bearer(access)
        return headers

    async def connect(self, names: Iterable[str] | None = None) -> None:
        """Open a session with each server named (all of them by default) and learn its
        tools. Never raises: what went wrong is on the server's row."""
        wanted = self.links if names is None else names
        links = [self.links[name] for name in wanted if name in self.links]
        await asyncio.gather(*(self._connect(link) for link in links))

    async def _connect(self, link: Link) -> None:
        server = link.server
        # Idle until it answers: a try that is cut off must not leave it looking connected.
        link.session, link.tools, link.skipped, link.status = None, (), (), IDLE
        if self.client is None:
            link.status, link.error = FAILED, t.MCP_NO_CLIENT
            return
        session = McpSession(
            server,
            self.client,
            lambda: self.headers_for(server),
            lambda refused: sign_in.renew(self, link, refused),
        )
        try:
            await session.start()
            listed = await session.list_tools()
        except Unauthorized as exc:
            if sign_in.has_own_key(link):
                link.status, link.error = FAILED, t.MCP_KEY_REFUSED
            else:
                link.status, link.error, link.challenge = SIGNED_OUT, "", exc.challenge
        except MissingEnv as exc:
            link.status = FAILED
            link.error = t.MCP_MISSING_ENV.format(names=", ".join(exc.names))
        except McpError as exc:
            link.status, link.error = FAILED, str(exc)
        except Exception as exc:
            # A server that answers nonsense is one more that is down, not a crash.
            logger.exception("MCP server %s: connecting failed", server.name)
            link.status, link.error = FAILED, f"{type(exc).__name__}: {exc}"
        else:
            link.session = session
            link.tools, link.skipped = build_tools(server, listed, session.call_tool)
            link.status, link.error, link.challenge = CONNECTED, "", ""
            for name in link.skipped:
                logger.warning(
                    "MCP server %s: tool %s left out, its name is taken", server.name, name
                )

    def waiting(self) -> list[str]:
        """Servers worth trying again without anyone asking. One that wants a sign-in is
        not among them: only the owner can give it that."""
        return [name for name, link in self.links.items() if link.status in (IDLE, FAILED)]

    def attach(self, agents: Mapping[str, AgentDeps]) -> None:
        """Hand each agent the tools of the servers its profile names, and take back every
        MCP tool it held before (`handout`)."""
        for deps in agents.values():
            hand_out(deps, self.links)

    async def sign_out(self, name: str) -> None:
        link = self.links[name]
        sign_in.forget(self, link)
        link.auth = None
        await self.connect([name])

    def describe(self, agents: Mapping[str, AgentDeps]) -> list[dict[str, Any]]:
        """What the owner is shown of each server. Never a header's value or a token."""
        return [
            {
                "name": name,
                "url": link.server.url,
                "description": link.server.description,
                "status": link.status,
                "error": link.error,
                "exposure": link.server.exposure,
                "signed_in": bool(self.tokens.get(link.server, ACCESS)),
                "uses_key": sign_in.has_own_key(link),
                "env": list(link.server.env_names()),
                "agents": sorted(a for a, deps in agents.items() if name in deps.agent.mcp),
                "skipped": list(link.skipped),
                "tools": [
                    {
                        "name": tool.name,
                        "remote": tool.remote,
                        "description": summary(tool.description),
                        "exposure": tool.exposure,
                        "requires_approval": tool.requires_approval,
                        "read_only_hint": tool.read_only_hint,
                    }
                    for tool in link.tools
                ],
            }
            for name, link in self.links.items()
        ]
