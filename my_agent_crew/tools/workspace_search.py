"""Searching the workspace by content or by filename. Without these a work agent reads
whole files to find one line, which burns the context it needs for the actual job."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from pathlib import Path
from typing import Any

from my_agent_crew import texts
from my_agent_crew.tools.registry import Tool, ToolError
from my_agent_crew.tools.workspace import resolve_inside

# Directories whose contents are never what a person is looking for, and which are big
# enough that walking them turns a search into a timeout.
SKIP_DIRS = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".mypy_cache"}
)
MAX_RESULTS = 200
MAX_GLOB_RESULTS = 500
GREP_TIMEOUT_SECONDS = 30
# Binary files answer a text search with noise; a NUL byte in the head is the cheap test.
SNIFF_BYTES = 1024


def _pruned_walk(root: Path):
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        yield Path(current), sorted(files)


def _is_text(path: Path) -> bool:
    try:
        return b"\0" not in path.open("rb").read(SNIFF_BYTES)
    except OSError:
        return False


def search_in_tree(root: Path, pattern: str, glob: str | None, max_results: int) -> list[str]:
    """Pure-Python fallback for when ripgrep is not installed."""
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise ToolError(texts.GREP_BAD_PATTERN.format(error=exc)) from exc
    hits: list[str] = []
    for directory, files in _pruned_walk(root):
        for name in files:
            path = directory / name
            if glob and not path.match(glob):
                continue
            if not _is_text(path):
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            relative = path.relative_to(root).as_posix()
            for number, line in enumerate(lines, start=1):
                if regex.search(line):
                    hits.append(f"{relative}:{number}: {line.strip()[:200]}")
                    if len(hits) >= max_results:
                        return hits
    return hits


async def _ripgrep(root: Path, pattern: str, glob: str | None, max_results: int) -> list[str]:
    command = ["rg", "--no-heading", "--line-number", "--color", "never", "-m", str(max_results)]
    for name in sorted(SKIP_DIRS):
        command += ["--glob", f"!{name}/"]
    if glob:
        command += ["--glob", glob]
    command += ["--regexp", pattern, "."]
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), GREP_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        process.kill()
        raise ToolError(texts.GREP_TIMEOUT) from exc
    if process.returncode not in (0, 1):
        raise ToolError(texts.GREP_BAD_PATTERN.format(error=err.decode(errors="replace").strip()))
    lines = out.decode(errors="replace").splitlines()
    return [line[:260] for line in lines[:max_results]]


def build_search_tools(root: Path) -> list[Tool]:
    async def grep(args: dict[str, Any]) -> str:
        base = resolve_inside(root, args.get("path") or ".")
        if not base.is_dir():
            base = base.parent
        pattern = str(args["pattern"])
        glob = str(args["glob"]) if args.get("glob") else None
        limit = min(int(args.get("max_results") or MAX_RESULTS), MAX_RESULTS)
        if shutil.which("rg"):
            hits = await _ripgrep(base, pattern, glob, limit)
        else:
            hits = search_in_tree(base, pattern, glob, limit)
        return "\n".join(hits) if hits else texts.GREP_NO_MATCH

    async def find_files(args: dict[str, Any]) -> str:
        base = resolve_inside(root, args.get("path") or ".")
        if not base.is_dir():
            raise ToolError(texts.WORKSPACE_NOT_FOUND.format(path=args.get("path") or "."))
        pattern = str(args["pattern"])
        found: list[str] = []
        for directory, files in _pruned_walk(base):
            for name in files:
                path = directory / name
                if path.match(pattern):
                    found.append(path.relative_to(base).as_posix())
                    if len(found) >= MAX_GLOB_RESULTS:
                        return "\n".join(sorted(found))
        return "\n".join(sorted(found)) if found else texts.GLOB_NO_MATCH

    return [
        Tool(
            name="workspace_grep",
            description=texts.GREP_DESCRIPTION,
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": texts.GREP_PARAM_PATTERN},
                    "path": {"type": "string"},
                    "glob": {"type": "string", "description": texts.GREP_PARAM_GLOB},
                    "max_results": {"type": "integer"},
                },
                "required": ["pattern"],
            },
            run=grep,
        ),
        Tool(
            name="workspace_glob",
            description=texts.GLOB_DESCRIPTION,
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": texts.GLOB_PARAM_PATTERN},
                    "path": {"type": "string"},
                },
                "required": ["pattern"],
            },
            run=find_files,
        ),
    ]
