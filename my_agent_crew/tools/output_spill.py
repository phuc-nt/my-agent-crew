"""The true original of a tool output, kept on disk next to the (possibly shaped) copy the
model sees in its context, so `tool_output_read` can hand back the real thing later without
re-running whatever produced it.

Every path is built from a hash of the call id and a conversation id checked against a fixed
shape, never from the id itself: a model-supplied id, however it is spelled, never becomes a
path component. `sweep`, `remove_conversation` and `copy_conversation` also confirm the path
they end up with is still inside `<home>/spill` before touching it, and none follow a
symlink out of that tree."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import tool_call_id, turn_conversation_id
from my_agent_crew.tools.output_shaping import Shaped, shape_output_async

if TYPE_CHECKING:  # registry.py imports this module; this avoids the reverse import cycle
    from my_agent_crew.tools.output_summary import Summariser

logger = logging.getLogger(__name__)

READ_TOOL = "tool_output_read"
SPILL_DIR = "spill"
# A run's own output rarely nears this; the cap exists so one runaway command cannot fill
# the disk with a single file.
MAX_SPILL_BYTES = 5 * 1024 * 1024
_TRUNCATED_NOTE = "\n…[đã cắt ở 5 MB, phần còn lại không được lưu]"
_CONV_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _digest(call_id: str) -> str:
    return hashlib.sha256(call_id.encode("utf-8")).hexdigest()[:32]


def _conv_dir(home: Path, conv_id: str) -> Path | None:
    """`None` for a conversation id that does not match the fixed shape, so no caller can
    build a path with it even indirectly."""
    if not _CONV_ID.match(conv_id):
        return None
    return home / SPILL_DIR / conv_id


def _inside(root: Path, path: Path) -> bool:
    resolved_root = root.resolve()
    return path.resolve() == resolved_root or resolved_root in path.resolve().parents


class Spill:
    def __init__(self, home: Path):
        self._home = home

    def write(self, conv_id: str, call_id: str, text: str) -> bool:
        conv_dir = _conv_dir(self._home, conv_id)
        if conv_dir is None:
            return False
        body = text.encode("utf-8")
        if len(body) > MAX_SPILL_BYTES:
            body = body[:MAX_SPILL_BYTES] + _TRUNCATED_NOTE.encode("utf-8")
        try:
            conv_dir.mkdir(parents=True, exist_ok=True)
            (conv_dir / f"{_digest(call_id)}.txt").write_bytes(body)
        except OSError:
            logger.exception("could not write spill file for conversation %s", conv_id)
            return False
        return True

    def read(self, conv_id: str, call_id: str) -> str | None:
        conv_dir = _conv_dir(self._home, conv_id)
        if conv_dir is None:
            return None
        path = conv_dir / f"{_digest(call_id)}.txt"
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None


def sweep(home: Path, max_age_days: int = 7) -> int:
    """Removes every spill file older than `max_age_days`, never following a symlink to
    somewhere else on disk. Returns how many files were removed."""
    root = home / SPILL_DIR
    if not root.is_dir():
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            if os.stat(path).st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            logger.exception("could not sweep spill file %s", path)
    return removed


def remove_conversation(home: Path, conv_id: str) -> None:
    """Deletes a conversation's whole spill folder, called right after the conversation
    itself is deleted. A conv_id shaped like a traversal attempt resolves outside
    `<home>/spill` and is refused instead of deleting whatever it happened to land on."""
    conv_dir = _conv_dir(home, conv_id)
    root = home / SPILL_DIR
    if conv_dir is None or not conv_dir.exists() or not _inside(root, conv_dir):
        return
    shutil.rmtree(conv_dir, ignore_errors=True)


def copy_conversation(home: Path, src_conv_id: str, dst_conv_id: str) -> None:
    """Copies a conversation's spill files to a fork's own folder, so the fork keeps reading
    the true original even after the source conversation (and its spill files) are deleted.
    `copyfile` rather than a hardlink or rename, so the copy gets its own fresh mtime and the
    two conversations' 7-day clocks run independently. Best effort: a failure is logged and
    the fork still works, reading whatever the DB kept instead."""
    src_dir = _conv_dir(home, src_conv_id)
    dst_dir = _conv_dir(home, dst_conv_id)
    if src_dir is None or dst_dir is None or not src_dir.is_dir():
        return
    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
        for path in src_dir.iterdir():
            if path.is_file() and not path.is_symlink():
                shutil.copyfile(path, dst_dir / path.name)
    except OSError:
        logger.exception("could not copy spill files from %s to %s", src_conv_id, dst_conv_id)


async def shape_with_spill(
    spill: Spill | None,
    name: str,
    text: str,
    limit: int,
    summariser: Summariser | None,
) -> Shaped:
    """`shape_output_async`, plus: when a call's own output is too big to fit in `limit`,
    the true original is written to disk first and a pointer line telling the model how to
    read it back (`tool_output_read`) is appended on top of the ordinary shaping.

    Falls straight through to `shape_output_async` — no file, no pointer line, byte-for-byte
    what this did before spilling existed — whenever there is nowhere safe to spill to (no
    `spill` collaborator, no conversation or call id in context), nothing worth spilling
    (the output already fits), no room left for a pointer line once one is subtracted from
    `limit`, or the call is to `tool_output_read` itself: that tool's own reply must never
    become a pointer to a spill file, or reading one segment back could spawn another spill,
    each with its own pointer, forever."""
    conv_id, call_id = turn_conversation_id(), tool_call_id()
    pointer = texts.TOOL_OUTPUT_POINTER.format(chars=len(text), id=call_id)
    if (
        spill is None
        or name == READ_TOOL
        or not conv_id
        or not call_id
        or len(text) <= limit
        or limit <= 2 * len(pointer)
    ):
        return await shape_output_async(text, limit, summariser)
    if not spill.write(conv_id, call_id, text):
        return await shape_output_async(text, limit, summariser)
    shaped = await shape_output_async(text, limit - len(pointer), summariser)
    return Shaped(shaped.text + pointer, shaped.kind, shaped.original_chars, shaped.cost_usd)
