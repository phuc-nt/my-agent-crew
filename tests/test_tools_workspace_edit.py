from pathlib import Path

import pytest

from my_agent_crew.tools.registry import ToolError
from my_agent_crew.tools.workspace_edit import apply_edit, build_edit_tool, changed_region


def test_apply_edit_replaces_one_occurrence_and_refuses_an_ambiguous_one():
    text = "alpha\nbeta\nalpha\n"
    assert apply_edit(text, "beta", "gamma") == ("alpha\ngamma\nalpha\n", 1)
    assert apply_edit(text, "alpha", "x", replace_all=True) == ("x\nbeta\nx\n", 2)
    with pytest.raises(ToolError, match="2 chỗ"):
        apply_edit(text, "alpha", "x")
    with pytest.raises(ToolError, match="Không tìm thấy"):
        apply_edit(text, "delta", "x")
    with pytest.raises(ToolError, match="không được rỗng"):
        apply_edit(text, "", "x")


def test_changed_region_shows_both_sides_of_the_change_with_context():
    before = "\n".join(f"line {i}" for i in range(1, 11))
    after = before.replace("line 5", "line five")
    region = changed_region(before, after)
    assert "- line 5" in region and "+ line five" in region
    assert "  line 4" in region and "  line 6" in region
    assert "line 1" not in region


def test_changed_region_truncates_a_large_rewrite():
    before = "\n".join(f"a{i}" for i in range(80))
    after = "\n".join(f"b{i}" for i in range(80))
    assert "còn" in changed_region(before, after)


async def test_edit_tool_writes_the_file_and_reports_the_change(tmp_path: Path):
    target = tmp_path / "notes.txt"
    target.write_text("one\ntwo\nthree\n", encoding="utf-8")
    tool = build_edit_tool(tmp_path)
    assert tool.requires_approval
    out = await tool.run({"path": "notes.txt", "old": "two", "new": "2"})
    assert target.read_text(encoding="utf-8") == "one\n2\nthree\n"
    assert "notes.txt" in out and "- two" in out and "+ 2" in out


async def test_edit_tool_refuses_a_missing_file_and_a_path_outside_the_workspace(tmp_path: Path):
    tool = build_edit_tool(tmp_path)
    with pytest.raises(ToolError, match="Không có tệp"):
        await tool.run({"path": "nope.txt", "old": "a", "new": "b"})
    with pytest.raises(ToolError, match="ngoài thư mục làm việc"):
        await tool.run({"path": "../escape.txt", "old": "a", "new": "b"})


async def test_edit_tool_deletes_a_snippet_when_new_is_empty(tmp_path: Path):
    target = tmp_path / "f.py"
    target.write_text("keep\nremove me\nkeep\n", encoding="utf-8")
    await build_edit_tool(tmp_path).run({"path": "f.py", "old": "remove me\n", "new": ""})
    assert target.read_text(encoding="utf-8") == "keep\nkeep\n"
