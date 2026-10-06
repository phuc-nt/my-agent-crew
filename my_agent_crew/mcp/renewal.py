"""Renewing a sign-in that ran out, with the refresh token the last one left.

Two answers end a sign-in: the authorization server saying the grant is spent, or that it
no longer knows this client. Whatever else it says, and whatever keeps it from saying a
thing, leaves what is kept as it was, and the next call tries again.

A refresh token is said only to the place that granted it. A server can come to name any
place as its sign-in; one that names another than the one kept ends the sign-in unsaid.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from my_agent_crew import texts_mcp as t
from my_agent_crew.mcp.oauth import GrantRefused, token
from my_agent_crew.mcp.oauth_discovery import discover
from my_agent_crew.mcp.sign_in import FAILED, SIGNED_OUT, forget, has_own_key
from my_agent_crew.mcp.tokens import ACCESS, CLIENT_ID, ISSUER, REFRESH, bearer
from my_agent_crew.mcp.wire import McpError

if TYPE_CHECKING:
    from my_agent_crew.mcp.hub import Link, McpHub


async def renew(hub: McpHub, link: Link, refused: str) -> bool:
    """Get a new access token with the refresh token; whether the request is worth
    sending again. `refused` is the authorization the server said no to: calls refused
    together renew once between them, however late each one hears of it."""
    server = link.server
    if has_own_key(link):
        # Its key is in the file. Nothing kept here renews that, and no sign-in would.
        link.status, link.error = FAILED, t.MCP_KEY_REFUSED
        return False
    async with link.renewing:
        current = hub.tokens.get(server, ACCESS)
        if current and refused != bearer(current):
            return True
        refresh, client_id, issuer = (
            hub.tokens.get(server, kind) for kind in (REFRESH, CLIENT_ID, ISSUER)
        )
        moved = ""
        try:
            if not (refresh and client_id and issuer) or hub.client is None:
                raise GrantRefused(t.MCP_UNAUTHORIZED.format(server=server.name))
            auth = link.auth
            if auth is None:
                auth = await discover(hub.client, server.url, link.challenge, hub.resolver)
            if auth.issuer != issuer:
                moved = t.MCP_OAUTH_MOVED.format(got=auth.issuer[:200], expected=issuer[:200])
                raise GrantRefused(moved)
            link.auth = auth
            tokens = await token(
                hub.client,
                auth,
                hub.resolver,
                grant_type="refresh_token",
                refresh_token=refresh,
                client_id=client_id,
            )
            # A server may renew the access token and leave the refresh token as it was.
            kept = {ACCESS: tokens.access, REFRESH: tokens.refresh or refresh}
            hub.tokens.put(server, kept)
        except GrantRefused:
            # Nothing kept can sign in again: only the owner can, and the screen says so.
            forget(hub, link)
            link.status, link.error = SIGNED_OUT, moved
            return False
        except McpError as exc:
            # No word that the grant is spent. The row says what was heard instead, since
            # the call itself can only say that its sign-in ran out.
            link.error = str(exc)
            return False
        except (ValueError, OSError) as exc:
            link.error = t.MCP_OAUTH_STORE.format(error=exc)
            return False
        link.error = ""
        return True
