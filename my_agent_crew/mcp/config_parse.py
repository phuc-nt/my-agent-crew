"""MCP servers read out of `config.yaml`: every setting checked, and the first thing wrong
named. A mistake here stops the start, like any other in the file."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from my_agent_crew.mcp.config import (
    DEFAULT_TIMEOUT,
    DEFERRED,
    ENV_REF,
    EXPOSURES,
    LOOPBACK_HOSTS,
    McpServer,
)

MAX_TIMEOUT = 600.0
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")
HEADER_RE = re.compile(r"[A-Za-z0-9-]{1,64}")
# Headers the client writes itself; one set from the file would break the protocol.
OWN_HEADERS = frozenset(
    {"host", "accept", "content-type", "content-length", "mcp-session-id", "mcp-protocol-version"}
)
SERVER_KEYS = frozenset(
    {"url", "description", "headers", "exposure", "tool_exposure", "read_only", "timeout"}
)


def _fail(name: str, problem: str) -> ValueError:
    return ValueError(f"config.yaml: mcp_servers.{name}: {problem}")


def _url(name: str, raw: Any) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise _fail(name, "url is required")
    url = raw.strip()
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        raise _fail(name, f"url {url!r} does not parse") from None
    # A password never comes without the user part it follows, so one check covers both.
    if not host or parts.username is not None or parts.fragment:
        raise _fail(name, "url must be a plain address: a host, no user, password or #fragment")
    if parts.scheme != "https" and not (parts.scheme == "http" and host in LOOPBACK_HOSTS):
        raise _fail(name, "url must be https; plain http is only for a server on this machine")
    return url


def _headers(name: str, raw: Any) -> tuple[tuple[str, str], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise _fail(name, "headers must map a header's name to its value")
    for key, value in raw.items():
        if not isinstance(key, str) or not HEADER_RE.fullmatch(key) or key.lower() in OWN_HEADERS:
            raise _fail(name, f"header {key!r} cannot be set")
        if not isinstance(value, str) or not ENV_REF.search(value):
            raise _fail(
                name,
                f"header {key} must take its value from the environment, written ${{NAME}}: "
                "this file never holds a key",
            )
    return tuple(raw.items())


def _exposure(name: str, key: str, raw: Any) -> str:
    if raw not in EXPOSURES:
        raise _fail(name, f"{key} must be one of {list(EXPOSURES)}, got {raw!r}")
    return raw


def _tool_exposure(name: str, raw: Any) -> tuple[tuple[str, str], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, dict) or not all(isinstance(k, str) and k for k in raw):
        raise _fail(name, "tool_exposure must map a tool's name or pattern to a level")
    return tuple(
        (tool, _exposure(name, f"tool_exposure.{tool}", level)) for tool, level in raw.items()
    )


def _patterns(name: str, key: str, raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    # A string is iterable: "notion-*" read as a list would be seven one-letter patterns.
    if not isinstance(raw, list) or not all(isinstance(v, str) and v.strip() for v in raw):
        raise _fail(name, f"{key} must be a list of tool names or patterns")
    return tuple(v.strip() for v in raw)


def _timeout(name: str, raw: Any) -> float:
    if raw is None:
        return DEFAULT_TIMEOUT
    if isinstance(raw, bool) or not isinstance(raw, int | float) or not 0 < raw <= MAX_TIMEOUT:
        raise _fail(name, f"timeout must be seconds, above 0 and at most {int(MAX_TIMEOUT)}")
    return float(raw)


def parse_server(name: str, raw: Any) -> McpServer:
    if not NAME_RE.fullmatch(name):
        raise _fail(
            name, "a name is letters, digits, - and _, at most 32, starting with none of - _"
        )
    if not isinstance(raw, dict):
        raise _fail(name, "must be a mapping with at least a url")
    unknown = sorted(set(raw) - SERVER_KEYS)
    if unknown:
        raise _fail(name, f"unknown keys {unknown}")
    return McpServer(
        name=name,
        url=_url(name, raw.get("url")),
        description=str(raw.get("description") or "").strip(),
        headers=_headers(name, raw.get("headers")),
        exposure=_exposure(name, "exposure", raw.get("exposure", DEFERRED)),
        tool_exposure=_tool_exposure(name, raw.get("tool_exposure")),
        read_only=_patterns(name, "read_only", raw.get("read_only")),
        timeout=_timeout(name, raw.get("timeout")),
    )


def parse_servers(raw: Any) -> tuple[McpServer, ...]:
    """Every server the file names, or a ValueError naming the first thing wrong: a
    mistake here is worth stopping for, like any other in `config.yaml`."""
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise ValueError("config.yaml: mcp_servers must map a server's name to its settings")
    servers = tuple(parse_server(str(name), body) for name, body in raw.items())
    keys = [server.env_key for server in servers]
    clash = sorted(server.name for server in servers if keys.count(server.env_key) > 1)
    if clash:
        # Each server keeps its sign-in under variables named after it.
        raise ValueError(f"config.yaml: mcp_servers: {clash} differ only by case, - or _")
    return servers
