"""Finding or opening the approval a single paused call waits on, split out of
`tool_calls.py` so that module keeps its own line budget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from my_agent_crew.agents.approval_ttl import effective_ttl
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store import Approval
from my_agent_crew.store.models import AWAITING_APPROVAL, QUESTION, TOOL, Conversation
from my_agent_crew.texts_approval import REPEATED_REFUSAL
from my_agent_crew.tools.ask_user import ASK_USER_TOOL_NAME, options_of

if TYPE_CHECKING:  # the loop owns the deps; importing it back would be a cycle
    from my_agent_crew.agent.loop import AgentDeps


def matches(approval: Approval, call: ToolCall) -> bool:
    """Whether a stored approval is actually a decision about this call, not just one that
    happens to share its id — ids could collide before `llm/openai_compat.py`'s uuid fix."""
    return approval.tool_name == call.name and approval.arguments == call.arguments


def refused_again(
    deps: AgentDeps, conv_id: str, call: ToolCall, asked_from: int | None
) -> str | None:
    """What to answer a call a person already refused in this turn, or None for a call that
    is theirs to decide. The same tool with the same arguments, denied or left to expire
    by a message past `asked_from` (where the turn began, or the person's last steer), is
    refused here: nobody is asked twice, no request is opened and no channel hears of it.
    Other arguments are another call, and the next turn asks again, since its message may
    be the person changing their mind. This only ever refuses; nothing runs because of it."""
    if asked_from is None:  # a caller that knows of no turn has nothing to compare with
        return None
    for earlier in deps.store.approvals.refused_after(conv_id, call.name, asked_from):
        if matches(earlier, call):
            return REPEATED_REFUSAL
    return None


def open_new(deps: AgentDeps, conv: Conversation, last_message_id: int, call: ToolCall) -> Approval:
    """Opens a fresh approval for a call with none yet, and marks the conversation as
    waiting. Callers must have already confirmed `find_for_call` returned nothing: opening
    one for a call that already has a row would fail on the store's UNIQUE constraint."""
    asking = call.name == ASK_USER_TOOL_NAME
    approval = deps.store.approvals.create(
        conv.id,
        last_message_id,
        call,
        ttl_seconds=effective_ttl(conv, deps.settings),
        kind=QUESTION if asking else TOOL,
        options=options_of(call.arguments) if asking else [],
    )
    deps.store.update(conv.id, status=AWAITING_APPROVAL)
    return approval
