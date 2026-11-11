"""Every HTTP client the engine makes comes from `egress.counted_client`, so none sends a
request whose host is not counted. A source file that makes one itself, calls httpx's
module functions, or brings in another HTTP library fails here."""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "my_agent_crew"
FACTORY = PACKAGE / "egress.py"
UNCOUNTED = re.compile(
    r"\bhttpx\s*\.\s*(AsyncClient|Client|get|post|put|patch|delete|head|options|request|stream)"
    r"\s*\("
    r"|^\s*from\s+httpx\s+import\b"
    r"|^\s*(import|from)\s+(aiohttp|requests|websockets|websocket|urllib3|http\.client|pycurl)\b"
    r"|\burllib\s*\.\s*request\b|^\s*from\s+urllib\s+import\s+.*\brequest\b",
    re.MULTILINE,
)


def uncounted(source: str) -> list[str]:
    return [match.group(0).strip() for match in UNCOUNTED.finditer(source)]


def test_no_source_file_makes_an_http_client_of_its_own():
    found = {
        path.relative_to(PACKAGE).as_posix(): hits
        for path in PACKAGE.rglob("*.py")
        if path != FACTORY and (hits := uncounted(path.read_text(encoding="utf-8")))
    }
    assert found == {}


def test_the_factory_is_the_one_place_a_client_is_made():
    assert uncounted(FACTORY.read_text(encoding="utf-8")) == ["httpx.AsyncClient("]


def test_the_scan_knows_a_client_when_it_sees_one():
    for line in (
        "client = httpx.AsyncClient(timeout=5)",
        "with httpx.Client() as c:",
        "httpx . AsyncClient (",
        "page = httpx.get(url)",
        "async with httpx.stream('GET', url) as r:",
        "from httpx import AsyncClient",
        "import requests",
        "    import aiohttp",
        "from websockets import connect",
        "import http.client",
        "urllib.request.urlopen(url)",
        "from urllib import parse, request",
    ):
        assert uncounted(line), line
    for line in (
        "def f(client: httpx.AsyncClient | None = None) -> httpx.Response:",
        "client = client or counted_client(timeout=httpx.Timeout(5))",
        "from urllib.parse import urlsplit",
        "self.requests: list[Request] = []",
        "await client.get(url)",
    ):
        assert not uncounted(line), line
