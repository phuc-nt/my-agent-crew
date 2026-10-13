"""The desktop of the machine's owner, reached through a small helper application that holds
the two macOS permissions and listens on a Unix socket. The machine's file says only where
that socket is. There is no switch here to turn the desktop on: a helper that is installed
and permitted is the machine's switch, and an agent's own file says whether that agent may
use it and on which applications (`agents/profile_desktop.py`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

# What an agent's `computer` key may say.
COMPUTER_OFF, COMPUTER_ON = "off", "on"
COMPUTER_MODES = (COMPUTER_OFF, COMPUTER_ON)
SOCKET_NAME = "sock"
# The longest path macOS binds a Unix socket to; the helper refuses a longer one.
SOCKET_PATH_BYTES = 103


def desktop_root(home: Path) -> Path:
    """Where the helper keeps its socket. Like the browsers' folder it is a place under the
    crew home no file tool and no sandboxed command goes into: whoever reaches the socket
    sees the screen and types on the keyboard. Named here once so the server that closes it
    and the client that connects agree."""
    return home / "desktop"


@dataclass(frozen=True)
class DesktopSettings:
    # Where the helper listens when the machine's file says so; empty is the socket under
    # the crew home (`socket_path`).
    socket: str = ""
    # The two below are set only by an agent's own file.
    mode: str = COMPUTER_OFF
    # Applications the agent may read the elements of and act on, each by its name or its
    # bundle id. Empty: it may look at the screen and nothing more.
    apps: tuple[str, ...] = ()

    @property
    def on(self) -> bool:
        return self.mode == COMPUTER_ON


def desktop_settings(env: Mapping[str, str], file_values: Mapping[str, object]) -> DesktopSettings:
    raw = env.get("MY_AGENT_DESKTOP_SOCKET") or file_values.get("desktop_socket")
    if raw is None:
        return DesktopSettings()
    if not isinstance(raw, str):
        raise ValueError(f"desktop_socket must be a path, got {raw!r}")
    if not raw.strip():
        return DesktopSettings()
    path = Path(raw.strip()).expanduser()
    if "\0" in raw or not path.is_absolute():
        raise ValueError(f"desktop_socket must be an absolute path, got {raw!r}")
    if len(str(path).encode()) > SOCKET_PATH_BYTES:
        raise ValueError(
            f"desktop_socket is longer than the {SOCKET_PATH_BYTES} bytes a socket path may have"
        )
    return DesktopSettings(socket=str(path))


def socket_path(home: Path, desktop: DesktopSettings) -> Path:
    """The socket the helper is looked for at. Worked out when it is asked for, from the home
    as it is then: the home's own path is settled only once its folder exists."""
    return Path(desktop.socket) if desktop.socket else desktop_root(home) / SOCKET_NAME
