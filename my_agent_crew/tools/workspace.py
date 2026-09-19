"""Files under the agent's workspace directory. Escaping the root is refused in code,
not by the prompt; writing asks the user first."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from my_agent_crew.texts import WORKSPACE_ESCAPE, WORKSPACE_IS_DIR, WORKSPACE_NOT_FOUND
from my_agent_crew.tools.registry import Tool, ToolError

MAX_READ_CHARS = 20000


def resolve_inside(root: Path, relative: str) -> Path:
    root = root.resolve()
    candidate = Path(relative)
    if candidate.is_absolute():
        raise ToolError(WORKSPACE_ESCAPE)
    resolved = (root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise ToolError(WORKSPACE_ESCAPE)
    return resolved


def build_workspace_tools(root: Path) -> list[Tool]:
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
        return path.read_text(encoding="utf-8", errors="replace")[:MAX_READ_CHARS]

    async def write_file(args: dict[str, Any]) -> str:
        path = resolve_inside(root, args["path"])
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
                "properties": {"path": {"type": "string"}},
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
