"""On Linux, the server's own process closed to the commands it runs.

A command runs as the same user as the server, and on Linux the same user may read another
of its processes through /proc: its environment, which holds the server's keys, and its
memory. bwrap does not give a command a process table of its own (`shell_bwrap.py`); its user
namespace keeps it out on the kernels tried, which the server does not count on. So the server
makes itself undumpable as it starts: its /proc files then belong to root, and a process
without the right to trace it reads none of them, sandboxed or not. A command the server
starts is dumpable again once it runs a program of its own, so nothing it runs is changed.

macOS has no /proc, and a sandboxed command there reads no other process's environment."""

from __future__ import annotations

import ctypes
import sys

PR_SET_DUMPABLE = 4


def close_own_process(libc: object | None = None) -> bool:
    """Make this process undumpable; whether it now is. False off Linux."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        libc = libc or ctypes.CDLL(None, use_errno=True)
    except OSError:
        return False
    return libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) == 0
