"""Refusing API requests that did not come from this server's own page.

The server has no login: it listens on the machine, and whoever reaches the port is the
person. A web page on another site can still reach it through DNS rebinding — its own
name made to resolve to 127.0.0.1 — and then its requests are same-origin to the browser.
Two headers give that away, and a browser does not let a page forge either:

- `Host` carries the name the page was loaded under. The server is reached by an IP or
  by `localhost`; any other name is what a rebinding attack arrives under, unless the
  person listed it in `MY_AGENT_ALLOWED_HOSTS` (a Tailscale name, say).
- `Origin`, when sent, must be a loopback address or the same host, so a page on another
  site cannot post here even when the Host looks right.

Everything under `/api` is guarded, not only the keys: a rebound page that could patch
the master's Telegram chat, or start a turn with tools, would be as bad as one that could
write the env file.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Awaitable, Callable, Mapping
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from my_agent_crew.texts_credentials import FOREIGN_ORIGIN

ALLOWED_HOSTS_ENV = "MY_AGENT_ALLOWED_HOSTS"
GUARDED_PREFIX = "/api/"


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


def is_local_request(host_header: str, origin: str | None, extra: frozenset[str]) -> bool:
    host = _hostname(f"//{host_header}")
    if host is None or not (host == "localhost" or _ip(host) is not None or host in extra):
        return False
    if origin is None:
        return True  # not a browser, or a same-origin GET
    origin_host = _hostname(origin)
    if origin_host is None:
        return False  # `Origin: null` comes from sandboxed and file pages
    loopback = origin_host == "localhost" or bool((ip := _ip(origin_host)) and ip.is_loopback)
    return loopback or origin_host == host


def install_local_guard(app: FastAPI, extra: frozenset[str]) -> None:
    @app.middleware("http")
    async def local_only(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path.startswith(GUARDED_PREFIX) and not is_local_request(
            request.headers.get("host", ""), request.headers.get("origin"), extra
        ):
            return JSONResponse({"detail": FOREIGN_ORIGIN}, status_code=403)
        return await call_next(request)
