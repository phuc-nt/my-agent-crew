"""Putting an exported canvas on disk, whole or not at all. The payload is written to a file
beside its place and moved in, so a write that stops half way leaves the old file as it was;
whatever stopped it, the half-written file and the folders made for it are taken away again.
From the moment it is made, the file being written is open to no reader the finished one is
closed to: a reader who opened it early would go on reading as the payload went in."""

from __future__ import annotations

import os
import secrets
import stat
from contextlib import suppress
from pathlib import Path

_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC


def write_whole(target: Path, payload: bytes) -> bool:
    """Puts `payload` at `target` and says whether a file was there. A new file gets the mode
    any written file gets; one that replaces another keeps the other's. On any failure the
    folders this call made are removed, deepest first and only while empty, and the error is
    raised as it came. It blocks: run in a thread."""
    made: list[Path] = []
    try:
        _make_folders(target.parent, made)
        return _move_in(target, payload)
    except BaseException:
        for folder in reversed(made):
            with suppress(OSError):  # one that holds something by now stays
                folder.rmdir()
        raise


def _make_folders(folder: Path, made: list[Path]) -> None:
    """Makes `folder` and each missing folder above it, adding to `made` the ones made here."""
    missing: list[Path] = []
    while not folder.exists():
        missing.append(folder)
        folder = folder.parent
    for folder in reversed(missing):
        with suppress(FileExistsError):  # another write made it first: not ours to take away
            folder.mkdir()
            made.append(folder)


def _move_in(target: Path, payload: bytes) -> bool:
    """Moving a file into place needs no leave from the one it replaces, so a file marked
    read-only is refused here, as a plain write would be."""
    old = stat.S_IMODE(target.stat().st_mode) if target.exists() else None
    if old is not None and not os.access(target, os.W_OK):
        raise PermissionError(target.name)
    temp = target.with_name(f".export-{secrets.token_hex(8)}.tmp")
    # A new file is made as any written file is, so the umask has shaped its mode before a
    # byte goes in. One that replaces another starts closed to everyone else and takes the
    # other's mode first; the umask is not read to do the same for a new file, since reading
    # it means setting it, for every thread at once.
    fd = os.open(temp, _FLAGS, 0o666 if old is None else 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            if old is not None:
                os.fchmod(fd, old)
            out.write(payload)
        os.replace(temp, target)
    except BaseException:
        with suppress(OSError):
            temp.unlink()
        raise
    return old is not None
