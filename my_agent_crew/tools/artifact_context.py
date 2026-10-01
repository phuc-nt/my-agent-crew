"""What every canvas tool works from: the agent it acts for, the conversation the turn belongs
to, and the arguments as the model sent them, checked before anything is touched."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import tzinfo
from typing import TYPE_CHECKING, Any

from my_agent_crew.agent.turn_context import turn_conversation_id
from my_agent_crew.texts import OUTPUT_TRUNCATED
from my_agent_crew.texts_canvas import ARTIFACT_ARG_TEXT, ARTIFACT_NO_CONVERSATION
from my_agent_crew.tools.artifact_scope import in_scope, not_found
from my_agent_crew.tools.registry import ToolError

if TYPE_CHECKING:
    from my_agent_crew.store import Store
    from my_agent_crew.store.artifact_models import ArtifactSummary
    from my_agent_crew.store.models import Conversation

# The registry cuts an output that a hook's note pushed past the cap, and marks the cut. A
# page or a diff sized to fit leaves room for the widest such mark, so the cut never reaches
# it and only the note is shortened.
CUT_MARK_ROOM = len(OUTPUT_TRUNCATED.format(dropped=10**9))


@dataclass(frozen=True)
class CanvasAgent:
    """The agent the canvas tools act for. `limit` is its registry's output cap, which a page
    and a diff are sized to fit with room to spare; `zone` is the owner's, for the times a
    list shows."""

    store: Store
    agent_id: str
    is_master: bool
    limit: int
    zone: tzinfo | None = None

    @property
    def author(self) -> str:
        return f"agent:{self.agent_id}"

    def conversation(self) -> Conversation:
        try:
            return self.store.get(turn_conversation_id())
        except KeyError:
            raise ToolError(ARTIFACT_NO_CONVERSATION) from None

    def reach(self, conv: Conversation, artifact_id: str) -> None:
        """Refuses a canvas out of reach in the very words used for one that does not exist."""
        reached = in_scope(
            self.store,
            artifact_id,
            agent_id=self.agent_id,
            is_master=self.is_master,
            conversation_id=conv.id,
            root_id=conv.root_id,
        )
        if not reached:
            raise not_found(artifact_id)

    def seen(self, conv: Conversation, artifact_id: str) -> int:
        """The newest version this conversation has read whole or written, 0 for none."""
        link = self.store.artifact_links.get(conv.id, artifact_id)
        return link.seen_version if link is not None else 0

    def share(self, conv: Conversation, artifact_id: str) -> None:
        """A canvas created or written here is shared with this conversation and with the
        root of its chain, so the chain's later children reach it too. A root deleted since
        is skipped by the store."""
        self.store.artifact_links.link(conv.id, artifact_id, shared=True)
        if conv.root_id:
            self.store.artifact_links.link(conv.root_id, artifact_id, shared=True)


def kind_label(summary: ArtifactSummary) -> str:
    """The kind as a list row and a page header show it: "code python" for code."""
    return f"{summary.kind} {summary.language}" if summary.language else summary.kind


def line_count(text: str | None) -> int:
    """Lines as a page counts them, so the length a write reports is the one a read shows."""
    return (text or "").count("\n") + 1


def text_arg(args: dict[str, Any], name: str) -> str:
    """A string argument as sent. Anything else is refused before anything is touched: the
    text of a number or a list is never what the model meant to write."""
    value = args.get(name)
    if not isinstance(value, str):
        raise ToolError(ARTIFACT_ARG_TEXT.format(name=name))
    return value


def optional_text(args: dict[str, Any], name: str) -> str | None:
    """None for an argument left out, else what `text_arg` makes of it."""
    return None if args.get(name) is None else text_arg(args, name)


def int_arg(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def flag_arg(value: Any) -> bool:
    """True for true, also when a model sends it as the string "true"."""
    return str(value).lower() == "true"
