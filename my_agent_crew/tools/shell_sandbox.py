"""The macOS sandbox an agent's `shell_run` commands run in, when its profile sets
`shell_network: false` or `shell_write_paths`.

Offline, denying sockets alone is not enough to keep data on the machine, because a sandboxed
process can still ask something unsandboxed to do the talking or the running for it:

- `open <url>` hands the URL to LaunchServices, and the browser it starts is not
  sandboxed; `launchctl`, `osascript` and `shortcuts` start other processes the same way,
  and `pbcopy` puts text on a clipboard that syncs to the owner's other devices.
- A file write is a delayed command: a line appended to a script a scheduled job runs,
  to a git hook, to `~/.zshrc`, or to a LaunchAgent plist runs later, outside the sandbox
  and with the network. So writes are denied everywhere except the paths the profile
  names (`shell_write_paths`) and the temp directories.
- A listening server outlives the command and hands files to whoever connects, so
  binding and inbound are denied along with outbound.

What is left open is reading, running local programs and writing data where the profile
says, which is what an agent that keeps a ledger needs.

With the network on, the same write rules keep an agent that works inside someone's repo
to its data: it can fetch and record, but it cannot edit the code, the scripts or the
config, and it cannot get `launchctl` or `osascript` to do that for it. Nor the server it
runs under: see `server_rules`.

Reading has one exception: a folder the server keeps private (a browser's logins, the
desktop helper's socket), which a sandboxed command neither reads nor writes nor connects
into, see `private_rules`."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")
# Programs whose whole job is to get something unsandboxed to act for the caller.
DENIED_PROGRAMS = (
    "/usr/bin/open",
    "/bin/launchctl",
    "/usr/bin/osascript",
    "/usr/bin/shortcuts",
    "/usr/bin/pbcopy",
)
# The same services reached without the programs, from any language's own API.
DENIED_SERVICES = ("com.apple.coreservices.launchservicesd", "com.apple.pasteboard.1")
# Where a command may always write: device files a shell redirect needs, and scratch
# space nothing runs from on its own.
DEVICE_RULES = '(literal "/dev/null") (regex #"^/dev/fd/") (regex #"^/dev/tty")'
# The ports this very server listens on, named once as it starts (`__main__`).
_served: set[int] = set()
# The folders of the Unix sockets it listens on instead, named the same way.
_served_dirs: set[Path] = set()


def temp_dirs() -> tuple[Path, ...]:
    """The person's TMPDIR and /tmp, resolved: the sandbox matches real paths, and on
    macOS both live under /private."""
    dirs = {Path("/tmp").resolve()}
    if tmp := os.environ.get("TMPDIR"):
        dirs.add(Path(tmp).resolve())
    return tuple(sorted(dirs))


def _quoted(path: Path) -> str:
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def helper_rules() -> str:
    """The rules that keep a process from getting something unsandboxed to act for it."""
    programs = " ".join(f'(literal "{p}")' for p in DENIED_PROGRAMS)
    services = " ".join(f'(global-name "{s}")' for s in DENIED_SERVICES)
    return (
        f"(deny process-exec {programs})"
        f'(deny mach-lookup {services} (global-name-regex #"^com\\.apple\\.lsd\\."))'
    )


def close_port(port: int) -> None:
    """Close `port`, the server's own, to every sandboxed command for as long as the
    process lives. Named before the crew is built: a profile is written with its tool."""
    _served.add(port)


def served_ports() -> frozenset[int]:
    """The ports `close_port` has named so far."""
    return frozenset(_served)


def close_socket(path: Path) -> None:
    """Close the folder of `path`, the server's own Unix socket, to every sandboxed command
    for as long as the process lives, as `close_port` does a port. A socket is reached by
    its path, so a folder can be closed where one port cannot: a command keeps the network
    on and still does not reach the server."""
    _served_dirs.add(Path(os.path.realpath(path.parent)))


def served_folders() -> tuple[Path, ...]:
    """The folders `close_socket` has named so far."""
    return tuple(sorted(_served_dirs))


def server_rules() -> str:
    """The rules that keep a command with the network off the server it runs under. The
    server's API asks for no login: a command that reaches it saves any agent's file, its
    own write paths among them, and so has something unsandboxed act for it. A port is
    closed on every address, since the server may listen on more than loopback; the cost
    is that such a command reaches that port number on no host."""
    return "".join(f'(deny network-outbound (remote tcp "*:{p}"))' for p in sorted(_served))


def private_rules(folders: Sequence[Path]) -> str:
    """The rules that close `folders` to a command altogether. Denying the read is not
    enough: the rules go by path, so a command that may write around such a folder would
    move it, or a folder above it, to a path no rule names and read it there. So the folder
    takes no write either, and no folder above it can be moved or removed.

    Nor is a socket in it connected to. With the network on, that is a rule of its own: a
    Unix socket is reached by `connect`, which the file rules do not judge, and whoever
    reaches the desktop helper's sees the screen and types on the keyboard."""
    if not folders:
        return ""
    inside = " ".join(f"(subpath {_quoted(folder)})" for folder in folders)
    above = sorted({parent for folder in folders for parent in folder.parents})
    held = " ".join(f"(literal {_quoted(parent)})" for parent in above)
    closed = f"(deny file-read* file-write* network-outbound {inside})"
    return f"{closed}(deny file-write-unlink {held})"


def sandbox_profile(
    write_paths: Sequence[Path], *, network: bool = False, private: Sequence[Path] = ()
) -> str:
    """The sandbox profile text. `write_paths` and `private` must already be resolved."""
    writable = " ".join(f"(subpath {_quoted(p)})" for p in (*write_paths, *temp_dirs()))
    offline = "" if network else "(deny network*)"
    return (
        f"(version 1)(allow default){offline}"
        # Later rules win, so the allow carves the writable paths out of the deny, and the
        # private folders are closed again even where they lie inside a writable one.
        f"(deny file-write*)(allow file-write* {writable} {DEVICE_RULES})"
        + helper_rules()
        + private_rules((*private, *served_folders()))
        + server_rules()
    )
