"""Where `artifact_export` will write. The place a file would really land, with every link on
the way followed, must be inside the workspace and inside the agent's write paths; a link is
never written through; and a write that fails leaves the old file whole and no other behind."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.store.db import Store
from my_agent_crew.texts import (
    TOOL_FAILED,
    WORKSPACE_ESCAPE,
    WORKSPACE_IS_DIR,
    WORKSPACE_WRITE_OUTSIDE,
)
from my_agent_crew.tools.artifact_file_texts import (
    EXPORT_FAILED,
    EXPORT_TARGET_IS_LINK,
    IMPORT_BAD_PATH,
)
from my_agent_crew.tools.artifact_source_ref import PATH_MAX
from my_agent_crew.tools.registry import ToolResult
from tests.canvas_helpers import PLAN, call, created, put, turn

OLD = "notes/old.md"


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    put(tmp_path / "ws", OLD, "cũ")
    (tmp_path / "ws" / "out").mkdir()
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


async def test_a_path_that_is_no_place_for_a_file_is_refused_and_nothing_is_written(
    store: Store, root: Path, art: str
):
    refusals = {
        "../outside/x.md": WORKSPACE_ESCAPE,
        str(root.parent / "outside" / "x.md"): WORKSPACE_ESCAPE,
        "~no-such-user-0/x.md": WORKSPACE_ESCAPE,
        "notes": WORKSPACE_IS_DIR.format(path="notes"),
        "notes/x\u202e.md": IMPORT_BAD_PATH.format(limit=PATH_MAX),
        "out/a\ud83d.md": IMPORT_BAD_PATH.format(limit=PATH_MAX),
        "": IMPORT_BAD_PATH.format(limit=PATH_MAX),
    }
    before = _tree(root)
    for path, refusal in refusals.items():
        assert (await _export(store, root, art, path)).output == _failed(refusal), path
    assert _tree(root) == before


async def test_an_agent_held_to_its_write_paths_exports_only_under_them(
    store: Store, root: Path, art: str
):
    """An agent that never stops for approval writes nowhere else, by this tool either."""
    held = ("out", "data")
    before = _tree(root)
    refused = await _export(store, root, art, "notes/x.md", held)
    refusal = WORKSPACE_WRITE_OUTSIDE.format(paths="out, data", path="notes/x.md")
    assert refused.output == _failed(refusal)
    assert _tree(root) == before
    for path in ("out/x.md", "data/tuan/x.md"):
        assert (await _export(store, root, art, path, held)).ok, path
        assert (root / path).read_text(encoding="utf-8") == PLAN


async def test_a_folder_linked_out_of_the_workspace_takes_no_export(
    store: Store, root: Path, art: str
):
    """The path reads as inside the workspace, and the file would land outside it."""
    (root / "linked").symlink_to(root.parent / "outside", target_is_directory=True)
    before = _tree(root)
    for path in ("linked/x.md", "linked/sub/x.md"):
        assert (await _export(store, root, art, path)).output == _failed(WORKSPACE_ESCAPE), path
    assert _tree(root) == before


async def test_a_folder_linked_out_of_the_write_paths_takes_no_export(
    store: Store, root: Path, art: str
):
    (root / "out" / "notes").symlink_to(root / "notes", target_is_directory=True)
    before = _tree(root)
    result = await _export(store, root, art, "out/notes/x.md", ("out",))
    refusal = WORKSPACE_WRITE_OUTSIDE.format(paths="out", path="out/notes/x.md")
    assert result.output == _failed(refusal)
    assert _tree(root) == before
    assert (await _export(store, root, art, "out/notes/x.md")).ok


async def test_a_link_is_never_written_through(store: Store, root: Path, art: str):
    """Neither onto the file it points at, nor into the place it only names."""
    (root / "notes" / "link.md").symlink_to(root / OLD)
    (root / "notes" / "dangling.md").symlink_to(root.parent / "outside" / "new.md")
    before = _tree(root)
    for path in ("notes/link.md", "notes/dangling.md"):
        result = await _export(store, root, art, path)
        assert result.output == _failed(EXPORT_TARGET_IS_LINK.format(path=path)), path
    assert _tree(root) == before
    assert (root / "notes" / "link.md").is_symlink()


async def test_a_write_that_fails_leaves_the_old_file_whole_and_no_other_behind(
    store: Store, root: Path, art: str, monkeypatch
):
    def full(*_: object) -> None:
        raise OSError(28, "No space left on device", str(root / OLD))

    monkeypatch.setattr(os, "replace", full)
    before = _tree(root)
    for path in (OLD, "notes/new.md"):
        result = await _export(store, root, art, path)
        assert result.output == _failed(EXPORT_FAILED.format(path=path)), path
        assert str(root.parent) not in result.output
    assert _tree(root) == before


@pytest.mark.skipif(os.geteuid() == 0, reason="root may write any file")
async def test_a_file_marked_read_only_is_not_replaced(store: Store, root: Path, art: str):
    """Moving a new file into its place needs no leave from the old one, so the tool looks."""
    (root / OLD).chmod(0o444)
    before = _tree(root)
    result = await _export(store, root, art, OLD)
    assert result.output == _failed(EXPORT_FAILED.format(path=OLD))
    assert _tree(root) == before


async def test_a_new_file_gets_the_mode_of_any_written_file_and_an_old_one_keeps_its_own(
    store: Store, root: Path, art: str
):
    plain = put(root, "plain.md", "x")
    script = put(root, "notes/run.sh", "#!/bin/sh\n")
    script.chmod(0o750)
    for path in ("new.md", "notes/run.sh"):
        assert (await _export(store, root, art, path)).ok, path
    modes = [stat.S_IMODE((root / name).stat().st_mode) for name in ("new.md", "plain.md")]
    assert modes[0] == modes[1], [oct(mode) for mode in modes]
    assert stat.S_IMODE(script.stat().st_mode) == 0o750
    assert script.read_text(encoding="utf-8") == PLAN
    assert plain.read_text(encoding="utf-8") == "x"
