"""A sign-in from its first click to the token kept (`renewal` renews one that ran out).

The owner starts it from the web on the machine the crew runs on; the authorization server
sends them back to this process with a code. What ties the two ends together is a `state`
made here, good for one use and for ten minutes: a code that arrives with no such state,
with one already used or with one that is too old, is traded for nothing.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from my_agent_crew import texts_mcp as t
from my_agent_crew.mcp.oauth import authorize_url, pkce, register, token
from my_agent_crew.mcp.oauth_discovery import AuthServer, discover
from my_agent_crew.mcp.tokens import ACCESS, CLIENT_ID, ISSUER, REFRESH, env_name
from my_agent_crew.mcp.wire import McpError

if TYPE_CHECKING:
    from my_agent_crew.mcp.hub import Link, McpHub

STATE_SECONDS = 600.0
CONNECTED, SIGNED_OUT, FAILED = "connected", "signed_out", "failed"


@dataclass(frozen=True)
class Pending:
    server: str
    verifier: str
    client_id: str
    redirect_uri: str
    auth: AuthServer
    expires: float


class SignIns:
    """The sign-ins that are waiting for a person to come back."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._waiting: dict[str, Pending] = {}

    def open(
        self, server: str, verifier: str, client_id: str, redirect: str, auth: AuthServer
    ) -> str:
        """The state to send with a person. A server has one sign-in open at a time: a
        second click makes the first one's state worthless."""
        now = self._clock()
        self._waiting = {
            state: pending
            for state, pending in self._waiting.items()
            if pending.server != server and pending.expires > now
        }
        state = secrets.token_urlsafe(32)
        expires = now + STATE_SECONDS
        self._waiting[state] = Pending(server, verifier, client_id, redirect, auth, expires)
        return state

    def take(self, state: str) -> Pending | None:
        return self._waiting.pop(state, None)

    def late(self, pending: Pending) -> bool:
        return pending.expires <= self._clock()


def has_own_key(link: Link) -> bool:
    """Whether the file already says how the server is authorised."""
    return any(name.lower() == "authorization" for name, _ in link.server.headers)


async def begin(hub: McpHub, link: Link, redirect_uri: str) -> str:
    """The address to send the owner to. Raises McpError when no sign-in can start. Nothing
    is kept until they come back: a sign-in begun and left changes nothing of the one in
    use."""
    if has_own_key(link):
        raise McpError(t.MCP_LOGIN_HEADER_KEY)
    if link.status == CONNECTED and not hub.tokens.get(link.server, ACCESS):
        raise McpError(t.MCP_LOGIN_NOT_ASKED)
    if hub.client is None:
        raise McpError(t.MCP_NO_CLIENT)
    server = link.server
    auth = await discover(hub.client, server.url, link.challenge, hub.resolver)
    if auth.registration_endpoint:
        client_id = await register(hub.client, auth, redirect_uri, hub.resolver)
    else:
        client_id = hub.tokens.get(server, CLIENT_ID)
        if not client_id:
            name = env_name(server, CLIENT_ID)
            raise McpError(t.MCP_OAUTH_NO_REGISTRATION.format(name=name))
    verifier, challenge = pkce()
    state = hub.sign_ins.open(server.name, verifier, client_id, redirect_uri, auth)
    return authorize_url(auth, client_id, redirect_uri, state, challenge)


def _unwelcome(hub: McpHub, pending: Pending, code: str, error: str, iss: str) -> str:
    """Why what a person came back with is not traded; empty when it is."""
    if hub.sign_ins.late(pending):
        return t.MCP_OAUTH_LATE
    if error:
        return t.MCP_OAUTH_DENIED.format(error=error[:200])
    if not code:
        return t.MCP_OAUTH_NO_CODE
    # A place that says who it is as it sends a person back is believed, and one that said
    # it would and did not is not (RFC 9207): a code another place gave is never traded.
    issuer = pending.auth.issuer
    if iss and iss != issuer:
        return t.MCP_OAUTH_ISSUER.format(got=iss[:200], expected=issuer[:200])
    if pending.auth.names_itself and not iss:
        return t.MCP_OAUTH_NO_ISS
    return ""


async def finish(hub: McpHub, state: str, code: str, error: str = "", iss: str = "") -> str | None:
    """Trade the code a person came back with and connect with what it bought. The name of
    the server it was for, or None when no sign-in was waiting for this state. A failure
    is left on the server's row, where the screen the person lands on shows it."""
    pending = hub.sign_ins.take(state) if state else None
    link = hub.links.get(pending.server) if pending else None
    if pending is None or link is None or hub.client is None:
        return None
    unwelcome = _unwelcome(hub, pending, code, error, iss)
    if unwelcome:
        link.error = unwelcome
        return pending.server
    try:
        tokens = await token(
            hub.client,
            pending.auth,
            hub.resolver,
            grant_type="authorization_code",
            code=code,
            redirect_uri=pending.redirect_uri,
            client_id=pending.client_id,
            code_verifier=pending.verifier,
        )
        # The whole sign-in or none of it: a refresh token is never left beside the name
        # of a place that did not grant it. One the new place did not give drops the old.
        kept = {ISSUER: pending.auth.issuer, ACCESS: tokens.access, REFRESH: tokens.refresh}
        if pending.client_id != hub.tokens.get(link.server, CLIENT_ID):
            kept[CLIENT_ID] = pending.client_id
        # After any renewal on its way, which would otherwise write what it gets over this.
        async with link.renewing:
            hub.tokens.put(link.server, kept)
            link.auth = pending.auth
    except McpError as exc:
        link.error = str(exc)
    except (ValueError, OSError) as exc:
        link.error = t.MCP_OAUTH_STORE.format(error=exc)
    else:
        await hub.connect([pending.server])
    return pending.server


def forget(hub: McpHub, link: Link) -> None:
    """Drop the sign-in and who granted it. The client id stays: it is this crew's name
    at that server."""
    try:
        hub.tokens.put(link.server, {ACCESS: "", REFRESH: "", ISSUER: ""})
    except OSError:
        # What cannot be written down stays as the file says, here and at the next start.
        pass
