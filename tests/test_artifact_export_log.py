"""What `artifact_export` tells the server log when a write fails: where on this machine the
file was going, the error's class and its number. The place is a name found on disk, which
nobody checked, so it is written in a form that stays on the line it began."""

from __future__ import annotations

import errno
import io
import logging
import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.tools.artifact_file_texts import EXPORT_FAILED
from my_agent_crew.tools.registry import ToolResult
from tests.canvas_helpers import PLAN, call, created, put, turn

OLD = "notes/old.md"
FULL = (28, "No space left on device")
LOGGER = "my_agent_crew.tools.artifact_files"
# The server's own format for a line of its log, and a line made to be read as one of them.
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
FORGED = "2026-10-05 00:00:00,000 WARNING forged: export of secrets.md done"


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    put(tmp_path / "ws", OLD, "cũ")
    return tmp_path / "ws"


@pytest.fixture
async def art(store: Store) -> str:
    turn(store)
    return await created(store, PLAN)


@pytest.fixture
def written() -> Iterator[io.StringIO]:
    """What the export logs, as the server's handler would put it in the file."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(FORMAT))
    logger = logging.getLogger(LOGGER)
    logger.addHandler(handler)
    yield stream
    logger.removeHandler(handler)


async def _export(store: Store, root: Path, art: str, path: str) -> ToolResult:
    return await call(store, "artifact_export", {"id": art, "path": path}, root=root)


def _failing(error: BaseException) -> Callable[..., None]:
    def fail(*_: object) -> None:
        raise error

    return fail


def _linked(root: Path, name: str) -> Path:
    """A folder of that name in the workspace, reached by the plain name `clean`: the path the
    agent sends is checked, the name the link leads to is whatever was put on the disk."""
    real = root / name
    real.mkdir()
    (root / "clean").symlink_to(real, target_is_directory=True)
    return real


@pytest.mark.parametrize(
    ("error", "told"),
    [
        (OSError(*FULL), "OSError errno 28"),
        (
            PermissionError(13, "Permission denied", "/Users/someone/ws/notes/old.md"),
            "PermissionError errno 13",
        ),
        (OSError("no number given"), "OSError errno None"),
    ],
)
async def test_a_disk_that_refuses_is_worded_for_the_agent_and_leaves_one_warning_in_the_log(
    store: Store, root: Path, art: str, monkeypatch, caplog, error: OSError, told: str
):
    """The agent hears what became of the file, in its own words for the place. Whoever reads
    the log learns where on this machine the file was going, which error stopped it and its
    number; the system's own sentence goes to neither."""
    monkeypatch.setattr(os, "replace", _failing(error))
    with caplog.at_level(logging.WARNING):
        result = await _export(store, root, art, OLD)
    assert result.output == TOOL_FAILED.format(error=EXPORT_FAILED.format(path=OLD))
    assert str(root.parent) not in result.output
    [record] = caplog.records
    assert record.levelno == logging.WARNING and record.exc_info is None
    assert record.name == LOGGER
    place = str(root.resolve() / OLD)
    assert record.getMessage() == f"artifact_export could not write {place!r}: {told}"


@pytest.mark.skipif(os.geteuid() == 0, reason="root may write in any folder")
@pytest.mark.parametrize("gap", ["\n", "\r", " "])
async def test_a_folder_whose_name_holds_a_line_break_starts_no_line_of_its_own_in_the_log(
    store: Store, root: Path, art: str, caplog, written: io.StringIO, gap: str
):
    """The place logged is the one on this machine with its links followed, so a folder reached
    by a plain name is written there under its own, and its own may go on with a second line
    made to be read as a record of the log."""
    real = _linked(root, f"x{gap}{FORGED}")
    real.chmod(0o555)
    try:
        with caplog.at_level(logging.WARNING):
            result = await _export(store, root, art, "clean/x.md")
    finally:
        real.chmod(0o755)
    assert result.output == TOOL_FAILED.format(error=EXPORT_FAILED.format(path="clean/x.md"))
    [record] = caplog.records
    place = str(root.resolve() / real.name / "x.md")
    told = f"PermissionError errno {errno.EACCES}"
    assert record.getMessage() == f"artifact_export could not write {place!r}: {told}"
    [line] = written.getvalue().splitlines()
    assert line.endswith(f" WARNING {LOGGER}: {record.getMessage()}")


async def test_a_failure_no_disk_reports_names_such_a_folder_on_the_line_it_began_too(
    store: Store, root: Path, art: str, monkeypatch, caplog, written: io.StringIO
):
    """This one is logged with its traceback, so more lines follow: none of them is the one
    the folder's name carries."""
    real = _linked(root, f"x\n{FORGED}")
    monkeypatch.setattr(os, "replace", _failing(ValueError("embedded null byte")))
    with caplog.at_level(logging.ERROR):
        result = await _export(store, root, art, "clean/x.md")
    assert result.output == TOOL_FAILED.format(error=EXPORT_FAILED.format(path="clean/x.md"))
    [record] = caplog.records
    place = str(root.resolve() / real.name / "x.md")
    assert record.getMessage() == f"artifact_export could not write {place!r}"
    lines = written.getvalue().splitlines()
    assert lines[0].endswith(f" ERROR {LOGGER}: {record.getMessage()}")
    assert lines[-1] == "ValueError: embedded null byte"
    assert not any(line.startswith(FORGED) for line in lines)
    assert list(real.iterdir()) == []
