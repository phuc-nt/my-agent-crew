"""Ollama provider: an OpenAI-compatible server running on the machine itself.

Worth having for two reasons. It costs nothing, which matters for the summarising of long
tool output that would otherwise add a paid call to every large result. And it keeps
working with no network, so a scheduled job does not fail because a remote host is down.

A local model reports no price. `cost_usd` stays None rather than 0.0, because zero and
unknown are different claims and the run card distinguishes them.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

import httpx

from my_agent_crew.llm.openai_compat import stream_chat, to_wire, tools_to_wire
from my_agent_crew.llm.types import Message, StreamItem, ToolSpec

DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
ENV_BASE_URL = "OLLAMA_BASE_URL"


def base_url(env: Mapping[str, str] | None = None) -> str:
    """Where ollama listens. The default is the port ollama uses out of the box, so a
    standard install needs no configuration at all."""
    source = os.environ if env is None else env
    return (source.get(ENV_BASE_URL) or "").strip() or DEFAULT_BASE_URL


class OllamaProvider:
    name = "ollama"

    def __init__(self, url: str | None = None, client: httpx.AsyncClient | None = None):
        self._base = (url or base_url()).rstrip("/")
        # A local model on a laptop can take a while on a long prompt, and a timeout here
        # costs the whole turn, so it is generous rather than snappy.
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(300.0))

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        model: str,
        reasoning: str = "",
    ) -> AsyncIterator[StreamItem]:
        body: dict[str, Any] = {
            "model": model,
            "messages": to_wire(messages),
            "stream": True,
        }
        if tools:
            body["tools"] = tools_to_wire(tools)
        # `reasoning` is ignored: ollama's thinking switch is per model, not an effort level.
        # No key: the server is on this machine, and ollama accepts none.
        async for item in stream_chat(
            self._client, f"{self._base}/chat/completions", body, {}, self.name, model
        ):
            yield item
