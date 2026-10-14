"""The mark macOS keeps on a file that came from outside: a file that carries it is checked
by the system before anything opens it as a program.

It is put on through the descriptor a file is written by, so it is on the very file that was
made, whatever its name is made to lead to meanwhile. Through `ctypes` and nothing else;
elsewhere than macOS there is no such mark and nothing is done."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import time

log = logging.getLogger(__name__)

NAME = b"com.apple.quarantine"
# The flags of a file a program fetched, the second it came (in hex), and who fetched it.
VALUE = "0081;{at:x};my-agent-crew;"


def mark(fd: int, platform: str = sys.platform) -> None:
    """Put the mark on the open file `fd`. A system that will not take it is noted and the
    file is kept all the same: the mark is one more guard, not what a file is kept for."""
    if platform != "darwin":
        return
    value = VALUE.format(at=int(time.time())).encode("ascii")
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        put = libc.fsetxattr
        put.restype = ctypes.c_int
        put.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.c_uint32,
            ctypes.c_int,
        ]
        if put(fd, NAME, value, len(value), 0, 0) != 0:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code))
    except (OSError, AttributeError, ValueError) as exc:
        log.debug("a kept file carries no quarantine mark: %s", exc)
