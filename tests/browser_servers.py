"""Small local servers the browser tests reach through the filtering proxy. A test's proxy is
told the ports it may reach; every other local port stands for a private service, which the
real rule refuses."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from my_agent_crew.browser.pool import BrowserPool
from my_agent_crew.config_browser import BrowserSettings

# A body is text, or a list of text and pauses in seconds for a page that comes in pieces.
Body = str | list[str | float]
Page = Callable[["Site"], tuple[int, dict[str, str], Body]] | str


class Site:
    """An HTTP server on loopback that keeps what it was asked. `pages` maps a path to its
    body, or to a function giving status, headers and body."""

    def __init__(self, pages: dict[str, Page] | None = None) -> None:
        self.pages: dict[str, Page] = dict(pages or {})
        self.seen: list[str] = []
        self.heads: list[dict[str, str]] = []
        self.bodies: list[bytes] = []
        self.cut: list[str] = []  # the paths whose answer the browser hung up on
        site = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _serve(self) -> None:
                size = int(self.headers.get("content-length") or 0)
                site.bodies.append(self.rfile.read(size) if size else b"")
                site.seen.append(f"{self.command} {self.path}")
                site.heads.append({k.lower(): v for k, v in self.headers.items()})
                page = site.pages.get(self.path.split("?")[0], "")
                status, headers, body = page(site) if callable(page) else (200, {}, page)
                if self.path.split("?")[0] not in site.pages:
                    status, body = 404, "không có trang này"
                pieces = body if isinstance(body, list) else [body]
                self.send_response(status)
                for name, value in {"content-type": "text/html; charset=utf-8", **headers}.items():
                    self.send_header(name, value)
                if len(pieces) == 1:
                    self.send_header("content-length", str(len(pieces[0].encode("utf-8"))))
                else:  # the page ends where the connection does
                    self.send_header("connection", "close")
                    self.close_connection = True
                try:
                    self.end_headers()
                    for piece in pieces:
                        if isinstance(piece, str):
                            self.wfile.write(piece.encode("utf-8"))
                            self.wfile.flush()
                        else:
                            time.sleep(piece)
                except OSError:  # the browser gave up on a slow page and hung up
                    self.close_connection = True
                    site.cut.append(self.path)

            do_GET = do_POST = _serve

            def log_message(self, *args) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def url(self, path: str = "/", host: str = "127.0.0.1") -> str:
        return f"http://{host}:{self.port}{path}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@contextmanager
def sites(*pages: dict[str, Page]) -> Iterator[list[Site]]:
    made = [Site(p) for p in pages]
    try:
        yield made
    finally:
        for site in made:
            site.close()


class Recorder:
    """A server that keeps every byte it is sent, answers the first request and never hangs
    up first: what a site that ignores `Connection: close` would be."""

    ANSWER = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"

    def __init__(self) -> None:
        self.received = b""
        self.port = 0
        self._server: asyncio.Server | None = None

    async def __aenter__(self) -> Recorder:
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._server.close()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        answered = False
        try:
            while data := await reader.read(65536):
                self.received += data
                if not answered and b"\r\n\r\n" in self.received:
                    answered = True
                    writer.write(self.ANSWER)
                    await writer.drain()
        except ConnectionError:
            pass
        finally:
            writer.close()


def only(*allowed: Site | Recorder) -> Callable[[str, int], bool]:
    """What a test's proxy lets through: these servers and nothing else on the machine."""
    ports = {site.port for site in allowed}
    return lambda address, port: port in ports


async def ask(port: int, raw: bytes, more: bytes = b"", wait: float = 0.3) -> bytes:
    """Sends `raw` to a server as one connection and reads until it closes. `more` is sent
    after the first bytes of the answer, as a client reusing the connection would."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(raw)
    await writer.drain()
    answer = b""
    try:
        if more:
            answer += await asyncio.wait_for(reader.read(65536), 5)
            writer.write(more)
            await writer.drain()
            await asyncio.sleep(wait)
        answer += await asyncio.wait_for(reader.read(), 5)
    except (TimeoutError, ConnectionError):
        pass
    finally:
        writer.close()
    return answer


def local_names(host: str) -> list[str]:
    """The names a test's browser resolves: this machine's and no other, so no test reaches
    a server that is not its own."""
    if host == "localhost" or host.replace(".", "").isdigit():
        return ["127.0.0.1"]
    raise OSError(f"no such host in a test: {host}")


class Clock:
    """A clock a test moves by hand."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@asynccontextmanager
async def browsers(
    root: Path,
    *allowed: Site,
    clock: Clock | None = None,
    resolver: Callable[[str], list[str]] | None = None,
    allow: Callable[[str, int], bool] | None = None,
    **settings: object,
) -> AsyncIterator[BrowserPool]:
    """A pool whose browsers reach the given test servers and nothing else on this machine,
    stopped with everything it started when the test is over. A test that wants to see what
    its browser asked for gives an `allow` of its own."""
    pool = BrowserPool(
        root,
        BrowserSettings(enabled=True, **settings),
        allow=allow or only(*allowed),
        **({"clock": clock} if clock else {}),
        resolver=resolver or local_names,
    )
    try:
        yield pool
    finally:
        # A stop that never ends is a failed test, not a run that never ends.
        async with asyncio.timeout(60):
            await pool.stop_all()
