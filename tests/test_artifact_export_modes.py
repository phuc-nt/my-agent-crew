"""Who may read a file `artifact_export` is still writing. The file is written beside its
place and moved in, and from the moment it is made it is open to no reader the finished file
will be closed to: one who opened it early would go on reading as the payload went in."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.store.db import Store
from tests.canvas_helpers import PLAN, call, created, put, turn

OLDS = {"notes/secret.md": 0o600, "notes/run.sh": 0o750, "notes/shared.md": 0o664}


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.fixture(params=[0o022, 0o077])
def umask(request: pytest.FixtureRequest) -> Iterator[int]:
    """One umask that leaves a new file open to every reader, and one that closes it."""
    old = os.umask(request.param)
    yield request.param
    os.umask(old)


@pytest.fixture
def seen(monkeypatch) -> list[int]:
    """The mode of each file opened for writing: as it was made, then as each payload on its
    way in found it."""
    modes: list[int] = []
    make, opened = os.open, os.fdopen

    def making(*args: Any, **kwargs: Any) -> int:
        fd = make(*args, **kwargs)
        modes.append(_mode(fd))
        return fd

    def watching(fd: int, *args: Any, **kwargs: Any) -> Any:
        def noting(data: bytes) -> int:
            modes.append(_mode(fd))
            return out.raw.write(data)

        out = opened(fd, *args, **kwargs)
        out.write = noting
        return out

    monkeypatch.setattr(os, "open", making)
    monkeypatch.setattr(os, "fdopen", watching)
    return modes


def _mode(file: Path | int) -> int:
    return stat.S_IMODE(os.stat(file).st_mode)


async def test_the_file_being_written_is_open_to_no_reader_the_finished_one_is_closed_to(
    store: Store, tmp_path: Path, umask: int, seen: list[int]
):
    """A file that replaces another is made closed and takes the other's mode before a byte
    goes in; a new one is made as any file is, so the umask has shaped it from the start."""
    turn(store)
    art = await created(store, PLAN)
    plain = put(tmp_path, "plain.md", "x")
    for path, mode in OLDS.items():
        put(tmp_path, path, "cũ").chmod(mode)
    for path in ("new.md", *OLDS):
        del seen[:]
        result = await call(store, "artifact_export", {"id": art, "path": path}, root=tmp_path)
        assert result.ok, result.output
        final = _mode(tmp_path / path)
        assert final == OLDS.get(path, _mode(plain)), (path, oct(final))
        assert (tmp_path / path).read_text(encoding="utf-8") == PLAN
        first, *written = seen
        assert first & ~final == 0 and written == [final], (path, [oct(mode) for mode in seen])
