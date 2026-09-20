"""Editing a file in place by replacing an exact snippet. A work agent that can only
overwrite whole files either re-reads and re-writes everything or quietly loses the parts
it did not remember; replacing a unique snippet keeps the rest of the file untouched."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from my_agent_crew import texts
from my_agent_crew.tools.registry import Tool, ToolError
from my_agent_crew.tools.workspace import resolve_inside

# How much of the changed region comes back so the model can see what it did without the
# result filling the context.
DIFF_CONTEXT_LINES = 3
MAX_DIFF_LINES = 40


def apply_edit(text: str, old: str, new: str, replace_all: bool = False) -> tuple[str, int]:
    """The replaced text and how many times it changed. Refuses an ambiguous match so an
    edit never silently lands on the wrong occurrence."""
    if not old:
        raise ToolError(texts.EDIT_EMPTY_OLD)
    count = text.count(old)
    if count == 0:
        raise ToolError(texts.EDIT_NO_MATCH)
    if count > 1 and not replace_all:
        raise ToolError(texts.EDIT_AMBIGUOUS.format(count=count))
    return (text.replace(old, new), count) if replace_all else (text.replace(old, new, 1), 1)


def changed_region(before: str, after: str) -> str:
    """The lines around the first difference, both sides, so the answer shows the edit
    rather than the whole file."""
    old_lines, new_lines = before.splitlines(), after.splitlines()
    shared = min(len(old_lines), len(new_lines))
    start = 0
    while start < shared and old_lines[start] == new_lines[start]:
        start += 1
    end_old, end_new = len(old_lines), len(new_lines)
    while end_old > start and end_new > start and old_lines[end_old - 1] == new_lines[end_new - 1]:
        end_old -= 1
        end_new -= 1
    head = max(0, start - DIFF_CONTEXT_LINES)
    lines = [f"  {line}" for line in new_lines[head:start]]
    lines += [f"- {line}" for line in old_lines[start:end_old]]
    lines += [f"+ {line}" for line in new_lines[start:end_new]]
    lines += [f"  {line}" for line in new_lines[end_new : end_new + DIFF_CONTEXT_LINES]]
    if len(lines) > MAX_DIFF_LINES:
        dropped = len(lines) - MAX_DIFF_LINES
        lines = lines[:MAX_DIFF_LINES] + [texts.EDIT_DIFF_TRUNCATED.format(dropped=dropped)]
    return "\n".join(lines)


def build_edit_tool(root: Path) -> Tool:
    async def edit_file(args: dict[str, Any]) -> str:
        path = resolve_inside(root, args["path"])
        if not path.is_file():
            raise ToolError(texts.WORKSPACE_NOT_FOUND.format(path=args["path"]))
        before = path.read_text(encoding="utf-8")
        after, count = apply_edit(
            before,
            str(args["old"]),
            str(args.get("new", "")),
            bool(args.get("replace_all", False)),
        )
        path.write_text(after, encoding="utf-8")
        header = texts.EDIT_DONE.format(path=args["path"], count=count)
        return f"{header}\n{changed_region(before, after)}"

    return Tool(
        name="workspace_edit",
        description=texts.EDIT_DESCRIPTION,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old": {"type": "string", "description": texts.EDIT_PARAM_OLD},
                "new": {"type": "string", "description": texts.EDIT_PARAM_NEW},
                "replace_all": {"type": "boolean"},
            },
            "required": ["path", "old", "new"],
        },
        run=edit_file,
        requires_approval=True,
    )
