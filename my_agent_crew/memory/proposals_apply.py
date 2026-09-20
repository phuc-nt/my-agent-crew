"""Carrying out a memory proposal once someone has decided on it.

The store records proposals but never touches the filesystem; this module is where an
approval becomes a written fact. Kept apart so the decision and its consequence can be
tested — and reasoned about — separately.
"""

from __future__ import annotations

import logging
from pathlib import Path

from my_agent_crew.agent.turn_context import WEB
from my_agent_crew.memory import user_store
from my_agent_crew.store import Store
from my_agent_crew.store.memory_proposals import (
    AGENT_MEMORY,
    USER_FACT,
    USER_FORGET,
    MemoryProposal,
)

logger = logging.getLogger(__name__)


def apply_proposal(
    store: Store,
    proposal_id: str,
    approve: bool,
    user_dir: Path,
    memory_files: dict[str, Path] | None = None,
) -> MemoryProposal:
    """Decide a proposal, writing the memory first when it is approved.

    The write happens before the proposal is resolved so a failure leaves it pending and
    reviewable rather than marked done with nothing written.
    """
    proposal = store.proposals.get(proposal_id)
    if approve:
        _write(proposal, user_dir, memory_files or {})
    return store.proposals.resolve(proposal_id, approve)


def _write(proposal: MemoryProposal, user_dir: Path, memory_files: dict[str, Path]) -> None:
    if proposal.kind == USER_FACT:
        user_store.write_fact(
            user_dir,
            name=proposal.name,
            description=proposal.description,
            type=proposal.type,
            body=proposal.body,
            written_by=proposal.agent_id,
            source=WEB,
        )
    elif proposal.kind == USER_FORGET:
        user_store.delete_fact(user_dir, proposal.name)
    elif proposal.kind == AGENT_MEMORY:
        path = memory_files.get(proposal.agent_id)
        if path is None:
            raise KeyError(proposal.agent_id)
        _append_line(path, proposal.body)
    else:
        raise ValueError(f"unknown proposal kind {proposal.kind!r}")


def _append_line(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    separator = "" if not existing or existing.endswith("\n") else "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{separator}- {body.strip()}\n")
