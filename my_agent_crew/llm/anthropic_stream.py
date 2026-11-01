"""Reading a streamed Claude Messages reply into the engine's stream items.

The stream is server-sent events: `message_start` with the prompt's usage, then each
content block opened, filled by deltas and closed, then `message_delta` with the stop
reason and the output count. Text becomes `TextDelta`, a tool call's arguments arrive as
`input_json_delta` pieces and become `ToolCallDelta`, thinking becomes `ReasoningDelta`
when the API shows any.

`StreamStarted` waits for the first text, tool call or shown thinking rather than the
first event: a reply the model refuses before writing anything then raises before the
chain has seen an item, so the chain still moves on to the next route.
"""

from __future__ import annotations

import json
from typing import Any

from my_agent_crew.llm.anthropic_errors import stream_error
from my_agent_crew.llm.anthropic_pricing import cost_usd
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.tool_call_buffer import CUT_OFF, parse_arguments
from my_agent_crew.llm.types import (
    Completion,
    Message,
    ReasoningDelta,
    StreamItem,
    StreamStarted,
    TextDelta,
    ToolCall,
    ToolCallDelta,
    Usage,
)

# The API's stop reasons in the engine's (OpenAI's) words. `length` is what marks a tool
# call cut off at the output limit.
FINISH = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "pause_turn": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
    "model_context_window_exceeded": "length",
    "refusal": "content_filter",
}


def usage_from(raw: dict[str, Any], model: str) -> Usage:
    """`input_tokens` is only the part of the prompt the cache did not touch; the prompt
    is that plus what was read from and written to the cache."""
    fresh = int(raw.get("input_tokens") or 0)
    read = int(raw.get("cache_read_input_tokens") or 0)
    written = int(raw.get("cache_creation_input_tokens") or 0)
    output = int(raw.get("output_tokens") or 0)
    split = raw.get("cache_creation") if isinstance(raw.get("cache_creation"), dict) else {}
    hour = min(int(split.get("ephemeral_1h_input_tokens") or 0), written)
    return Usage(
        prompt_tokens=fresh + read + written,
        completion_tokens=output,
        cost_usd=cost_usd(
            model,
            fresh=fresh,
            cache_read=read,
            write_5m=written - hour,
            write_1h=hour,
            output=output,
        ),
        cached_tokens=read,
    )


class ReplyReader:
    """Feeds on the decoded events of one reply and hands back the items to yield."""

    def __init__(self, provider: str, model: str):
        self.provider, self.model = provider, model
        self.started = False
        self.text: list[str] = []
        self.calls: list[dict[str, Any]] = []  # in order: id, name, the input as sent
        self.block_call: dict[int, int] = {}  # content block index -> place in `calls`
        self.usage: dict[str, Any] = {}
        self.stop = ""
        self.ended = False

    def _start(self) -> list[StreamItem]:
        if self.started:
            return []
        self.started = True
        return [StreamStarted()]

    def feed(self, event: dict[str, Any]) -> list[StreamItem]:
        kind = event.get("type")
        if kind == "error":
            raise stream_error(event, self.model)
        if kind == "message_start":
            self.usage.update((event.get("message") or {}).get("usage") or {})
        elif kind == "message_delta":
            self.stop = (event.get("delta") or {}).get("stop_reason") or self.stop
            self.usage.update(
                {k: v for k, v in (event.get("usage") or {}).items() if v is not None}
            )
        elif kind == "message_stop":
            self.ended = True
        elif kind == "content_block_start":
            return self._open(event.get("index", 0), event.get("content_block") or {})
        elif kind == "content_block_delta":
            return self._delta(event.get("index", 0), event.get("delta") or {})
        return []

    def _open(self, index: int, block: dict[str, Any]) -> list[StreamItem]:
        if block.get("type") == "tool_use":
            self.block_call[index] = len(self.calls)
            given = block.get("input")
            self.calls.append(
                {
                    "id": block.get("id") or "",
                    "name": block.get("name") or "",
                    "json": "",
                    "given": given if isinstance(given, dict) else {},
                }
            )
            return self._start()
        if block.get("type") == "text":
            return self._start()
        return []

    def _delta(self, index: int, delta: dict[str, Any]) -> list[StreamItem]:
        kind = delta.get("type")
        if kind == "text_delta" and delta.get("text"):
            self.text.append(delta["text"])
            return [*self._start(), TextDelta(delta["text"])]
        if kind == "input_json_delta" and delta.get("partial_json") and index in self.block_call:
            place = self.block_call[index]
            call = self.calls[place]
            call["json"] += delta["partial_json"]
            return [
                *self._start(),
                ToolCallDelta(index=place, name=call["name"], chunk=delta["partial_json"]),
            ]
        if kind == "thinking_delta" and delta.get("thinking"):
            return [*self._start(), ReasoningDelta(delta["thinking"])]
        return []

    def _tool_calls(self, cut_off: bool) -> tuple[ToolCall, ...]:
        out = []
        for place, call in enumerate(self.calls):
            raw = call["json"] or json.dumps(call["given"])
            arguments, invalid = parse_arguments(raw)
            if invalid and cut_off and place == len(self.calls) - 1:
                invalid = CUT_OFF + invalid
            out.append(
                ToolCall(id=call["id"], name=call["name"], arguments=arguments, invalid=invalid)
            )
        return tuple(out)

    def completion(self) -> Completion:
        """The whole reply, once the stream has ended. A refusal with nothing written is
        an error, raised before any item, so the next route gets the turn."""
        if not self.ended:
            raise ProviderError(
                f"stream from {self.model} ended before message_stop", transient=True
            )
        finish = FINISH.get(self.stop, "stop")
        if self.stop == "refusal" and not self.text and not self.calls:
            raise ProviderError(f"{self.model} declined to answer (stop_reason refusal)")
        tool_calls = self._tool_calls(cut_off=finish == "length")
        message = Message(role="assistant", content="".join(self.text), tool_calls=tool_calls)
        return Completion(
            message=message,
            usage=usage_from(self.usage, self.model),
            provider=self.provider,
            model=self.model,
            finish_reason=finish,
        )
