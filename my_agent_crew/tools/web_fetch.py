"""The plain GET behind `fetch_url`: bounded in time and in bytes. A page that trickles
or never ends used to hold the turn for the whole 20-second budget and then be cut to
`MAX_PAGE_CHARS` anyway; now the connection gets 5 seconds, each read 10, and the body is
read only up to `MAX_PAGE_BYTES` before the socket is closed."""

from __future__ import annotations

import httpx

from my_agent_crew import texts
from my_agent_crew.tools.registry import ToolError

# Connect fast or not at all; a slow read is a slow server, and the model would rather
# hear that than wait. Total wall time stays well under the old single 20-second budget
# for the common case of one request.
FETCH_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
# Half a megabyte of HTML is far more than the few thousand characters the model gets to
# read; anything past it is downloaded for nothing.
MAX_PAGE_BYTES = 512 * 1024


async def fetch_page(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    """`(body, content_type)` for a 2xx page, the redirect notice with an empty type for a
    3xx, and a `ToolError` for anything else. The body is decoded with the charset the
    server named, or UTF-8 with replacement so one odd byte does not lose the page."""
    try:
        async with client.stream("GET", url, follow_redirects=False, timeout=FETCH_TIMEOUT) as resp:
            if 300 <= resp.status_code < 400:
                return texts.URL_REDIRECT.format(location=resp.headers.get("location", "?")), ""
            if resp.status_code >= 400:
                raise ToolError(texts.URL_STATUS.format(status=resp.status_code))
            raw = await _read_capped(resp)
            content_type = resp.headers.get("content-type", "")
    except httpx.HTTPError as exc:
        raise ToolError(texts.URL_UNREACHABLE.format(error=exc)) from exc
    return raw.decode(resp.charset_encoding or "utf-8", errors="replace"), content_type


async def _read_capped(resp: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in resp.aiter_bytes():
        chunks.append(chunk)
        size += len(chunk)
        if size >= MAX_PAGE_BYTES:
            break
    return b"".join(chunks)[:MAX_PAGE_BYTES]
