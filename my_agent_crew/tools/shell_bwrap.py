"""The Linux sandbox for the same commands, where macOS `sandbox-exec` is missing: bubblewrap
(`bwrap`), which needs the user namespaces some hosts do not give a process.

It holds the policy of `shell_sandbox.py` by other means. The whole file system is mounted
read-only and only the profile's write paths and the temp directories are mounted writable
over it. Offline, the command gets a network namespace of its own, with nothing in it but a
loopback no server listens on, so the server's port is closed with the rest. A private folder
is covered by an empty one, and so are the folders where a session's helpers listen (D-Bus,
the user's systemd), which would start something outside for whoever asks. A mount point is
neither moved nor removed from inside, which is what the macOS profile says with its rules on
the folders above a private one.

What it cannot say is the network on with one port closed: a namespace has the network or
has none. The server's API asks for no login (`server_rules`), so a command with the network
that reaches it has something unsandboxed act for it; such a command is refused here, not run
looser. A server on a Unix socket (`--uds`) names no port: the socket's folder is covered like
a private one, offline or not, and a command with the network runs.

Nor can it deny forking, which the script child's macOS profile does (`SEALED`): under bwrap
the child may fork, and its children are as offline and as read-only as it is.

Two more differences. A write path not yet on disk is not mounted, so it stays read-only until
something outside the sandbox makes it. A private folder not yet on disk is not covered: a
command that may write above it could make it first, a folder for the browser to find."""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from pathlib import Path

from my_agent_crew.tools.shell_sandbox import served_folders, served_ports, temp_dirs

# Read-only root, a /dev of its own, gone when its parent is, and a session of its own so it
# cannot type into the terminal it was started from. The process table stays the host's, as
# it does under sandbox-exec: a container that masks parts of /proc (Docker does) refuses a
# fresh one to a process table of its own.
BASE = (
    "--ro-bind", "/", "/",
    "--dev", "/dev",
    "--proc", "/proc",
    "--die-with-parent", "--new-session",
)  # fmt: skip


def bwrap_path() -> Path | None:
    found = shutil.which("bwrap")
    return Path(found) if found else None


def helper_dirs() -> tuple[Path, ...]:
    """Where the system bus and the user's session bus and systemd listen, if they are here."""
    dirs = (Path("/run/dbus"), Path(f"/run/user/{os.getuid()}"))
    return tuple(d for d in dirs if d.is_dir())


def _covered(folders: Sequence[Path]) -> list[str]:
    return [arg for folder in folders if folder.exists() for arg in ("--tmpfs", str(folder))]


def bwrap_args(
    write_paths: Sequence[Path],
    *,
    network: bool = False,
    private: Sequence[Path] = (),
    cwd: Path | None = None,
) -> list[str] | None:
    """The arguments before the command, or None when bwrap cannot hold the policy: the
    network on while the server has named a port of its own. Paths must already be resolved."""
    if network and served_ports():
        return None
    args = list(BASE)
    if not network:
        args.append("--unshare-net")
    for path in (*write_paths, *temp_dirs()):
        args += ["--bind-try", str(path), str(path)]
    # After the writable mounts, so a private folder inside one is covered again.
    args += _covered((*helper_dirs(), *private, *served_folders()))
    if cwd is not None:
        args += ["--chdir", str(cwd)]
    return args


def sealed_args() -> list[str]:
    """The script child's: offline, and no write anywhere, the temp directories included."""
    # Offline is no network namespace's answer to a socket on disk: its folder is covered too.
    return [*BASE, "--unshare-net", *_covered((*helper_dirs(), *served_folders()))]
