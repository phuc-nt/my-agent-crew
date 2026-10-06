"""Where a server's sign-in is kept: the home's env file and this process's environment,
under names made from the server's own.

A token is a secret like a provider's key and lives where those live. It is written
owner-only, read back into the environment at the next start, and never handed to
anything that answers a request: what is listed of a server says only whether it is
signed in.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping
from pathlib import Path

from my_agent_crew.env_file import check_value, env_path, set_many
from my_agent_crew.mcp.config import McpServer

ACCESS, REFRESH, CLIENT_ID = "ACCESS_TOKEN", "REFRESH_TOKEN", "CLIENT_ID"
# The authorization server that granted what is kept: a refresh token is said to no other.
ISSUER = "ISSUER"


def env_name(server: McpServer, kind: str) -> str:
    return f"MCP_{server.env_key}_{kind}"


def bearer(access: str) -> str:
    """The Authorization header an access token is sent in."""
    return f"Bearer {access}"


def managed_names(servers: Iterable[McpServer]) -> frozenset[str]:
    """The variables a sign-in keeps for itself, its tokens and who granted them, so the
    screen that lists keys leaves them to the screen that signs in and out. The client id
    is no secret and is listed: where no client may register itself, the owner writes it."""
    kinds = (ACCESS, REFRESH, ISSUER)
    return frozenset(env_name(server, kind) for server in servers for kind in kinds)


class TokenStore:
    def __init__(self, home: Path | None, environ: MutableMapping[str, str]):
        # Without a home nothing is written down: the sign-in lasts as long as the process.
        self._path = env_path(home) if home is not None else None
        self._environ = environ

    def get(self, server: McpServer, kind: str) -> str:
        return self._environ.get(env_name(server, kind), "")

    def put(self, server: McpServer, kept: Mapping[str, str]) -> None:
        """Keep each value under its kind; an empty one forgets what was kept there. All of
        them or none: a value the env file cannot hold raises ValueError and a file that
        cannot be written OSError, and either leaves everything as it was."""
        values = {env_name(server, kind): check_value(v) if v else "" for kind, v in kept.items()}
        if self._path is not None:
            set_many(self._path, values)
        for name, value in values.items():
            if value:
                self._environ[name] = value
            else:
                self._environ.pop(name, None)
