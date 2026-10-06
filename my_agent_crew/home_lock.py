"""One server at a time on a home.

A server that starts takes over what the last one left: it closes the runs still marked as
running and carries the cut turns on (`turn_resume.py`). Under a server that is still up,
that ends its turns in the record and runs each of them a second time. So a server holds
its home from before it opens what is kept there until its process is gone, and one that
finds the home held does not start.

What is held is the home directory itself, by a lock the system drops with the process
however it ended: a start leaves no file behind, and none that a stop forgot to clear.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path


class HomeHeld(Exception):
    """Another process holds this home."""


def hold(home: Path) -> int:
    """Take `home` for this process, making it when it is not there yet. Raises HomeHeld
    when another process holds it. The descriptor that is returned is the hold: a server
    never closes it, and no process it starts is handed it."""
    home.mkdir(parents=True, exist_ok=True)
    held = os.open(home, os.O_RDONLY)
    try:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(held)
        if isinstance(exc, BlockingIOError):
            raise HomeHeld(str(home)) from None
        raise  # no lock to be had here at all: said as it came, never as a home in use
    return held
