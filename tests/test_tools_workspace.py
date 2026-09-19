from pathlib import Path

import pytest

from my_agent_crew.tools.registry import ToolError, ToolRegistry
from my_agent_crew.tools.workspace import build_workspace_tools, resolve_inside


@pytest.fixture
def reg(tmp_path: Path) -> ToolRegistry:
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "a.txt").write_text("hello")
    return ToolRegistry(build_workspace_tools(tmp_path))


@pytest.mark.parametrize("bad", ["../x", "/etc/passwd", "notes/../../x"])
def test_escape_attempts_are_refused(tmp_path: Path, bad: str):
    with pytest.raises(ToolError):
        resolve_inside(tmp_path, bad)


def test_symlink_pointing_outside_is_refused(tmp_path: Path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret")
    (tmp_path / "link").symlink_to(outside)
    with pytest.raises(ToolError):
        resolve_inside(tmp_path, "link")


async def test_list_read_write_round_trip(reg: ToolRegistry, tmp_path: Path):
    listing = await reg.execute("workspace_list", {"path": "."})
    assert "notes/" in listing.output
    read = await reg.execute("workspace_read", {"path": "notes/a.txt"})
    assert read.output == "hello"
    write = await reg.execute("workspace_write", {"path": "new/b.txt", "content": "xin chào"})
    assert write.ok and (tmp_path / "new" / "b.txt").read_text() == "xin chào"


async def test_missing_file_is_a_readable_error(reg: ToolRegistry):
    result = await reg.execute("workspace_read", {"path": "nope.txt"})
    assert result.ok is False and "nope.txt" in result.output


async def test_reading_a_directory_is_an_error(reg: ToolRegistry):
    result = await reg.execute("workspace_read", {"path": "notes"})
    assert result.ok is False


def test_only_write_requires_approval(tmp_path: Path):
    flags = {t.name: t.requires_approval for t in build_workspace_tools(tmp_path)}
    assert flags == {"workspace_list": False, "workspace_read": False, "workspace_write": True}
