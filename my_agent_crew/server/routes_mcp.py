"""The MCP servers of the crew, for the Connections screen: how each one stands, trying
one again, and signing in to one and out of it.

A sign-in starts and ends in the owner's browser on the machine the crew runs on. The
authorization server sends them back to a loopback address of this process, which is the
only kind a public client may be sent a code on; started from any other address it is
refused before anything is registered. Nothing answered here carries a token.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from my_agent_crew import texts_mcp as t
from my_agent_crew.mcp import sign_in
from my_agent_crew.mcp.config import LOOPBACK_HOSTS
from my_agent_crew.mcp.hub import Link
from my_agent_crew.mcp.wire import McpError
from my_agent_crew.server.deps import Rt
from my_agent_crew.server.local_guard import OAUTH_CALLBACK_PATH
from my_agent_crew.server.runtime import Runtime

router = APIRouter(tags=["mcp"])

# Where the owner lands after a sign-in: the screen that lists the servers.
AFTER_SIGN_IN = "/#/manage/connections"


def _link(rt: Runtime, name: str) -> Link:
    link = rt.mcp.links.get(name)
    if link is None:
        raise HTTPException(404, t.MCP_UNKNOWN_SERVER.format(name=name))
    return link


def _answer(rt: Runtime) -> dict[str, Any]:
    return {"servers": rt.mcp.describe(rt.agents)}


def _loopback(host_header: str) -> bool:
    try:
        return urlsplit(f"//{host_header}").hostname in LOOPBACK_HOSTS
    except ValueError:
        return False


@router.get("/mcp")
def list_servers(rt: Rt) -> dict[str, Any]:
    return _answer(rt)


@router.post("/mcp/{name}/reconnect")
async def reconnect(name: str, rt: Rt) -> dict[str, Any]:
    _link(rt, name)
    await rt.mcp.connect([name])
    rt.mcp.attach(rt.agents)
    return _answer(rt)


@router.post("/mcp/{name}/login")
async def login(name: str, request: Request, rt: Rt) -> dict[str, Any]:
    link = _link(rt, name)
    host = request.headers.get("host", "")
    if not _loopback(host):
        raise HTTPException(409, t.MCP_LOGIN_LOCAL_ONLY)
    try:
        url = await sign_in.begin(rt.mcp, link, f"http://{host}{OAUTH_CALLBACK_PATH}")
    except McpError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"authorize_url": url}


@router.delete("/mcp/{name}/login")
async def logout(name: str, rt: Rt) -> dict[str, Any]:
    _link(rt, name)
    await rt.mcp.sign_out(name)
    rt.mcp.attach(rt.agents)
    return _answer(rt)


@router.get("/mcp/oauth/callback")
async def callback(
    rt: Rt, code: str = "", state: str = "", error: str = "", iss: str = ""
) -> RedirectResponse:
    """Where the authorization server sends the owner back. Whatever happened, they land
    on the screen that lists the servers, which shows it."""
    if await sign_in.finish(rt.mcp, state, code, error, iss) is not None:
        rt.mcp.attach(rt.agents)
    return RedirectResponse(AFTER_SIGN_IN, status_code=303)
