"""MCP servers as `config.yaml` names them: where each one is, how its requests are
authorised, and how far its tools are let in.

Nothing here talks to a server. A server's address is the owner's, written in the file:
no tool argument and nothing a server answers ever picks where a request goes. The file
carries no secret either. A header takes its value from the environment, as `${NAME}`,
and one written out in the file is refused rather than kept.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

# How far a tool is let in. `direct`: told to the model like a built-in. `deferred`: told
# only once `tool_search` has loaded it. `codemode`: called from a script, or loaded the
# same way. `hidden`: not reachable at all.
DIRECT, DEFERRED, CODEMODE, HIDDEN = "direct", "deferred", "codemode", "hidden"
EXPOSURES = (DIRECT, DEFERRED, CODEMODE, HIDDEN)
DEFAULT_TIMEOUT = 60.0
MAX_TIMEOUT = 600.0
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")
HEADER_RE = re.compile(r"[A-Za-z0-9-]{1,64}")
ENV_REF = re.compile(r"\$\{([A-Z][A-Z0-9_]{0,63})\}")
# The only hosts plain http is spoken to: a server on this machine.
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
# Headers the client writes itself; one set from the file would break the protocol.
OWN_HEADERS = frozenset(
    {"host", "accept", "content-type", "content-length", "mcp-session-id", "mcp-protocol-version"}
)
SERVER_KEYS = frozenset(
    {"url", "description", "headers", "exposure", "tool_exposure", "read_only", "timeout"}
)


class MissingEnv(ValueError):
    """A header names variables the environment does not hold."""

    def __init__(self, names: list[str]):
        super().__init__(", ".join(names))
        self.names = names


def matches(pattern: str, name: str) -> bool:
    """`*` stands for any run of characters; every other character is itself."""
    return re.fullmatch(".*".join(map(re.escape, pattern.split("*"))), name) is not None


@dataclass(frozen=True)
class McpServer:
    name: str
    url: str
    description: str = ""
    # (header, value) as written. `${NAME}` in a value is read from the environment each
    # time a request is made, so a key changed since is the one sent.
    headers: tuple[tuple[str, str], ...] = ()
    exposure: str = DEFERRED
    # (pattern, exposure) in the file's order: a tool's exact name wins, then the first
    # pattern that matches it, then the server's own level.
    tool_exposure: tuple[tuple[str, str], ...] = ()
    # Tools the owner says only read. They run without asking and may be made again after
    # a restart; every other tool of the server asks first and is never repeated.
    read_only: tuple[str, ...] = ()
    timeout: float = DEFAULT_TIMEOUT

    @property
    def env_key(self) -> str:
        """The server's name as it appears inside an environment variable's name."""
        return self.name.upper().replace("-", "_")

    def exposure_of(self, tool: str) -> str:
        rules = dict(self.tool_exposure)
        if tool in rules:
            return rules[tool]
        return next((e for p, e in self.tool_exposure if matches(p, tool)), self.exposure)

    def reads_only(self, tool: str) -> bool:
        return any(matches(pattern, tool) for pattern in self.read_only)

    def env_names(self) -> tuple[str, ...]:
        found = (name for _, value in self.headers for name in ENV_REF.findall(value))
        return tuple(dict.fromkeys(found))

    def request_headers(self, env: Mapping[str, str]) -> dict[str, str]:
        missing = [name for name in self.env_names() if not env.get(name)]
        if missing:
            raise MissingEnv(missing)
        return {key: ENV_REF.sub(lambda m: env[m.group(1)], value) for key, value in self.headers}


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
