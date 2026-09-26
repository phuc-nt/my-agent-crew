"""How hard a model thinks, and what the person sees while it does.

The health coach answered a "why" about three weeks of data on the provider's default
effort; the owner wanted it to think harder there and nowhere else. A thinking model also
stays silent for a long while before its first word, and the web showed nothing moving."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from my_agent_crew.agent.events import TextDeltaEvent, ThinkingEvent, to_dict
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agents.profile_yaml import parse_profile
from my_agent_crew.config import Route, Settings
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import (
    Completion,
    Message,
    ReasoningDelta,
    StreamStarted,
    TextDelta,
    Usage,
)
from tests.conftest import collect
from tests.test_openrouter import delta, provider_with, sse


def test_an_agents_effort_goes_on_every_route_it_may_fall_back_to(settings, tmp_path: Path):
    raw = {"routes": ["scripted:a", "scripted:b"], "reasoning": "medium"}
    profile = parse_profile("coach", tmp_path / "coach", raw, settings)
    assert [r.reasoning for r in profile.settings.routes] == ["medium", "medium"]


def test_an_agent_without_the_key_leaves_the_effort_to_the_provider(settings, tmp_path: Path):
    profile = parse_profile("coach", tmp_path / "coach", {"routes": ["scripted:a"]}, settings)
    assert profile.settings.routes == (Route("scripted", "a"),)


def test_an_unknown_effort_is_refused_rather_than_sent(settings: Settings, tmp_path: Path):
    with pytest.raises(ValueError, match="reasoning must be one of"):
        parse_profile("coach", tmp_path / "coach", {"reasoning": "max"}, settings)


@pytest.mark.parametrize("effort", ["medium", ""])
async def test_openrouter_asks_for_the_effort_only_when_one_is_set(effort: str):
    captured: list[httpx.Request] = []
    p = provider_with(sse(delta("ok")), capture=captured)
    await collect(p.stream([Message(role="user", content="hi")], [], "x/y", reasoning=effort))
    sent = json.loads(captured[0].content)
    assert sent.get("reasoning") == ({"effort": effort} if effort else None)


async def test_the_chain_hands_the_routes_effort_to_its_provider(deps_factory):
    deps = deps_factory(script=[completion("ok")], routes=(Route("scripted", "m", "high"),))
    await collect(run_turn(deps, deps.store.create().id, "hi"))
    assert deps.chain.providers["scripted"].requests[-1].reasoning == "high"


async def test_thoughts_stream_apart_from_the_answer_and_their_tokens_are_counted():
    thinking = {"choices": [{"delta": {"reasoning": "Row D+1 holds "}}]}
    usage = {"completion_tokens": 50, "completion_tokens_details": {"reasoning_tokens": 42}}
    items = await collect(
        provider_with(sse(thinking, delta("HRV 37"), {"usage": usage})).stream(
            [Message(role="user", content="hi")], [], "x/y"
        )
    )
    assert items[:2] == [StreamStarted(), ReasoningDelta("Row D+1 holds ")]
    assert items[-1].message.content == "HRV 37"
    assert items[-1].usage.reasoning_tokens == 42


class ThinkingProvider:
    name = "thinker"

    async def stream(self, messages, tools, model, reasoning=""):
        for piece in ("so ", "row ", "D+1"):
            yield ReasoningDelta(piece)
        yield TextDelta("HRV 37")
        yield Completion(
            message=Message(role="assistant", content="HRV 37"),
            usage=Usage(prompt_tokens=10, completion_tokens=50, reasoning_tokens=42),
            provider=self.name,
            model=model,
        )


async def test_the_person_is_told_once_that_the_model_is_thinking(deps_factory):
    deps = deps_factory(providers={"thinker": ThinkingProvider()}, routes=(Route("thinker", "m"),))
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, "vì sao?"))

    shown = [e for e in events if isinstance(e, ThinkingEvent | TextDeltaEvent)]
    assert shown == [ThinkingEvent(), TextDeltaEvent("HRV 37")]
    assert to_dict(shown[0]) == {"type": "thinking"}
    # The thoughts themselves are never kept: only how many tokens they cost.
    reply = deps.store.history(conv.id)[-1]
    assert reply.message.content == "HRV 37" and reply.reasoning_tokens == 42
