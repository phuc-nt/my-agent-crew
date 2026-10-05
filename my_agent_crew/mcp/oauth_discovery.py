"""Finding where to sign in for an MCP server, from what it and its authorization server
publish (RFC 9728, RFC 8414).

Every address learned here came from a remote machine, so each is checked before anything
is sent to it: https only, never an address inside this network, and no redirect followed.
A server that cannot do PKCE with S256 is refused, since a code sent back to a loopback
address has no other protection.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from my_agent_crew import texts_mcp as t
from my_agent_crew.mcp.wire import McpError
from my_agent_crew.tools.web import Resolver, is_private

TIMEOUT_SECONDS = 15.0
MAX_BODY_BYTES = 200_000
RESOURCE_METADATA = re.compile(r'resource_metadata="([^"]+)"')


@dataclass(frozen=True)
class AuthServer:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str = ""
    # What a token is asked for (RFC 8707), as the server names itself.
    resource: str = ""
    scopes: tuple[str, ...] = ()


def origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


async def checked(url: Any, resolver: Resolver) -> str:
    """`url` when it is safe to send a request to, else an McpError naming it."""
    refused = McpError(t.MCP_OAUTH_URL.format(url=str(url)[:200]))
    try:
        parts = urlsplit(url) if isinstance(url, str) else None
        host = parts.hostname if parts else None
    except ValueError:
        raise refused from None
    if parts is None or parts.scheme != "https" or not host or parts.username is not None:
        raise refused
    try:
        addresses = await asyncio.to_thread(resolver, host)
    except OSError:
        raise refused from None
    if not addresses or any(is_private(address) for address in addresses):
        raise refused
    return url


async def fetch_json(
    client: httpx.AsyncClient, method: str, url: str, resolver: Resolver, **kwargs: Any
) -> tuple[int, dict[str, Any]]:
    await checked(url, resolver)
    headers = {"Accept": "application/json"}
    request = client.build_request(method, url, headers=headers, timeout=TIMEOUT_SECONDS, **kwargs)
    response = await client.send(request, stream=True, follow_redirects=False)
    try:
        raw = b""
        async for chunk in response.aiter_bytes():
            raw += chunk
            if len(raw) > MAX_BODY_BYTES:
                return response.status_code, {}
    finally:
        await response.aclose()
    try:
        body = json.loads(raw)
    except ValueError:
        body = {}
    return response.status_code, body if isinstance(body, dict) else {}


async def _first(client: httpx.AsyncClient, urls: list[str], resolver: Resolver) -> dict[str, Any]:
    """The first of `urls` that answers with a document, or {} when none does."""
    for url in urls:
        try:
            status, body = await fetch_json(client, "GET", url, resolver)
        except httpx.HTTPError:
            continue
        if status == 200 and body:
            return body
    return {}


def _resource_places(server_url: str) -> list[str]:
    """Where a server publishes what protects it: for its own path first, then its host."""
    parts = urlsplit(server_url)
    root, path = f"{parts.scheme}://{parts.netloc}", parts.path.rstrip("/")
    urls = [f"{root}/.well-known/oauth-protected-resource{path}"]
    return [*urls, f"{root}/.well-known/oauth-protected-resource"] if path else urls


def _issuer_places(issuer: str) -> list[str]:
    """Where an authorization server publishes itself: the OAuth document, then the OpenID
    one, which a server with a path may keep before the path or after it."""
    parts = urlsplit(issuer)
    root, path = f"{parts.scheme}://{parts.netloc}", parts.path.rstrip("/")
    urls = [
        f"{root}/.well-known/oauth-authorization-server{path}",
        f"{root}/.well-known/openid-configuration{path}",
    ]
    return [*urls, f"{root}{path}/.well-known/openid-configuration"] if path else urls


async def discover(
    client: httpx.AsyncClient, server_url: str, challenge: str, resolver: Resolver
) -> AuthServer:
    """Where to sign in for the server at `server_url`, from what it publishes."""
    try:
        named = RESOURCE_METADATA.search(challenge)
        places = [named.group(1)] if named else []
        places += _resource_places(server_url)
        resource = await _first(client, places, resolver)
        issuers = resource.get("authorization_servers")
        # A server that publishes nothing of its own is its own authorization server.
        issuer = issuers[0] if isinstance(issuers, list) and issuers else origin(server_url)
        await checked(issuer, resolver)
        metadata = await _first(client, _issuer_places(issuer), resolver)
    except httpx.HTTPError as exc:
        raise McpError(t.MCP_OAUTH_DISCOVERY.format(error=exc)) from exc
    if not metadata:
        raise McpError(t.MCP_OAUTH_DISCOVERY.format(error=issuer))
    said = str(metadata.get("issuer") or "")
    if said.rstrip("/") != issuer.rstrip("/"):
        raise McpError(t.MCP_OAUTH_ISSUER.format(got=said[:200], expected=issuer))
    if "S256" not in (metadata.get("code_challenge_methods_supported") or ()):
        raise McpError(t.MCP_OAUTH_NO_PKCE)
    target = str(resource.get("resource") or server_url)
    if origin(target) != origin(server_url):
        raise McpError(t.MCP_OAUTH_RESOURCE.format(resource=target[:200]))
    scopes = resource.get("scopes_supported")
    registration = metadata.get("registration_endpoint")
    return AuthServer(
        issuer=issuer,
        authorization_endpoint=await checked(metadata.get("authorization_endpoint"), resolver),
        token_endpoint=await checked(metadata.get("token_endpoint"), resolver),
        registration_endpoint=await checked(registration, resolver) if registration else "",
        resource=target,
        scopes=tuple(s for s in scopes if isinstance(s, str)) if isinstance(scopes, list) else (),
    )
