"""Parsed files, kept until the file changes.

A file's identity here is its path with its size and modification time: the cost of a
`stat` per turn instead of a read and a parse. An edit on disk still takes effect on the
very next call, which is the promise the prompt builders make, and a file that vanished
is forgotten the next time the cache is asked about a different one at that path."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

_entries: dict[Path, tuple[int, int, object]] = {}


def cached[T](path: Path, parse: Callable[[Path], T]) -> T:
    """`parse(path)`, or its result from the last call if the file has not changed."""
    stat = path.stat()
    stamp = (stat.st_mtime_ns, stat.st_size)
    hit = _entries.get(path)
    if hit is not None and hit[:2] == stamp:
        return hit[2]  # type: ignore[return-value]
    value = parse(path)
    _entries[path] = (*stamp, value)
    return value


def forget(path: Path) -> None:
    _entries.pop(path, None)


def clear() -> None:
    _entries.clear()
