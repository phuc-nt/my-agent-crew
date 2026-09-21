"""Hooks from a kit's `settings.json`, in the shape Claude Code writes them:

    {"hooks": {"PreToolUse": [{"matcher": "Bash|Write", "hooks": [{"type": "command",
    "command": "node .claude/hooks/guard.cjs"}]}]}}

A hook is a command run before (`PreToolUse`) or after (`PostToolUse`) a tool whose name
matches. The matcher is written against the harness's tool names, so each of ours is also
matched under the name the harness would give it (`shell_run` is `Bash`). Running them is
`tools/hooks.py`; this module only reads the files."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from my_agent_crew.agents.kit import Kit

logger = logging.getLogger(__name__)

PRE, POST = "PreToolUse", "PostToolUse"
EVENTS = (PRE, POST)
DEFAULT_TIMEOUT_SECONDS = 30.0
# What the other harnesses call our tools; a matcher written for them matches these too.
TOOL_ALIASES = {
    "shell_run": "Bash",
    "workspace_read": "Read",
    "workspace_write": "Write",
    "workspace_edit": "Edit",
    "workspace_glob": "Glob",
    "workspace_grep": "Grep",
    "workspace_list": "LS",
    "fetch_url": "WebFetch",
    "web_search": "WebSearch",
    "delegate": "Task",
}


@dataclass(frozen=True)
class Hook:
    event: str
    matcher: str  # a regex over tool names; empty or "*" matches every tool
    command: str
    cwd: Path
    timeout: float = DEFAULT_TIMEOUT_SECONDS

    def matches(self, tool_name: str) -> bool:
        if self.matcher in ("", "*"):
            return True
        names = (tool_name, TOOL_ALIASES.get(tool_name, ""))
        try:
            return any(name and re.fullmatch(self.matcher, name) for name in names)
        except re.error:
            return self.matcher in names


def parse_hooks(data: dict, cwd: Path) -> list[Hook]:
    """Every command hook under `hooks.<event>`; entries of another shape are skipped,
    not refused, since a harness may add kinds we do not run."""
    found: list[Hook] = []
    for event in EVENTS:
        for group in (data.get("hooks") or {}).get(event) or []:
            if not isinstance(group, dict):
                continue
            matcher = str(group.get("matcher") or "")
            for entry in group.get("hooks") or []:
                if not isinstance(entry, dict) or entry.get("type", "command") != "command":
                    continue
                command = str(entry.get("command") or "").strip()
                if not command:
                    continue
                timeout = float(entry.get("timeout") or DEFAULT_TIMEOUT_SECONDS)
                found.append(Hook(event, matcher, command, cwd, timeout))
    return found


def load_hooks(kits: Sequence[Kit]) -> tuple[Hook, ...]:
    hooks: list[Hook] = []
    for kit in kits:
        path = kit.settings_file
        if path is None:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("kit %s: settings.json unreadable: %s", kit.root, exc)
            continue
        if isinstance(data, dict):
            hooks.extend(parse_hooks(data, kit.project))
    return tuple(hooks)
