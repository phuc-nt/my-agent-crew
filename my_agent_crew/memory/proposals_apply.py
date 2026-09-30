"""Carrying out a memory proposal once someone has decided on it.

The store records proposals but never touches the filesystem; this module is where an
approval becomes a written fact. Kept apart so the decision and its consequence can be
tested — and reasoned about — separately.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from my_agent_crew.agent.turn_context import WEB
from my_agent_crew.memory import agent_store, user_store
from my_agent_crew.memory.wiki_apply import WIKI_COMPILE, apply_wiki_proposal
from my_agent_crew.store import Store
from my_agent_crew.store.memory_proposals import (
    AGENT_MEMORY,
    AGENT_MEMORY_REWRITE,
    PENDING,
    USER_FACT,
    USER_FORGET,
    MemoryProposal,
)

logger = logging.getLogger(__name__)

# One decision at a time, from the pending check to the resolve. The web decides in a
# worker thread, so an approval on the phone and a rejection on the laptop can arrive
# together; without it both see the proposal pending, and a rejection landing while the
# approval is still writing leaves the fact on disk under a proposal marked rejected.
_deciding = threading.Lock()


class StaleProposal(Exception):
    """A rewrite proposal's `previous_body` no longer matches the file: something else
    wrote to it — a newer consolidation, a person editing by hand — after this proposal
    was made. Applying it would silently discard that other write, so it is refused."""


@contextmanager
def pending(store: Store, proposal_id: str) -> Iterator[MemoryProposal]:
    """Hold the one decision at a time for a proposal still pending, refusing one already
    decided with `KeyError`. Whatever writes a proposal's memory does it inside this."""
    with _deciding:
        proposal = store.proposals.get(proposal_id)
        if proposal.status != PENDING:
            raise KeyError(proposal_id)
        yield proposal


def apply_proposal(
    store: Store,
    proposal_id: str,
    approve: bool,
    user_dir: Path,
    memory_files: dict[str, Path] | None = None,
    memory_dirs: dict[str, Path] | None = None,
) -> MemoryProposal:
    """Decide a proposal, writing the memory first when it is approved.

    The write happens before the proposal is resolved so a failure leaves it pending and
    reviewable rather than marked done with nothing written.

    `memory_dirs` is needed only by a wiki batch, which writes many files under the
    agent's memory folder rather than one named file. It is passed rather than derived
    from `memory_files` so the layout stays stated in one place.

    A proposal already decided is refused before anything is written: an approval from a
    stale tab would otherwise write a fact the person rejected, or append a line twice,
    and only then learn from the store that it was too late. Two decisions arriving
    together are taken one after the other, so the second finds the first's answer.

    A rewrite proposal whose file changed underneath it is superseded rather than left
    pending: retrying the same approval would just fail the same way again, and the
    person's actual choice now is to look at the newer state, not to re-click this stale
    one.
    """
    with pending(store, proposal_id) as proposal:
        if approve:
            try:
                _write(proposal, user_dir, memory_files or {}, memory_dirs or {})
            except StaleProposal:
                store.proposals.supersede(
                    proposal.agent_id,
                    kind=proposal.kind,
                    source=proposal.source,
                    name=proposal.name,
                )
                raise
        return store.proposals.resolve(proposal_id, approve)


def _write(
    proposal: MemoryProposal,
    user_dir: Path,
    memory_files: dict[str, Path],
    memory_dirs: dict[str, Path],
) -> None:
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
    elif proposal.kind == WIKI_COMPILE:
        directory = memory_dirs.get(proposal.agent_id)
        if directory is None:
            raise KeyError(proposal.agent_id)
        apply_wiki_proposal(directory, proposal.body)
    elif proposal.kind in (AGENT_MEMORY, AGENT_MEMORY_REWRITE):
        path = memory_files.get(proposal.agent_id)
        if path is None:
            raise KeyError(proposal.agent_id)
        if proposal.kind == AGENT_MEMORY_REWRITE:
            current = agent_store.read_memory_md(path).strip()
            if current != proposal.previous_body.strip():
                raise StaleProposal(proposal.agent_id)
            agent_store.write_memory_md(path, proposal.body)
        else:
            _append_line(path, proposal.body)
    else:
        raise ValueError(f"unknown proposal kind {proposal.kind!r}")


def _append_line(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    separator = "" if not existing or existing.endswith("\n") else "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{separator}- {body.strip()}\n")
