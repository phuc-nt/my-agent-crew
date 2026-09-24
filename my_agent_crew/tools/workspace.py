"""Files under the agent's workspace directory. Escaping the root is refused in code,
not by the prompt; writing asks the user first. A read returns the whole file (or the
requested window): the registry's per-agent output cap is the one place text is cut, and it
says so, whereas a silent cap here left the model believing a 24k brief ended at 20k."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from my_agent_crew.texts import (
    WORKSPACE_ESCAPE,
    WORKSPACE_IS_DIR,
    WORKSPACE_NOT_FOUND,
    WORKSPACE_WRITE_OUTSIDE,
)
from my_agent_crew.tools.registry import Tool, ToolError


def _within(root: Path, path: Path) -> bool:
    return path == root or root in path.parents


def resolve_inside(root: Path, relative: str) -> Path:
    """Absolute paths and `~` are fine as long as they land inside the workspace; personas
    written for other runtimes quote absolute paths, and refusing them only wastes a step.
    Containment is checked on the lexical path, so `..` cannot walk out of the root while
    symlinks the user placed inside the workspace (a chart folder linked from another tool's
    workspace) are followed like any other entry."""
    root = root.resolve()
    candidate = Path(relative).expanduser()
    lexical = Path(os.path.normpath(root / candidate))
    if _within(root, lexical):
        return lexical
    resolved = lexical.resolve()
    if _within(root, resolved):
        return resolved
    raise ToolError(WORKSPACE_ESCAPE)


def resolve_writable(root: Path, relative: str, write_paths: Sequence[str] = ()) -> Path:
    """A path the file tools may write. With `write_paths` set, only under one of them:
    an autonomous agent never stops for approval, so a path guessed by whoever wrote its
    task would otherwise become a new folder of personal data in a git repo. Compared on
    the lexical path, like containment, so `data/../x` is `x` and refused."""
    path = resolve_inside(root, relative)
    if not write_paths:
        return path
    base = root.resolve()
    if any(_within(Path(os.path.normpath(base / p)), path) for p in write_paths):
        return path
    raise ToolError(WORKSPACE_WRITE_OUTSIDE.format(paths=", ".join(write_paths), path=relative))


def build_workspace_tools(root: Path, write_paths: Sequence[str] = ()) -> list[Tool]:
    async def list_dir(args: dict[str, Any]) -> str:
        path = resolve_inside(root, args.get("path") or ".")
        if not path.exists():
            raise ToolError(WORKSPACE_NOT_FOUND.format(path=args.get("path") or "."))
        if path.is_file():
            return path.relative_to(root.resolve()).as_posix()
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        lines = [
            f"{p.name}/" if p.is_dir() else f"{p.name} ({p.stat().st_size} B)" for p in entries
        ]
        return "\n".join(lines) or "(thư mục trống)"

    async def read_file(args: dict[str, Any]) -> str:
        path = resolve_inside(root, args["path"])
        if not path.exists():
            raise ToolError(WORKSPACE_NOT_FOUND.format(path=args["path"]))
        if path.is_dir():
            raise ToolError(WORKSPACE_IS_DIR.format(path=args["path"]))
        text = path.read_text(encoding="utf-8", errors="replace")
        offset, limit = args.get("offset"), args.get("limit")
        if offset is None and limit is None:
            return text
        # 1-based like an editor's gutter, so a line number from a grep hit can be used
        # here without arithmetic.
        start = max(int(offset or 1), 1) - 1
        lines = text.splitlines()[start:]
        if limit is not None:
            lines = lines[: max(int(limit), 0)]
        return "\n".join(lines)

    async def write_file(args: dict[str, Any]) -> str:
        path = resolve_writable(root, args["path"], write_paths)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = str(args.get("content", ""))
        path.write_text(content, encoding="utf-8")
        return f"Đã ghi {len(content)} ký tự vào {args['path']}"

    return [
        Tool(
            name="workspace_list",
            description="Liệt kê tệp và thư mục trong thư mục làm việc.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Đường dẫn tương đối"}},
            },
            run=list_dir,
        ),
        Tool(
            name="workspace_read",
            description="Đọc nội dung một tệp văn bản trong thư mục làm việc.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer", "description": "Dòng bắt đầu, tính từ 1."},
                    "limit": {"type": "integer", "description": "Số dòng tối đa đọc về."},
                },
                "required": ["path"],
            },
            run=read_file,
        ),
        Tool(
            name="workspace_write",
            description="Ghi (tạo hoặc ghi đè) một tệp văn bản trong thư mục làm việc.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
            run=write_file,
            requires_approval=True,
        ),
    ]
