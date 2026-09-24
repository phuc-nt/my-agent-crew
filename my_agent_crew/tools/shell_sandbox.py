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
config, and it cannot get `launchctl` or `osascript` to do that for it."""

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


def temp_dirs() -> tuple[Path, ...]:
    """The person's TMPDIR and /tmp, resolved: the sandbox matches real paths, and on
    macOS both live under /private."""
    dirs = {Path("/tmp").resolve()}
    if tmp := os.environ.get("TMPDIR"):
        dirs.add(Path(tmp).resolve())
    return tuple(sorted(dirs))


def _quoted(path: Path) -> str:
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def sandbox_profile(write_paths: Sequence[Path], *, network: bool = False) -> str:
    """The sandbox profile text. `write_paths` must already be resolved."""
    writable = " ".join(f"(subpath {_quoted(p)})" for p in (*write_paths, *temp_dirs()))
    programs = " ".join(f'(literal "{p}")' for p in DENIED_PROGRAMS)
    services = " ".join(f'(global-name "{s}")' for s in DENIED_SERVICES)
    offline = "" if network else "(deny network*)"
    return (
        f"(version 1)(allow default){offline}"
        # Later rules win, so the allow carves the writable paths out of the deny.
        f"(deny file-write*)(allow file-write* {writable} {DEVICE_RULES})"
        f"(deny process-exec {programs})"
        f'(deny mach-lookup {services} (global-name-regex #"^com\\.apple\\.lsd\\."))'
    )
