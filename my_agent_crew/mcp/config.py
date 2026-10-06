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

# How far a tool is let in. `direct`: told to the model like a built-in. `deferred`: told
# only once `tool_search` has loaded it. `codemode`: called from a script, or loaded the
# same way. `hidden`: not reachable at all.
DIRECT, DEFERRED, CODEMODE, HIDDEN = "direct", "deferred", "codemode", "hidden"
EXPOSURES = (DIRECT, DEFERRED, CODEMODE, HIDDEN)
DEFAULT_TIMEOUT = 60.0
ENV_REF = re.compile(r"\$\{([A-Z][A-Z0-9_]{0,63})\}")
# The only hosts plain http is spoken to: a server on this machine.
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


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
        filled = (
            (key, ENV_REF.sub(lambda m: env[m.group(1)], value)) for key, value in self.headers
        )
        # A key pasted with the line break after it is still the key; sent so, no request is.
        return {key: value.strip() for key, value in filled}
