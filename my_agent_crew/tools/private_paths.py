"""Folders no file tool goes into, by whatever path one is reached.

A browser keeps an agent's logins in a folder under the crew home. Some file tools may read
the home (what a person attached is kept there), a workspace may hold a link that leads
anywhere, and the words of a page can ask an agent to read a file and carry what it holds to
an address. So the server names the folder here once, when it starts, and every path a file
tool is about to use is judged by where it really leads.

A folder is known by what it is on disk, not by how its name is spelt: on a file system that
folds case `Browser` is `browser`. One that is not made yet has only its name, and is known by
the nearest folder above it that is there and the names from that one down. The check is made
when a path is resolved; a file linked hard out of such a folder is not seen by it, which is
the shell sandbox's to refuse (`shell_sandbox.py`)."""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path

_kept: set[Path] = set()


def keep_private(folder: Path) -> None:
    """Close `folder` to the file tools for as long as the process lives."""
    _kept.add(Path(os.path.realpath(folder)))


def _identity(path: Path) -> tuple[int, int] | None:
    try:
        found = os.stat(path)
    except OSError:
        return None
    return found.st_dev, found.st_ino


def _folded(name: str) -> str:
    return unicodedata.normalize("NFD", name).casefold()


def _anchor(folder: Path) -> tuple[tuple[int, int] | None, tuple[str, ...]]:
    """The nearest part of `folder` that is on disk, and the names below it that are not."""
    names: list[str] = []
    while (found := _identity(folder)) is None and folder != folder.parent:
        names.insert(0, _folded(folder.name))
        folder = folder.parent
    return found, tuple(names)


def is_private(path: Path) -> bool:
    """Whether `path` is one of the folders kept private, or leads into one."""
    if not _kept:
        return False
    real = Path(os.path.realpath(path))
    # The path and every folder above it, each with the names that lead from it to the path.
    steps = [(_identity(step), real.parts[len(step.parts) :]) for step in (real, *real.parents)]
    for folder in _kept:
        anchor, names = _anchor(folder)
        for found, below in steps:
            if found == anchor and tuple(_folded(n) for n in below[: len(names)]) == names:
                return True
    return False


def kept_under(base: Path) -> list[str]:
    """The folders kept private that lie under `base`, each as the path from it: what a
    program that walks `base` by itself has to be told to leave out."""
    root = _identity(Path(os.path.realpath(base)))
    found: list[str] = []
    for folder in sorted(_kept):
        for parent in folder.parents:
            if root is not None and _identity(parent) == root:
                found.append(folder.relative_to(parent).as_posix())
                break
    return found
