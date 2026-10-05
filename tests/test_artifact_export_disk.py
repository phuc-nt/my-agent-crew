"""What `artifact_export` answers when the disk refuses before the file is opened: a name
longer than the file system takes, a folder the process may not enter, a link that leads back
to itself. Each is an export that failed, worded like any other, with its one line in the log;
and none is asked of the disk before the path is judged for where it leads."""

from __future__ import annotations

import errno
import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED, WORKSPACE_ESCAPE, WORKSPACE_WRITE_OUTSIDE
from my_agent_crew.tools.artifact_file_texts import EXPORT_FAILED
from my_agent_crew.tools.registry import ToolResult
from tests.canvas_helpers import PLAN, call, created, put, turn

OLD = "notes/old.md"
LONG = "a" * 300 + ".md"


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    put(tmp_path / "ws", OLD, "cũ")
    (tmp_path / "outside").mkdir()
    return tmp_path / "ws"


@pytest.fixture
async def art(store: Store) -> str:
    turn(store)
    return await created(store, PLAN)


async def _export(
    store: Store, root: Path, art: str, path: str, write_paths: tuple[str, ...] = ()
) -> ToolResult:
    args = {"id": art, "path": path}
    return await call(store, "artifact_export", args, root=root, write_paths=write_paths)


def _failed(message: str) -> str:
    return TOOL_FAILED.format(error=message)


def _tree(root: Path) -> list[str]:
    """Every entry of the workspace and of the folder beside it, and what each file holds."""
    base = root.parent
    found = [*root.rglob("*"), *(base / "outside").rglob("*")]
    return sorted(
        f"{entry.relative_to(base).as_posix()}={entry.read_bytes()!r}"
        if entry.is_file() and not entry.is_symlink()
        else entry.relative_to(base).as_posix()
        for entry in found
    )


def _warned(caplog: pytest.LogCaptureFixture, place: Path, told: str) -> None:
    """The one line a refused export leaves: where on this machine the file was going, the
    error's class and its number. No traceback, and nothing the registry logs for a crash."""
    [record] = caplog.records
    assert record.levelno == logging.WARNING and record.exc_info is None
    assert record.name == "my_agent_crew.tools.artifact_files"
    assert record.getMessage() == f"artifact_export could not write {str(place)!r}: {told}"


@pytest.mark.parametrize("path", [LONG, "notes/" + LONG, "fresh/" + LONG, "b" * 300 + "/x.md"])
async def test_a_name_longer_than_the_disk_takes_is_an_export_that_failed(
    store: Store, root: Path, art: str, caplog: pytest.LogCaptureFixture, path: str
):
    """The same sentence wherever the name stands: in a folder that is there, in one the write
    would have made, or as the folder itself."""
    before = _tree(root)
    with caplog.at_level(logging.WARNING):
        result = await _export(store, root, art, path)
    assert result.output == _failed(EXPORT_FAILED.format(path=path))
    assert str(root.parent) not in result.output
    assert _tree(root) == before
    _warned(caplog, root.resolve() / path, f"OSError errno {errno.ENAMETOOLONG}")


@pytest.mark.skipif(os.geteuid() == 0, reason="root may enter any folder")
@pytest.mark.parametrize("path", ["locked/old.md", "locked/new.md", "locked/sub/new.md"])
async def test_a_folder_the_process_may_not_enter_is_an_export_that_failed(
    store: Store, root: Path, art: str, caplog: pytest.LogCaptureFixture, path: str
):
    """Whether the file would replace one in it or be new there, the folder is as it was."""
    locked = put(root, "locked/old.md", "cũ").parent
    before = _tree(root)
    locked.chmod(0)
    try:
        with caplog.at_level(logging.WARNING):
            result = await _export(store, root, art, path)
    finally:
        locked.chmod(0o755)
    assert result.output == _failed(EXPORT_FAILED.format(path=path))
    assert _tree(root) == before
    _warned(caplog, root.resolve() / path, f"PermissionError errno {errno.EACCES}")


@pytest.mark.parametrize("held", [(), ("loop",)])
async def test_a_folder_that_is_a_link_back_to_itself_is_an_export_that_failed(
    store: Store, root: Path, art: str, caplog: pytest.LogCaptureFixture, held: tuple[str, ...]
):
    """Followed, such a link leads nowhere, so it leads out of neither the workspace nor the
    write paths: the write is what finds it cannot be passed."""
    (root / "loop").symlink_to(root / "loop")
    before = _tree(root)
    with caplog.at_level(logging.WARNING):
        result = await _export(store, root, art, "loop/x.md", held)
    assert result.output == _failed(EXPORT_FAILED.format(path="loop/x.md"))
    assert _tree(root) == before and (root / "loop").is_symlink()
    _warned(caplog, root.resolve() / "loop" / "x.md", f"OSError errno {errno.ELOOP}")


async def test_a_write_path_that_is_a_link_back_to_itself_holds_no_folder(
    store: Store, root: Path, art: str
):
    """So a file that would land outside the other write paths is kept out as it always was."""
    (root / "out").mkdir()
    (root / "out" / "notes").symlink_to(root / "notes", target_is_directory=True)
    (root / "loop").symlink_to(root / "loop")
    before = _tree(root)
    result = await _export(store, root, art, "out/notes/x.md", ("out", "loop"))
    refusal = WORKSPACE_WRITE_OUTSIDE.format(paths="out, loop", path="out/notes/x.md")
    assert result.output == _failed(refusal)
    assert _tree(root) == before


async def test_where_a_path_leads_is_judged_before_the_disk_is_asked_about_its_name(
    store: Store, root: Path, art: str, caplog: pytest.LogCaptureFixture
):
    """A name the disk would refuse is refused first, and in other words, when it lies outside
    the workspace or the write paths: nothing was going to be written, so nothing is logged."""
    (root / "linked").symlink_to(root.parent / "outside", target_is_directory=True)
    before = _tree(root)
    with caplog.at_level(logging.WARNING):
        for path in ("../outside/" + LONG, "linked/" + LONG):
            result = await _export(store, root, art, path)
            assert result.output == _failed(WORKSPACE_ESCAPE), path
        kept_out = await _export(store, root, art, "notes/" + LONG, ("out",))
    refusal = WORKSPACE_WRITE_OUTSIDE.format(paths="out", path="notes/" + LONG)
    assert kept_out.output == _failed(refusal)
    assert _tree(root) == before and caplog.records == []
