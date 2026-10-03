"""Headers every response carries, whichever route or guard made it.

`frame-ancestors 'self'` lets this app's own pages frame a response and nobody else. Without
it a page on any site could frame the web app, lay its own buttons over it and have the person
click Approve. The canvas render route is framed by the app itself, which is why `'self'` and
not `'none'`.

The rule goes out as its own `Content-Security-Policy` header and never merged into one a route
already set: a browser enforces every policy it is given, so each keeps its own meaning.

Plain ASGI rather than `BaseHTTPMiddleware`: that wraps the response body, and an event stream
must reach the client as it is written.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

FRAME_ANCESTORS = "frame-ancestors 'self'"


class SecurityHeaders:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def forbid_framing(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append("content-security-policy", FRAME_ANCESTORS)
            await send(message)

        await self.app(scope, receive, forbid_framing)
