"""OpenRouter provider. The wire format and stream handling are the shared
OpenAI-compatible ones; what is specific here is the host, the bearer key and asking for
the price to come back in the usage block."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from my_agent_crew.llm.openai_compat import (
    stream_chat,
    to_wire,
    tools_to_wire,
)
from my_agent_crew.llm.types import Message, StreamItem, ToolSpec

BASE_URL = "https://openrouter.ai/api/v1"

# `to_wire` and `tools_to_wire` were defined here before the OpenAI-compatible parts were
# shared, and tests still import them from this module, so they stay re-exported.
__all__ = ["BASE_URL", "OpenRouterProvider", "to_wire", "tools_to_wire"]


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(120.0))

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec], model: str
    ) -> AsyncIterator[StreamItem]:
        body: dict[str, Any] = {
            "model": model,
            "messages": to_wire(messages),
            "stream": True,
            # OpenRouter reports what the call cost; without this every run shows an
            # unknown price and the cost cap has nothing to count.
            "usage": {"include": True},
        }
        if tools:
            body["tools"] = tools_to_wire(tools)
        async for item in stream_chat(
            self._client,
            f"{BASE_URL}/chat/completions",
            body,
            {"Authorization": f"Bearer {self._api_key}"},
            self.name,
            model,
        ):
            yield item
