from pathlib import Path

import pytest

from my_agent_crew import texts
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


def test_absolute_and_home_paths_inside_the_workspace_are_accepted(tmp_path: Path, monkeypatch):
    assert (
        resolve_inside(tmp_path, str(tmp_path / "notes" / "a.txt"))
        == (tmp_path / "notes" / "a.txt").resolve()
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    assert resolve_inside(tmp_path, "~/notes") == (tmp_path / "notes").resolve()
    with pytest.raises(ToolError):
        resolve_inside(tmp_path, str(tmp_path.parent / "outside.txt"))


def test_symlinks_placed_inside_the_workspace_are_followed(tmp_path: Path):
    """Real workspaces link chart folders in from elsewhere; the link is the user's choice."""
    outside = tmp_path.parent / "charts-outside"
    outside.mkdir(exist_ok=True)
    (outside / "sleep.png").write_bytes(b"png")
    (tmp_path / "charts").symlink_to(outside)
    path = resolve_inside(tmp_path, "charts/sleep.png")
    assert path == tmp_path / "charts" / "sleep.png" and path.read_bytes() == b"png"
    with pytest.raises(ToolError):
        resolve_inside(tmp_path, "charts/../../x")


async def test_list_read_write_round_trip(reg: ToolRegistry, tmp_path: Path):
    listing = await reg.execute("workspace_list", {"path": "."})
    assert "notes/" in listing.output
    read = await reg.execute("workspace_read", {"path": "notes/a.txt"})
    assert read.output == "hello"
    write = await reg.execute("workspace_write", {"path": "new/b.txt", "content": "xin chào"})
    assert write.ok and (tmp_path / "new" / "b.txt").read_text() == "xin chào"


async def test_reading_a_window_of_lines(reg: ToolRegistry, tmp_path: Path):
    """Long files would swamp the context; the model asks for the slice it needs."""
    (tmp_path / "long.txt").write_text("\n".join(f"line {i}" for i in range(1, 101)))
    whole = await reg.execute("workspace_read", {"path": "long.txt"})
    assert whole.output.startswith("line 1\n") and whole.output.endswith("line 100")
    window = await reg.execute("workspace_read", {"path": "long.txt", "offset": 10, "limit": 3})
    assert window.output == "line 10\nline 11\nline 12"
    tail = await reg.execute("workspace_read", {"path": "long.txt", "offset": 99})
    assert tail.output == "line 99\nline 100"
    head = await reg.execute("workspace_read", {"path": "long.txt", "limit": 2})
    assert head.output == "line 1\nline 2"


async def test_a_long_file_is_cut_only_by_the_agents_output_cap_and_says_so(tmp_path: Path):
    """The tool has no cap of its own: a 24k brief reaches an agent whose cap allows it,
    and an agent with a smaller cap sees the marker instead of a file that just stops."""
    (tmp_path / "brief.md").write_text("x" * 24000)
    wide = ToolRegistry(build_workspace_tools(tmp_path), 32000)
    assert len((await wide.execute("workspace_read", {"path": "brief.md"})).output) == 24000
    narrow = ToolRegistry(build_workspace_tools(tmp_path), 20000)
    cut = (await narrow.execute("workspace_read", {"path": "brief.md"})).output
    assert cut.startswith("x" * 20000) and texts.OUTPUT_TRUNCATED.format(dropped=4000) in cut


async def test_missing_file_is_a_readable_error(reg: ToolRegistry):
    result = await reg.execute("workspace_read", {"path": "nope.txt"})
    assert result.ok is False and "nope.txt" in result.output


async def test_reading_a_directory_is_an_error(reg: ToolRegistry):
    result = await reg.execute("workspace_read", {"path": "notes"})
    assert result.ok is False


def test_only_write_requires_approval(tmp_path: Path):
    flags = {t.name: t.requires_approval for t in build_workspace_tools(tmp_path)}
    assert flags == {"workspace_list": False, "workspace_read": False, "workspace_write": True}
