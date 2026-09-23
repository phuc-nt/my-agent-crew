"""Refusing API requests that did not come from this server's own page.

The server has no login: it listens on the machine, and whoever reaches the port is the
person. A web page on another site can still reach it through DNS rebinding — its own
name made to resolve to 127.0.0.1 — and then its requests are same-origin to the browser.
Two headers give that away, and a browser does not let a page forge either:

- `Host` carries the name the page was loaded under. The server is reached by an IP or
  by `localhost`; any other name is what a rebinding attack arrives under, unless the
  person listed it in `MY_AGENT_ALLOWED_HOSTS` (a Tailscale name, say).
- `Origin`, when sent, must be exactly the host and port asked for, so a page on another
  site — or another local port, a dev server an agent started — cannot post here even
  when the Host looks right. The Vite dev proxy passes `localhost:5173` as both.

Every path is guarded, not only the keys: a rebound page that could patch the master's
Telegram chat, start a turn with tools, or fetch a file would be as bad as one that could
write the env file, and the page itself has nothing to show a stranger.

A refused name is said back with what would let it in, and logged once: someone opening
the server through a tunnel or a Tailscale name is the likelier visitor than an attacker,
and a bare 403 would leave them guessing. The list itself is only read from the
environment at startup — widening who may use a server with no login is not a click.
"""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Awaitable, Callable, Mapping
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from my_agent_crew.texts_credentials import FOREIGN_HOST, FOREIGN_ORIGIN

logger = logging.getLogger(__name__)
ALLOWED_HOSTS_ENV = "MY_AGENT_ALLOWED_HOSTS"
# A refused name is logged once; the set is capped so a stream of made-up names cannot grow it.
MAX_LOGGED_HOSTS = 32
SHOWN_HOST_CHARS = 100


def allowed_hosts(env: Mapping[str, str]) -> frozenset[str]:
    raw = env.get(ALLOWED_HOSTS_ENV) or ""
    return frozenset(name.strip().lower() for name in raw.split(",") if name.strip())


def _hostname(url: str) -> str | None:
    """The host part, or None when there is none or the header does not parse."""
    try:
        return urlsplit(url).hostname or None
    except ValueError:
        return None


def _ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def refusal(host_header: str, origin: str | None, extra: frozenset[str]) -> str | None:
    """Why the request is turned away, or None when it may pass."""
    host = _hostname(f"//{host_header}")
    if host is None:
        return FOREIGN_ORIGIN
    if not (host == "localhost" or _ip(host) is not None or host in extra):
        return FOREIGN_HOST.format(host=host[:SHOWN_HOST_CHARS], env=ALLOWED_HOSTS_ENV)
    if origin is None:
        return None  # not a browser, or a same-origin GET
    try:
        origin_at = urlsplit(origin).netloc.lower()
    except ValueError:
        return FOREIGN_ORIGIN
    # `Origin: null` (sandboxed and file pages) has no host and never matches.
    return None if origin_at and origin_at == host_header.lower() else FOREIGN_ORIGIN


def is_local_request(host_header: str, origin: str | None, extra: frozenset[str]) -> bool:
    return refusal(host_header, origin, extra) is None


def install_local_guard(app: FastAPI, extra: frozenset[str]) -> None:
    logged: set[str] = set()

    @app.middleware("http")
    async def local_only(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        host_header = request.headers.get("host", "")
        reason = refusal(host_header, request.headers.get("origin"), extra)
        if reason is None:
            return await call_next(request)
        if host_header not in logged and len(logged) < MAX_LOGGED_HOSTS:
            logged.add(host_header)
            logger.warning(
                "refused a request for host %r (%s)",
                host_header[:SHOWN_HOST_CHARS],
                ALLOWED_HOSTS_ENV,
            )
        return JSONResponse({"detail": reason}, status_code=403)
