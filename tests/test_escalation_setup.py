"""Where an escalation route comes from and what a move leaves behind: the key an agent's
file names it with, the route that is left unused because it is no way out, and the step a
run's timeline shows (`agents/profile_settings.py`, `server/agent_assembly.py`,
`activity/route_steps.py`)."""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

import pytest

from my_agent_crew import texts
from my_agent_crew.activity.steps import CLOCK_KEY, apply_event
from my_agent_crew.agent.events import (
    AssistantMessageEvent,
    DoneEvent,
    EscalatedEvent,
    ModelCallEvent,
    RouteFallbackEvent,
    ToolResultEvent,
    to_dict,
)
from my_agent_crew.agents.profile_yaml import parse_profile
from my_agent_crew.config import Route, Settings
from my_agent_crew.llm.fake import EchoProvider, ScriptedProvider, completion
from my_agent_crew.llm.provider import ProviderChain, ProviderError
from my_agent_crew.server.agent_assembly import escalation_chain, escalation_problem
from my_agent_crew.store.runs import DONE, RUNNING, RunRecord
from tests.test_server_api import parse_sse


def fresh_run() -> RunRecord:
    return RunRecord("r1", "default", "c1", "chat", "t", RUNNING, "2026-10-06T08:00:00")


def test_a_move_for_an_error_takes_the_place_of_the_model_step_that_was_waiting():
    """The request opened a model step that no route answered. The move says where that
    wait went; the call made next opens its own step, so none is left open behind it."""
    run = fresh_run()
    apply_event(run, ModelCallEvent("sent"), 10.0)
    apply_event(run, RouteFallbackEvent("openrouter", "flash", "HTTP 502"), 12.0)
    moved = EscalatedEvent("error", "openrouter", "big", "every route failed — " + "x" * 400)
    apply_event(run, moved, 12.5)

    assert [(s["kind"], s["duration_ms"]) for s in run.steps] == [
        ("fallback", 2000),
        ("escalation", 500),
    ]
    assert all(CLOCK_KEY not in step for step in run.steps)
    step = run.steps[-1]
    assert (step["reason"], step["provider"], step["model"]) == ("error", "openrouter", "big")
    assert len(step["error"]) <= 161 and step["error"].endswith("…")

    apply_event(run, ModelCallEvent("sent"), 12.5)
    apply_event(run, AssistantMessageEvent(1, "xong", [], "openrouter", "big", 0.01), 14.0)
    apply_event(run, DoneEvent(0.01, 1), 14.0)

    assert [s["kind"] for s in run.steps] == ["fallback", "escalation", "model"]
    assert run.steps[-1]["model"] == "big" and run.steps[-1]["duration_ms"] == 1500
    assert run.status == DONE and run.spent_usd == pytest.approx(0.01)


def test_a_move_for_repeating_itself_is_a_step_of_its_own_with_no_error():
    run = fresh_run()
    apply_event(run, ModelCallEvent("sent"), 10.0)
    call = {"id": "c5", "name": "count_up", "arguments": {}}
    apply_event(run, AssistantMessageEvent(1, "", [call], "openrouter", "flash", 0.001), 11.0)
    apply_event(run, ToolResultEvent("c5", "count_up", False, texts.LOOP_ESCALATED_TOOL), 11.0)
    apply_event(run, EscalatedEvent("loop", "openrouter", "big"), 11.0)

    assert [s["kind"] for s in run.steps][-1] == "escalation"
    assert run.steps[-1] == {
        "kind": "escalation",
        "reason": "loop",
        "provider": "openrouter",
        "model": "big",
        "duration_ms": 0,
    }
    # The model step before it answered and stays as it was.
    model = next(s for s in run.steps if s["kind"] == "model")
    assert model["model"] == "flash" and model["duration_ms"] == 1000
    assert run.status == RUNNING


def test_a_move_reaches_a_reader_as_an_event_of_its_own_kind():
    wire = to_dict(EscalatedEvent("loop", "openrouter", "big"))

    assert wire == {
        "type": "escalated",
        "reason": "loop",
        "provider": "openrouter",
        "model": "big",
        "error": "",
    }


async def test_a_turn_that_moved_tells_the_reader_and_keeps_the_step_in_its_run(served):
    app = served([ProviderError("upstream 502")])
    deps = app.runtime.default
    spare = ScriptedProvider([completion("đã xong")], name="strong")
    deps.escalation = ProviderChain(
        {**deps.chain.providers, "strong": spare}, [Route("strong", "big")]
    )

    reply = await app.client.post(app.messages, json={"text": "chào"})

    events = parse_sse(reply.text)
    kinds = [e["type"] for e in events]
    assert kinds[-1] == "done" and "error" not in kinds
    [moved] = [e for e in events if e["type"] == "escalated"]
    assert (moved["reason"], moved["provider"], moved["model"]) == ("error", "strong", "big")
    assert "upstream 502" in moved["error"]
    assert kinds.index("route_fallback") < kinds.index("escalated")
    run = app.runtime.store.runs.latest_for_conversation(app.conv.id)
    assert run is not None and run.status == DONE
    assert [s["kind"] for s in run.steps] == ["fallback", "escalation", "model"]
    assert (run.steps[-1]["provider"], run.steps[-1]["model"]) == ("strong", "big")


def test_an_agent_names_its_escalation_route_in_its_own_file(settings: Settings, tmp_path: Path):
    raw = {"escalation_route": "openrouter:big", "reasoning": "high"}

    profile = parse_profile("coach", tmp_path / "coach", raw, settings)

    # The effort the agent asks of its own routes is asked of this one too.
    assert profile.settings.escalation_route == Route("openrouter", "big", reasoning="high")
    assert profile.to_dict()["escalation_route"] == {"provider": "openrouter", "model": "big"}


def test_an_agent_that_names_none_has_none_whatever_the_crew_was_given(
    settings: Settings, tmp_path: Path
):
    """Off unless an agent's own file turns it on: never handed down with the crew's
    settings, so no agent starts moving to a dearer model because another one may."""
    base = replace(settings, escalation_route=Route("openrouter", "big"))

    for raw in ({}, {"escalation_route": None}, {"escalation_route": ""}):
        profile = parse_profile("coach", tmp_path / "coach", raw, base)
        assert profile.settings.escalation_route is None
        assert profile.to_dict()["escalation_route"] is None


@pytest.mark.parametrize("value", ["big", ":big", "openrouter:", ["openrouter:big"], 7])
def test_an_escalation_route_that_is_not_a_provider_and_a_model_fails_by_name(
    settings: Settings, tmp_path: Path, value
):
    with pytest.raises(ValueError, match="agent coach: escalation_route"):
        parse_profile("coach", tmp_path / "coach", {"escalation_route": value}, settings)


def with_spare(settings: Settings, route: str) -> Settings:
    return replace(settings, escalation_route=Route.parse(route))


def test_a_usable_escalation_route_becomes_a_chain_of_that_one_route(settings: Settings):
    providers = {"scripted": EchoProvider(), "fake": EchoProvider()}

    chain = escalation_chain(with_spare(settings, "fake:big"), providers)

    assert chain is not None and [(r.provider, r.model) for r in chain.routes] == [("fake", "big")]
    assert escalation_chain(settings, providers) is None


@pytest.mark.parametrize(
    ("route", "problem"),
    [
        # A file written for a key this machine lacks still loads.
        ("openrouter:big", texts.ESCALATION_ROUTE_UNUSABLE),
        # A turn stuck on a model gains nothing from being sent to the same one.
        ("scripted:m", texts.ESCALATION_ROUTE_SAME),
    ],
    ids=["provider not built", "one of the agent's own routes"],
)
def test_a_route_that_is_no_way_out_is_left_unused_and_said_so(
    settings: Settings, caplog, route, problem
):
    providers = {"scripted": EchoProvider(), "fake": EchoProvider()}
    named = with_spare(settings, route)

    with caplog.at_level(logging.WARNING):
        chain = escalation_chain(named, providers)

    assert chain is None
    assert escalation_problem(named, providers) == problem.format(route=route)
    assert route in caplog.text and "left unused" in caplog.text


def test_the_same_model_on_another_provider_is_a_way_out(settings: Settings):
    providers = {"scripted": EchoProvider(), "fake": EchoProvider()}

    assert escalation_problem(with_spare(settings, "fake:m"), providers) == ""
    assert escalation_problem(settings, providers) == ""
