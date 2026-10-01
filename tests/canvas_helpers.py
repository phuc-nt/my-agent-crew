"""Shared steps for the canvas tests: whether the store's lock is free, a turn in a
conversation, a canvas tool called through the registry the way the loop calls it, a hook
whose note the registry must cut, and the canvases a person and an agent leave behind."""

from __future__ import annotations

import re
import threading
from typing import Any
from zoneinfo import ZoneInfo

from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.artifacts.tag import TAG_RE
from my_agent_crew.config import DEFAULT_TOOL_OUTPUT_CHARS
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store
from my_agent_crew.store.models import Conversation
from my_agent_crew.texts import OUTPUT_TRUNCATED
from my_agent_crew.tools.artifact import build_artifact_tools
from my_agent_crew.tools.registry import ToolRegistry, ToolResult

ZONE = ZoneInfo("Asia/Saigon")
NOTE_CUT = re.compile("h*" + re.escape(OUTPUT_TRUNCATED).replace(re.escape("{dropped}"), r"\d+"))


def lock_is_free(store: Store) -> bool:
    """Whether another thread could take the store's lock right now."""
    taken: list[bool] = []

    def take() -> None:
        got = store._lock.acquire(timeout=1)
        taken.append(got)
        if got:
            store._lock.release()

    thread = threading.Thread(target=take)
    thread.start()
    thread.join()
    return taken[0]


def turn(
    store: Store, conv: Conversation | None = None, source: str = CHAT, depth: int = 0
) -> Conversation:
    """Starts a turn of `conv` from `source`, in a new conversation when none is given."""
    conv = conv or store.create()
    set_turn_source(source)
    set_turn_conversation(conv.id, depth)
    return conv


def child_turn(store: Store, root: Conversation, root_source: str = CHAT) -> Conversation:
    """Starts the turn of a child delegated to from `root`, whose chain began in `root_source`."""
    child = store.create(root_id=root.id, root_source=root_source)
    return turn(store, child, source=f"delegate:{root.id}", depth=1)


async def call(
    store: Store,
    name: str,
    args: dict[str, Any],
    *,
    agent_id: str = "coach",
    is_master: bool = False,
    limit: int = DEFAULT_TOOL_OUTPUT_CHARS,
    hooks: Any = None,
) -> ToolResult:
    tools = build_artifact_tools(store, agent_id, is_master, limit, ZONE)
    return await ToolRegistry(tools, limit, hooks).execute(name, args)


class LongNote:
    """A kit hook that adds a long note after every result, so the registry has to cut."""

    async def before(self, name: str, args: dict[str, Any]) -> None:
        return None

    async def after(self, name: str, args: dict[str, Any], ok: bool, output: str) -> str:
        return "\n" + "h" * 2000


def before_note(output: str) -> str:
    """What a tool returned in front of `LongNote`'s note, checking that the registry's cut
    fell inside the note and left the tool's own text whole."""
    text, note = output.split("\nh", 1)
    assert NOTE_CUT.fullmatch(note), note[-60:]
    return text


def tagged(result: ToolResult) -> tuple[str, int, bool]:
    """The canvas id, version and unchanged mark a successful write opens with."""
    assert result.ok, result.output
    match = TAG_RE.match(result.output)
    assert match is not None, result.output
    return match[1], int(match[2]), match[3] is not None


def persons_canvas(store: Store, content: str, *links: str, kind: str = "markdown") -> str:
    """A canvas a person made on the web, linked to each conversation in `links`."""
    art = store.artifacts.create("Ghi chú của người", kind, "", USER, "", content).id
    for conversation_id in links:
        store.artifact_links.link(conversation_id, art)
    return art


def agents_canvas(store: Store, agent_id: str, content: str = "# Kế hoạch\n") -> str:
    """A canvas `agent_id` made in some earlier conversation, linked to none."""
    return store.artifacts.create(
        "Kế hoạch", "markdown", agent_id, f"agent:{agent_id}", "", content
    ).id


def seen(store: Store, conv: Conversation, art: str) -> int:
    link = store.artifact_links.get(conv.id, art)
    return link.seen_version if link is not None else 0


def lines_text(count: int, width: int = 40) -> str:
    """`count` distinct lines of `width` characters each."""
    return "\n".join(f"dòng {n:05d} ".ljust(width, "x") for n in range(1, count + 1))
