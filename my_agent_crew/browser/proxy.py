"""The one way out of a crew browser: a forward proxy in this process that refuses every
private address.

A page reaches the network in ways no page-level hook sees: the hop of a redirect, a
sub-resource, `fetch`, a WebSocket. Chromium is started so that all of it comes through here
(`pool.py`), and each connection is decided where it is made: the name is resolved here,
every address it resolves to is checked (`network.py`), and the connection goes to an address
that was checked, never to the name again.

It listens on loopback under a password made for this launch, so nothing else on the machine
borrows the way out. One request is carried per plain connection: what a client sends after
it is never passed on, since it would reach the first host under another host's name.
"""

from __future__ import annotations

import asyncio
import base64
import hmac
import secrets
from collections import deque
from collections.abc import Coroutine
from typing import Any
from urllib.parse import urlsplit

from my_agent_crew.browser.network import Allow, reachable
from my_agent_crew.tools.web import Resolver, resolve_host

USER = "crew"
HEAD_LIMIT = 64 * 1024
CONNECT_SECONDS = 10.0
REFUSED_KEPT = 50
# Headers that speak to this proxy, or about this one connection, and not to the site.
HOP_HEADERS = ("proxy-", "connection:", "keep-alive:")
REASONS = {
    400: "Bad Request",
    403: "Forbidden: the crew's browser does not reach private addresses",
    407: "Proxy Authentication Required",
    411: "Length Required",
    502: "Bad Gateway",
}
Stream = tuple[asyncio.StreamReader, asyncio.StreamWriter]


class FilteringProxy:
    def __init__(self, resolver: Resolver = resolve_host, allow: Allow | None = None) -> None:
        self._resolver = resolver
        self._allow = allow
        self._password = secrets.token_urlsafe(24)
        self._token = base64.b64encode(f"{USER}:{self._password}".encode()).decode()
        self._server: asyncio.Server | None = None
        self._open: set[asyncio.Task[Any]] = set()
        # The hosts last refused and how many were ever, so a tool can say what a page tried.
        self.refused: deque[str] = deque(maxlen=REFUSED_KEPT)
        self.refused_total = 0
        self.port = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0, limit=HEAD_LIMIT)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is None:
            return
        server, self._server = self._server, None
        server.close()
        for task in list(self._open):
            task.cancel()
        await asyncio.gather(*self._open, return_exceptions=True)
        await server.wait_closed()

    @property
    def launch_option(self) -> dict[str, str]:
        """What Playwright is handed to send a browser through here."""
        server = f"http://127.0.0.1:{self.port}"
        return {"server": server, "username": USER, "password": self._password}

    def refused_since(self, mark: int) -> list[str]:
        """The hosts refused since `refused_total` read `mark`, the most recent last."""
        count = min(self.refused_total - mark, len(self.refused))
        return list(self.refused)[len(self.refused) - count :] if count > 0 else []

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        self._open.add(task)
        try:
            await self._exchange(reader, writer)
        except (OSError, EOFError, ValueError, asyncio.LimitOverrunError):
            pass  # a client that hung up or sent what is no request is owed nothing
        finally:
            self._open.discard(task)
            writer.close()

    async def _exchange(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1")
        request, *lines = head[:-4].split("\r\n")
        method, target, _ = request.split(" ", 2)
        headers = {k.strip().lower(): v.strip() for k, _, v in (ln.partition(":") for ln in lines)}
        scheme, _, token = headers.get("proxy-authorization", "").partition(" ")
        if scheme.lower() != "basic" or not hmac.compare_digest(token.strip(), self._token):
            return await _answer(writer, 407, 'Proxy-Authenticate: Basic realm="crew"\r\n')
        if method.upper() == "CONNECT":
            parts = urlsplit(f"//{target}")
            upstream = await self._reach(parts.hostname, parts.port or 443)
            if isinstance(upstream, int):
                return await _answer(writer, upstream)
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            return await _first_of(_pipe(reader, upstream[1]), _pipe(upstream[0], writer), upstream)
        parts = urlsplit(target)
        length = headers.get("content-length", "0")
        if parts.scheme != "http" or not parts.hostname:
            return await _answer(writer, 400)
        if "transfer-encoding" in headers or not length.isdigit():
            return await _answer(writer, 411)
        upstream = await self._reach(parts.hostname, parts.port or 80)
        if isinstance(upstream, int):
            return await _answer(writer, upstream)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        kept = [ln for ln in lines if ln and not ln.lower().startswith(HOP_HEADERS)]
        sent = "\r\n".join([f"{method} {path} HTTP/1.1", *kept, "Connection: close"])
        upstream[1].write(sent.encode("latin-1") + b"\r\n\r\n")
        if int(length):
            upstream[1].write(await reader.readexactly(int(length)))
        await upstream[1].drain()
        # Anything more from the client ends the exchange: it is never passed on.
        await _first_of(reader.read(1), _pipe(upstream[0], writer), upstream)

    async def _reach(self, host: str | None, port: int) -> Stream | int:
        """A connection to an address of `host` that was checked, or the status that says
        why there is none."""
        if not host:
            return 400
        try:
            addresses = await asyncio.to_thread(self._resolver, host)
        except OSError:
            return 502
        if not reachable(addresses, port, self._allow):
            self.refused.append(host)
            self.refused_total += 1
            return 403
        for address in dict.fromkeys(addresses):
            try:
                return await asyncio.wait_for(
                    asyncio.open_connection(address, port, limit=HEAD_LIMIT), CONNECT_SECONDS
                )
            except (OSError, TimeoutError):
                continue
        return 502


async def _answer(writer: asyncio.StreamWriter, status: int, extra: str = "") -> None:
    body = REASONS[status].encode()
    head = (
        f"HTTP/1.1 {status} {REASONS[status].split(':')[0]}\r\n{extra}"
        f"Content-Type: text/plain\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n"
    )
    writer.write(head.encode("latin-1") + body)
    await writer.drain()


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while data := await reader.read(65536):
        writer.write(data)
        await writer.drain()


async def _first_of(one: Coroutine[Any, Any, Any], other: Coroutine[Any, Any, Any], up: Stream):
    """Both directions of one exchange, over as soon as either is: the other has nobody
    left to talk to."""
    tasks = [asyncio.ensure_future(one), asyncio.ensure_future(other)]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        up[1].close()
