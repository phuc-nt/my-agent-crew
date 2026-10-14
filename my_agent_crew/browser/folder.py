"""A folder beneath a workspace, reached and written through descriptors.

`saved.place` judges a folder where it really is, and a tool may wait a long while between
that and its write: for a file to come, for a page to be printed. So nothing here goes by the
path a second time. The folder is walked to from the workspace a part at a time, each part
opened under the one above it and never through a link: a link put there meanwhile, at the
folder or at any part above it, is refused as a folder outside the workspace is, and nothing
is made or written past it. What is then done in the folder (a file made new, a half-written
one taken away, what it holds looked over) is done under that one descriptor."""

from __future__ import annotations

import contextlib
import errno
import itertools
import os
import shutil
import stat
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from my_agent_crew.browser.quarantine import mark
from my_agent_crew.texts import WORKSPACE_ESCAPE
from my_agent_crew.tools.registry import ToolError

DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
NEW = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW


def _step(parent: int, part: str, make: bool) -> int:
    """The folder `part` directly under the open folder `parent`, made first when `make` and
    it is not there. A link is no folder of the workspace's, wherever it leads; anything
    else in a folder's place is told as a folder that could not be made is."""
    if make:
        with contextlib.suppress(FileExistsError):
            os.mkdir(part, dir_fd=parent)
    try:
        return os.open(part, DIR, dir_fd=parent)
    except OSError:
        found = os.stat(part, dir_fd=parent, follow_symlinks=False)
        if stat.S_ISLNK(found.st_mode):
            raise ToolError(WORKSPACE_ESCAPE) from None
        if not stat.S_ISDIR(found.st_mode):
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), part) from None
        raise


@contextlib.contextmanager
def reached(base: Path, shown: str, make: bool = True) -> Iterator[int]:
    """The folder `shown` names beneath the workspace `base`, open: by the way it was judged,
    one real folder under another from the workspace down. Closed when this is left."""
    path = PurePosixPath(shown)
    if path.is_absolute() or ".." in path.parts:
        raise ToolError(WORKSPACE_ESCAPE)  # a walk that would not stay under where it began
    fd = os.open(os.path.realpath(base), os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts:
            above, fd = fd, _step(fd, part, make)
            os.close(above)
        yield fd
    finally:
        os.close(fd)


def write(folder: int, name: str, content: bytes | Path) -> tuple[str, int]:
    """Put `content` (the bytes, or the file that holds them) in the open folder under `name`,
    or under that name with a number when it is taken; the name it has there, and its size.
    Made new or not at all: never over a file, nor through a link, already there; and a file
    that could not be written whole is taken away again."""
    stem, dot, ending = name.rpartition(".")
    if not dot:
        stem, ending = name, ""
    for n in itertools.count(1):
        called = f"{stem}{f'-{n}' if n > 1 else ''}{dot}{ending}"
        try:
            # Ours to take away again only once this did not raise.
            fd = os.open(called, NEW, 0o644, dir_fd=folder)
        except FileExistsError:
            continue
        try:
            with open(fd, "wb") as file:
                mark(fd)  # before a byte of it: what a site sent is never there without it
                if isinstance(content, bytes):
                    file.write(content)
                else:
                    with open(content, "rb") as source:
                        shutil.copyfileobj(source, file)
                size = file.tell()
        except BaseException:
            with contextlib.suppress(OSError):  # the failure that is told is the first one
                remove(folder, called)
            raise
        return called, size
    raise AssertionError("unreachable")


def keep(base: Path, shown: str, name: str, content: bytes | Path) -> tuple[str, int]:
    """`write`, in the folder `shown` names beneath `base`, which is made when it is not
    there. The file is in that folder under the name this says, and nowhere else."""
    with reached(base, shown) as folder:
        return write(folder, name, content)


def listed(folder: int) -> list[tuple[str, os.stat_result]]:
    """What is directly in the open folder: each name and what it is, a link as itself."""
    found = []
    with os.scandir(folder) as entries:
        for entry in entries:
            with contextlib.suppress(OSError):  # gone since it was listed
                found.append((entry.name, entry.stat(follow_symlinks=False)))
    return found


def remove(folder: int, name: str) -> None:
    """Take `name` out of the open folder; one that is gone already is no trouble."""
    with contextlib.suppress(FileNotFoundError):
        os.unlink(name, dir_fd=folder)


def held_bytes(base: Path, shown: str) -> int:
    """How much the folder `shown` names holds: the sizes of the files directly in it. Not
    what a folder in it holds, nor what a link there names; and a folder that is not there,
    or is no folder, holds nothing (the write says what is wrong with it)."""
    try:
        with reached(base, shown, make=False) as folder:
            return sum(x.st_size for _name, x in listed(folder) if stat.S_ISREG(x.st_mode))
    except OSError:
        return 0
