"""The soft step cap of a delegated turn.

A child that hits its hard step cap hands back half a thought, and the delegator retells a
fragment. Before that can happen the child gets one last call with no tools and a note
that says so: whatever it has by then becomes its answer. The nudge is stored as a message
in the child's conversation, so the log shows why it stopped, and the cap is read off the
log too: a turn resumed after an approval counts the calls it had already made."""

from __future__ import annotations

from collections.abc import Sequence

from my_agent_crew import texts
from my_agent_crew.llm.types import Message
from my_agent_crew.store import Conversation, Store, StoredMessage

# Model calls a delegated child may make before it is told to conclude. Fewer than the
# hard cap of a work agent, which exists for the person's own long jobs; a task handed
# over inside someone else's turn should wrap up well before the delegator gives up.
WRAP_UP_AT = 25


def wrap_up_due(conv: Conversation, history: Sequence[StoredMessage], max_steps: int) -> bool:
    """True from the call at which a delegated child must conclude: the last one before
    the soft cap, or before the hard cap when that is lower, so its answer is still read
    as an answer and not halted. Never for a turn the person started themselves."""
    if not conv.parent_call_id:
        return False
    limit = min(WRAP_UP_AT, max_steps - 1)
    made = sum(1 for m in history if m.message.role == "assistant")
    return limit >= 1 and made + 1 >= limit


def nudge_to_conclude(
    store: Store, conv: Conversation, history: Sequence[StoredMessage]
) -> list[StoredMessage]:
    """Appends the wrap-up note once and returns the history with it in place."""
    note = texts.DELEGATE_WRAP_UP
    if any(m.message.role == "user" and m.message.content == note for m in history):
        return list(history)
    store.append(conv.id, Message(role="user", content=note))
    return store.history(conv.id)
