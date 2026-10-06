"""Signing in to an MCP server with OAuth 2.1, as a public client with PKCE: registering
this client where the authorization server lets one (RFC 7591), the address a person is
sent to, and the trade of a code or a refresh token for an access token.

The addresses used here were checked when they were learned (`oauth_discovery`), and are
checked again each time something is sent: a name can come to point somewhere else.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx

from my_agent_crew import texts_mcp as t
from my_agent_crew.mcp.oauth_discovery import AuthServer, fetch_json
from my_agent_crew.mcp.wire import McpError
from my_agent_crew.tools.web import Resolver

CLIENT_NAME = "my-agent-crew"
# What a token endpoint says when the grant is spent or this client is unknown to it
# (RFC 6749 §5.2). Every other no leaves the grant as good as it was.
SPENT = ("invalid_grant", "invalid_client")


class GrantRefused(McpError):
    """The authorization server said that what was traded is no longer good."""


@dataclass(frozen=True)
class Tokens:
    access: str
    refresh: str = ""


def _said(status: int, body: dict[str, Any]) -> str:
    detail = body.get("error_description") or body.get("error") or ""
    return f"HTTP {status} {str(detail)[:200]}".strip()


async def register(
    client: httpx.AsyncClient, auth: AuthServer, redirect_uri: str, resolver: Resolver
) -> str:
    """Register as a public client for one redirect address; the client id it is given."""
    request = {
        "client_name": CLIENT_NAME,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    try:
        status, body = await fetch_json(
            client, "POST", auth.registration_endpoint, resolver, json=request
        )
    except httpx.HTTPError as exc:
        raise McpError(t.MCP_OAUTH_REGISTER.format(error=exc)) from exc
    client_id = body.get("client_id")
    if status not in (200, 201) or not isinstance(client_id, str) or not client_id:
        raise McpError(t.MCP_OAUTH_REGISTER.format(error=_said(status, body)))
    return client_id


def pkce() -> tuple[str, str]:
    """(verifier, challenge): the verifier stays here, its digest goes with the person."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def authorize_url(
    auth: AuthServer, client_id: str, redirect_uri: str, state: str, challenge: str
) -> str:
    query = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": auth.resource,
    }
    if auth.scopes:
        query["scope"] = " ".join(auth.scopes)
    joiner = "&" if urlsplit(auth.authorization_endpoint).query else "?"
    return f"{auth.authorization_endpoint}{joiner}{urlencode(query)}"


async def token(
    client: httpx.AsyncClient, auth: AuthServer, resolver: Resolver, **grant: str
) -> Tokens:
    """Trade a code, or a refresh token, for an access token."""
    form = {**grant, "resource": auth.resource}
    try:
        status, body = await fetch_json(client, "POST", auth.token_endpoint, resolver, data=form)
    except httpx.HTTPError as exc:
        raise McpError(t.MCP_OAUTH_TOKEN.format(error=exc)) from exc
    access = body.get("access_token")
    if status != 200 or not isinstance(access, str) or not access:
        spent = 400 <= status < 500 and body.get("error") in SPENT
        failure = GrantRefused if spent else McpError
        raise failure(t.MCP_OAUTH_TOKEN.format(error=_said(status, body)))
    kind = str(body.get("token_type") or "")
    if kind.lower() != "bearer":
        raise McpError(t.MCP_OAUTH_TOKEN_TYPE.format(kind=kind[:40]))
    refresh = body.get("refresh_token")
    return Tokens(access, refresh if isinstance(refresh, str) else "")
