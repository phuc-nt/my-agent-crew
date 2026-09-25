"""Provider protocol and the route chain that falls back across providers and models."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from my_agent_crew.config import Route
from my_agent_crew.llm.types import Message, RouteFailed, StreamItem, ToolSpec

logger = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    """The upstream could not serve the request; the chain may try the next route."""


class Provider(Protocol):
    name: str

    def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        model: str,
        reasoning: str = "",
    ) -> AsyncIterator[StreamItem]: ...


class AllRoutesFailed(ProviderError):
    def __init__(self, errors: list[tuple[Route, ProviderError]]):
        self.errors = errors
        detail = "; ".join(f"{r.provider}:{r.model}: {e}" for r, e in errors)
        super().__init__(f"every route failed — {detail}")


class ProviderChain:
    """Tries routes in order. Falls back only before the first item has been streamed:
    a half-delivered answer cannot be restarted on another model without the reader
    seeing the seam, so a mid-stream failure surfaces instead. Each fallback is yielded
    as a `RouteFailed` item and logged, so a route that keeps failing is never silent."""

    def __init__(self, providers: dict[str, Provider], routes: Sequence[Route]):
        missing = [r for r in routes if r.provider not in providers]
        if missing:
            raise ValueError(f"no provider registered for {missing}")
        self._providers = providers
        self._routes = tuple(routes)

    @property
    def routes(self) -> tuple[Route, ...]:
        return self._routes

    @property
    def providers(self) -> dict[str, Provider]:
        return dict(self._providers)

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> AsyncIterator[StreamItem]:
        errors: list[tuple[Route, ProviderError]] = []
        for route in self._routes:
            provider = self._providers[route.provider]
            started = False
            # Only a route that states an effort passes one, so a provider written before
            # the setting existed keeps working.
            extra = {"reasoning": route.reasoning} if route.reasoning else {}
            try:
                async for item in provider.stream(messages, tools, route.model, **extra):
                    started = True
                    yield item
                return
            except ProviderError as exc:
                if started:
                    raise
                errors.append((route, exc))
                logger.warning(
                    "route %s:%s failed, trying next: %s", route.provider, route.model, exc
                )
                yield RouteFailed(provider=route.provider, model=route.model, error=str(exc))
        raise AllRoutesFailed(errors)
