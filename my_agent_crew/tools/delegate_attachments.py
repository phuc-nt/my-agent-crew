"""Charts and files a delegated agent attached, carried over to the agent that asked.

A reply attaches a file with a `MEDIA:` or `FILE:` line, and the path on it is looked up
inside the replying agent's own workspace: that is how Telegram and the web find the file,
and it is what keeps one agent from attaching another agent's files. A child's lines name
paths in the child's workspace, so passed on unchanged they would point at nothing in the
parent's. The files are copied into the parent's workspace and the lines rewritten to the
copies.

The parent then retells the answer in its own words, and a retelling drops attachment
lines readily: a health coach drew two charts, the master summarised, and the person saw
neither. So the loop puts back, at the end of the final reply, any relayed line the reply
left out. The charts were made for the person; whether they arrive should not depend on
the model remembering to copy a path.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Sequence
from pathlib import Path

from my_agent_crew import texts
from my_agent_crew.agents.roster import DELEGATE_TOOL_NAME
from my_agent_crew.reply_attachments import FILE_PREFIX, MAX_DOCUMENT_BYTES, MEDIA_PREFIX
from my_agent_crew.store import StoredMessage
from my_agent_crew.tools.registry import ToolError
from my_agent_crew.tools.workspace import resolve_inside

logger = logging.getLogger(__name__)

# Under the parent's workspace, one folder per child conversation, so two children that
# both drew `sleep.png` do not overwrite each other.
RELAY_DIR = "delegated"
PREFIXES = (MEDIA_PREFIX, FILE_PREFIX)


def attachment(line: str) -> tuple[str, str] | None:
    """`(prefix, path)` when the line attaches a file, else None. A bare prefix is prose."""
    stripped = line.strip()
    for prefix in PREFIXES:
        if stripped.startswith(prefix) and stripped[len(prefix) :].strip():
            return prefix, stripped[len(prefix) :].strip()
    return None


def relay_attachments(answer: str, child_root: Path, parent_root: Path, child_id: str) -> str:
    """The child's answer with each attachment copied into the parent's workspace and its
    line pointing at the copy. A file that cannot be carried over becomes a sentence saying
    so, not a line that would fail again at delivery with no word about why."""
    if child_root.resolve() == parent_root.resolve():
        return answer
    used: set[str] = set()
    lines = []
    for line in answer.split("\n"):
        found = attachment(line)
        if found is None:
            lines.append(line)
            continue
        prefix, path = found
        copied = _copy(path, child_root, parent_root / RELAY_DIR / child_id, used)
        if copied is None:
            lines.append(texts.DELEGATE_ATTACHMENT_LOST.format(path=path))
        else:
            lines.append(f"{prefix} {copied.relative_to(parent_root).as_posix()}")
    return "\n".join(lines)


def _copy(path: str, child_root: Path, target_dir: Path, used: set[str]) -> Path | None:
    try:
        source = resolve_inside(child_root, path)
        if not source.is_file() or source.stat().st_size > MAX_DOCUMENT_BYTES:
            return None
        name = source.name
        if name in used:
            name = f"{len(used)}-{name}"
        used.add(name)
        target_dir.mkdir(parents=True, exist_ok=True)
        return Path(shutil.copyfile(source, target_dir / name))
    except (ToolError, OSError) as exc:
        logger.warning("delegate attachment %s: %s", path, exc)
        return None


def dropped_attachments(history: Sequence[StoredMessage], reply: str) -> list[str]:
    """The attachment lines this turn's delegated answers carried that `reply` does not,
    in the order they came back. Only this turn: an older chart was already delivered."""
    kept = {found[1] for line in reply.split("\n") if (found := attachment(line))}
    start = max((i for i, m in enumerate(history) if m.message.role == "user"), default=-1)
    missing: list[str] = []
    for stored in history[start + 1 :]:
        message = stored.message
        if message.role != "tool" or message.name != DELEGATE_TOOL_NAME:
            continue
        for line in message.content.split("\n"):
            found = attachment(line)
            if found is not None and found[1] not in kept:
                kept.add(found[1])
                missing.append(f"{found[0]} {found[1]}")
    return missing
