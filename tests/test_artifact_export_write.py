"""What `artifact_export` leaves on disk. A write that fails, whatever stopped it, leaves the
old file whole, no half-written file beside it and none of the folders it made on the way."""

from __future__ import annotations

import logging
import os
import secrets
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.tools.artifact_file_texts import EXPORT_FAILED
from my_agent_crew.tools.artifact_file_write import write_whole
from my_agent_crew.tools.registry import ToolResult
from tests.canvas_helpers import PLAN, call, created, put, turn

OLD = "notes/old.md"
FULL = (28, "No space left on device")


class Stopped(BaseException):
    """What ends a thread from outside: no `Exception`, so no tool words it."""


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    put(tmp_path / "ws", OLD, "cũ")
    (tmp_path / "ws" / "out").mkdir()
    return tmp_path / "ws"


@pytest.fixture
async def art(store: Store) -> str:
    turn(store)
    return await created(store, PLAN)


async def _export(store: Store, root: Path, art: str, path: str) -> ToolResult:
    return await call(store, "artifact_export", {"id": art, "path": path}, root=root)


def _tree(root: Path) -> list[str]:
    """Every folder and file of the workspace, and what each file holds."""
    return sorted(
        f"{entry.relative_to(root).as_posix()}={entry.read_bytes()!r}"
        if entry.is_file()
        else entry.relative_to(root).as_posix()
        for entry in root.rglob("*")
    )


def _failing(error: BaseException) -> Callable[..., None]:
    def fail(*_: object) -> None:
        raise error

    return fail


async def test_a_failure_no_disk_reports_is_worded_like_any_other_and_leaves_nothing_behind(
    store: Store, root: Path, art: str, monkeypatch, caplog
):
    """The registry would name only the error's type; the agent is told what became of the
    file, and the cause is kept for whoever reads the log, with where on this machine the
    file was going: the agent's own words for the place would not say whose workspace."""
    monkeypatch.setattr(os, "replace", _failing(ValueError("embedded null byte")))
    before, paths = _tree(root), (OLD, "notes/new.md", "fresh/deep/new.md")
    with caplog.at_level(logging.ERROR):
        for path in paths:
            result = await _export(store, root, art, path)
            assert result.output == TOOL_FAILED.format(error=EXPORT_FAILED.format(path=path)), path
            assert str(root.parent) not in result.output
    assert _tree(root) == before
    assert caplog.text.count("ValueError: embedded null byte") == 3
    places = [record.getMessage().rpartition(" ")[2] for record in caplog.records]
    assert places == [str(root.resolve() / path) for path in paths]


async def test_a_full_disk_is_worded_without_a_line_in_the_log(
    store: Store, root: Path, art: str, monkeypatch, caplog
):
    monkeypatch.setattr(os, "replace", _failing(OSError(*FULL)))
    with caplog.at_level(logging.ERROR):
        result = await _export(store, root, art, OLD)
    assert result.output == TOOL_FAILED.format(error=EXPORT_FAILED.format(path=OLD))
    assert caplog.records == []


@pytest.mark.parametrize("error", [OSError(*FULL), MemoryError(), Stopped()])
def test_a_write_cut_short_takes_its_half_written_file_away(
    root: Path, monkeypatch, error: BaseException
):
    opened = os.fdopen

    def cutting(fd: int, *args: Any, **kwargs: Any) -> Any:
        def cut(data: bytes) -> None:
            os.write(fd, data[:3])
            raise error

        out = opened(fd, *args, **kwargs)
        out.write = cut
        return out

    monkeypatch.setattr(os, "fdopen", cutting)
    before = _tree(root)
    for path in (OLD, "notes/new.md", "fresh/deep/new.md"):
        with pytest.raises(type(error)):
            write_whole(root / path, PLAN.encode())
        assert _tree(root) == before, path


async def test_the_folders_made_for_a_file_that_was_not_written_are_taken_away_again(
    store: Store, root: Path, art: str, monkeypatch
):
    """Only the ones this write made: `out` was there before it, so `out` stays."""
    monkeypatch.setattr(os, "replace", _failing(OSError(*FULL)))
    before = _tree(root)
    for path in ("fresh/new.md", "fresh/deep/er/new.md", "out/sub/new.md"):
        assert not (await _export(store, root, art, path)).ok, path
        assert _tree(root) == before, path


@pytest.mark.parametrize("error", [OSError(*FULL), Stopped()])
def test_a_folder_that_holds_something_by_then_is_left_with_what_it_holds(
    root: Path, monkeypatch, error: BaseException
):
    """And its refusal to go is not what the caller hears: the error is the one that stopped
    the write."""

    def stopping(*_: object) -> None:
        put(root, "fresh/other.md", "của việc khác")
        raise error

    monkeypatch.setattr(os, "replace", stopping)
    before = _tree(root)
    with pytest.raises(type(error)) as caught:
        write_whole(root / "fresh/deep/new.md", PLAN.encode())
    assert caught.value is error
    left = [entry for entry in _tree(root) if entry not in before]
    assert left == ["fresh", f"fresh/other.md={'của việc khác'.encode()!r}"]


def test_a_name_someone_put_a_link_at_first_is_never_written_through(
    root: Path, tmp_path: Path, monkeypatch
):
    """The file is made new or not at all, and what was there is not this write's to remove."""
    outside = put(tmp_path, "outside.md", "của người khác")
    monkeypatch.setattr(secrets, "token_hex", lambda _: "ab" * 8)
    planted = root / "notes" / f".export-{'ab' * 8}.tmp"
    planted.symlink_to(outside)
    before = _tree(root)
    with pytest.raises(FileExistsError):
        write_whole(root / OLD, PLAN.encode())
    assert _tree(root) == before and planted.is_symlink()
    assert outside.read_text(encoding="utf-8") == "của người khác"


async def test_a_folder_another_write_made_first_is_used_and_is_not_this_ones_to_take_away(
    store: Store, root: Path, art: str, monkeypatch
):
    make = Path.mkdir

    def late(self: Path, *args: Any, **kwargs: Any) -> None:
        os.mkdir(self)  # the other write gets there between the look and the making
        make(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", late)
    assert (await _export(store, root, art, "fresh/new.md")).ok
    assert (root / "fresh" / "new.md").read_text(encoding="utf-8") == PLAN
    monkeypatch.setattr(os, "replace", _failing(OSError(*FULL)))
    assert not (await _export(store, root, art, "other/new.md")).ok
    assert (root / "other").is_dir() and list((root / "other").iterdir()) == []
