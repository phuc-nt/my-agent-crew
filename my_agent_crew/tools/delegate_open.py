"""Opening a child conversation for a delegation, split out of `delegate.py` so that
module keeps its own line budget."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import DELEGATE, turn_source
from my_agent_crew.store.models import Conversation

if TYPE_CHECKING:  # the runtime builds the tool, so importing it back would be a cycle
    from my_agent_crew.server.runtime import Runtime

TITLE_TASK_CHARS = 60


def open_child(
    runtime: Runtime,
    parent: Conversation | None,
    target: str,
    task: str,
    args: dict[str, Any],
    call_id: str,
) -> Conversation:
    """The child inherits the parent's approval stance and what is left of its budget, so a
    fan-out cannot spend more than the parent was allowed in total. It also records the
    root of its chain and where the turn that opened the chain came from, once: which
    canvases the child reaches, and whether it may write them, follow from those."""
    cap = runtime.deps_for(target).settings.cost_cap_usd
    if parent is not None and parent.cost_cap_usd:
        remaining = max(parent.cost_cap_usd - parent.spent_usd, 0.0)
        cap = min(cap, remaining) if cap else remaining
    title = texts.DELEGATE_CONVERSATION_TITLE.format(agent=target, task=task[:TITLE_TASK_CHARS])
    child = runtime.store.create(
        title=title,
        autonomous=parent.autonomous if parent is not None else True,
        cost_cap_usd=cap,
        skills=tuple(str(s) for s in args.get("skills") or ()),
        agent_id=target,
        parent_call_id=call_id,
        approval_ttl_seconds=parent.approval_ttl_seconds if parent is not None else None,
        **_root(parent),
    )
    if parent is not None and parent.auto_approve:
        child = runtime.store.update(child.id, auto_approve=list(parent.auto_approve))
    return child


def _root(parent: Conversation | None) -> dict[str, str]:
    """A child of a child keeps the root it was given. A parent that is itself the root
    names the source of the turn delegating now; a parent that is a child opened before
    roots were recorded is taken as the root, with a source no write is allowed from."""
    if parent is None:
        return {}
    if parent.root_id:
        return {"root_id": parent.root_id, "root_source": parent.root_source}
    source = turn_source()
    return {"root_id": parent.id, "root_source": "" if source == DELEGATE else source}
