"""Where a server's sign-in is kept: the home's env file and this process's environment,
under names made from the server's own.

A token is a secret like a provider's key and lives where those live. It is written
owner-only, read back into the environment at the next start, and never handed to
anything that answers a request: what is listed of a server says only whether it is
signed in.
"""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping
from pathlib import Path

from my_agent_crew.env_file import check_value, env_path, remove_env, set_env
from my_agent_crew.mcp.config import McpServer

ACCESS, REFRESH, CLIENT_ID = "ACCESS_TOKEN", "REFRESH_TOKEN", "CLIENT_ID"


def env_name(server: McpServer, kind: str) -> str:
    return f"MCP_{server.env_key}_{kind}"


def bearer(access: str) -> str:
    """The Authorization header an access token is sent in."""
    return f"Bearer {access}"


def managed_names(servers: Iterable[McpServer]) -> frozenset[str]:
    """The variables a sign-in keeps its tokens in, so the screen that lists keys leaves
    them to the screen that signs in and out. The client id is no secret and is listed."""
    return frozenset(env_name(server, kind) for server in servers for kind in (ACCESS, REFRESH))


class TokenStore:
    def __init__(self, home: Path | None, environ: MutableMapping[str, str]):
        # Without a home nothing is written down: the sign-in lasts as long as the process.
        self._path = env_path(home) if home is not None else None
        self._environ = environ

    def get(self, server: McpServer, kind: str) -> str:
        return self._environ.get(env_name(server, kind), "")

    def put(self, server: McpServer, kind: str, value: str) -> None:
        """Keep `value`; an empty one forgets what was kept. Raises ValueError for a value
        the env file cannot hold, and OSError when the file cannot be written."""
        name = env_name(server, kind)
        if not value:
            if self._path is not None:
                remove_env(self._path, name)
            self._environ.pop(name, None)
            return
        value = check_value(value)
        if self._path is not None:
            set_env(self._path, name, value)
        self._environ[name] = value
