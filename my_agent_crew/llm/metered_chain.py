"""A route chain whose every call lands in the usage ledger.

The turn loop writes its completions to the message log, and the ledger adds up that log.
Everything else that asks a model — a title, a recap, a summary of a long output, a
picture, a scanned page, consolidation, the wiki — goes through a chain wrapped here, so
each call is written down as a side call with what it was for and whose it was.

It is a `ProviderChain` itself, built on the same providers and routes, so every place
that takes a chain takes this one unchanged and sees every item the chain yields.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING

from my_agent_crew.agent.turn_context import turn_conversation_id
from my_agent_crew.llm.provider import ProviderChain
from my_agent_crew.llm.types import Completion, Message, RouteFailed, StreamItem, ToolSpec
from my_agent_crew.store.side_calls import PURPOSES, SideCall

if TYPE_CHECKING:  # the store is handed in; importing its package here would be a cycle
    from my_agent_crew.store import Store

logger = logging.getLogger(__name__)


class MeteredChain(ProviderChain):
    """`conversation_id`, when given, wins over the turn's own: a title or a recap runs in
    a task started before (or after) the turn it belongs to, where the turn's context
    variable is empty or still names the previous conversation."""

    def __init__(
        self,
        chain: ProviderChain,
        store: Store,
        agent_id: str,
        purpose: str,
        conversation_id: str | None = None,
    ):
        if purpose not in PURPOSES:
            raise ValueError(f"unknown side call purpose: {purpose!r}")
        super().__init__(chain.providers, chain.routes)
        self._store = store
        self._agent_id = agent_id
        self._purpose = purpose
        self._conversation_id = conversation_id

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> AsyncIterator[StreamItem]:
        # A call dropped after its first chunk (a timeout, a failure mid-answer) was still
        # served and may still be billed, so it is written down as one of unknown cost.
        # A route that failed before its first chunk served nothing and is not.
        failed, started, answered = 0, False, False
        try:
            async for item in super().stream(messages, tools):
                if isinstance(item, RouteFailed):
                    failed += 1
                elif isinstance(item, Completion):
                    answered = True
                    self._record(item.provider, item.model, item)
                else:
                    started = True
                yield item
        finally:
            if started and not answered and failed < len(self.routes):
                route = self.routes[failed]
                self._record(route.provider, route.model, None)

    def _record(self, provider: str, model: str, completion: Completion | None) -> None:
        usage = completion.usage if completion is not None else None
        call = SideCall(
            agent_id=self._agent_id,
            purpose=self._purpose,
            provider=provider,
            model=model,
            cost_usd=usage.cost_usd if usage else None,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            cached_tokens=usage.cached_tokens if usage else None,
            conversation_id=self._conversation_id or turn_conversation_id() or None,
        )
        try:
            self._store.side_calls.record(call)
        except Exception:  # the ledger must never cost the caller its answer
            logger.exception("could not record a %s side call", self._purpose)
