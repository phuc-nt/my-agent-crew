"""Every paid model call reaches the usage ledger: a turn's own through the message log,
the ones made beside a turn through `side_calls`, and a paid tool's price reaches its run."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime

import pytest

from my_agent_crew.activity.steps import apply_event
from my_agent_crew.agent.events import AssistantMessageEvent, ToolCallEvent, ToolResultEvent
from my_agent_crew.agent.turn_context import set_turn_conversation
from my_agent_crew.config import Route
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.metered_chain import MeteredChain
from my_agent_crew.llm.provider import AllRoutesFailed, ProviderChain, ProviderError
from my_agent_crew.llm.types import Completion, Message, TextDelta
from my_agent_crew.store import Store
from my_agent_crew.store.runs import RUNNING, RunRecord
from my_agent_crew.store.side_calls import SideCall

QUESTION = [Message(role="user", content="Đặt tên giúp")]


def chain_of(*scripts) -> ProviderChain:
    """One scripted provider per script, tried in order: `a`, then `b`."""
    names = ("a", "b")[: len(scripts)]
    providers = {n: ScriptedProvider(list(s), name=n) for n, s in zip(names, scripts, strict=True)}
    return ProviderChain(providers, [Route(n, f"{n}-model") for n in names])


async def ask(chain: ProviderChain) -> list:
    return [item async for item in chain.stream(QUESTION, [])]


class Stalling:
    """Starts answering and never finishes, the way a route that times out mid-answer does."""

    name = "a"

    async def stream(self, messages, tools, model, reasoning=""):
        yield TextDelta("Kế hoạch")
        await asyncio.Event().wait()


async def test_a_side_call_is_written_down_with_what_it_was_for_and_whose_it_was(store: Store):
    conv = store.create()
    metered = MeteredChain(
        chain_of([completion("Ôn thi", cost_usd=0.003)]), store, "coach", "title", conv.id
    )

    items = await ask(metered)

    assert isinstance(items[-1], Completion) and items[-1].message.content == "Ôn thi"
    assert store.side_calls.for_conversation(conv.id) == [
        SideCall("coach", "title", "a", "a-model", 0.003, 10, 5, None, conv.id)
    ]


async def test_every_item_passes_through_and_a_route_that_failed_first_is_not_written(
    store: Store,
):
    script = ([ProviderError("down")], [completion("ổn")])
    conv = store.create()

    plain = await ask(chain_of(*script))
    metered = await ask(MeteredChain(chain_of(*script), store, "default", "image", conv.id))

    assert metered == plain and len(plain) == 3  # RouteFailed, a chunk, the completion
    [call] = store.side_calls.for_conversation(conv.id)
    assert (call.provider, call.model) == ("b", "b-model")


async def test_without_a_named_conversation_the_turns_own_is_used(store: Store):
    conv = store.create()
    set_turn_conversation(conv.id)

    await ask(MeteredChain(chain_of([completion("ảnh")]), store, "default", "image"))

    assert [c.purpose for c in store.side_calls.for_conversation(conv.id)] == ["image"]


async def test_a_named_conversation_wins_over_the_one_the_task_inherited(store: Store):
    """A title task copies whatever turn its creator was in, often the previous one."""
    earlier, named = store.create(), store.create()
    set_turn_conversation(earlier.id)

    await ask(MeteredChain(chain_of([completion("tên")]), store, "default", "title", named.id))

    assert store.side_calls.for_conversation(earlier.id) == []
    assert len(store.side_calls.for_conversation(named.id)) == 1


async def test_a_call_dropped_after_its_first_chunk_is_written_down_at_an_unknown_cost(
    store: Store,
):
    conv = store.create()
    script = ([ProviderError("down")], [completion("một câu trả lời dài")])
    stream = MeteredChain(chain_of(*script), store, "default", "tool_summary", conv.id).stream(
        QUESTION, []
    )
    await anext(stream)  # the first route failing
    await anext(stream)  # the second route's first chunk
    await stream.aclose()

    [call] = store.side_calls.for_conversation(conv.id)
    assert (call.provider, call.model, call.cost_usd, call.prompt_tokens) == (
        "b",
        "b-model",
        None,
        None,
    )


async def test_a_call_that_timed_out_mid_answer_is_written_down_at_an_unknown_cost(
    store: Store,
):
    conv = store.create()
    stalled = ProviderChain({"a": Stalling()}, [Route("a", "a-model")])
    metered = MeteredChain(stalled, store, "default", "title", conv.id)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(ask(metered), 0.05)

    [call] = store.side_calls.for_conversation(conv.id)
    assert call.cost_usd is None and call.purpose == "title"


async def test_when_every_route_fails_before_answering_nothing_is_written(store: Store):
    conv = store.create()
    metered = MeteredChain(
        chain_of([ProviderError("x")], [ProviderError("y")]), store, "default", "wiki", conv.id
    )

    with pytest.raises(AllRoutesFailed):
        await ask(metered)

    assert store.side_calls.for_conversation(conv.id) == []


async def test_a_ledger_that_cannot_write_never_costs_the_caller_its_answer(
    store: Store, monkeypatch, caplog
):
    def locked(call: SideCall, stamp: str | None = None) -> None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(store.side_calls, "record", locked)

    items = await ask(MeteredChain(chain_of([completion("vẫn trả lời")]), store, "default", "wiki"))

    assert items[-1].message.content == "vẫn trả lời"
    assert "could not record a wiki side call" in caplog.text


def test_a_purpose_outside_the_fixed_set_is_refused_where_it_is_written(store: Store):
    with pytest.raises(ValueError, match="misc"):
        MeteredChain(chain_of([]), store, "default", "misc")
    with pytest.raises(ValueError, match="misc"):
        store.side_calls.record(SideCall("default", "misc", "p", "m", None))


async def test_a_transcription_is_a_side_call_of_its_own_named_purpose(store: Store):
    conv = store.create()
    metered = MeteredChain(
        chain_of([completion("nghe rõ rồi", cost_usd=0.00004)]),
        store,
        "master",
        "transcribe",
        conv.id,
    )

    items = await ask(metered)

    assert items[-1].message.content == "nghe rõ rồi"
    [call] = store.side_calls.for_conversation(conv.id)
    assert (call.purpose, call.cost_usd) == ("transcribe", 0.00004)


@pytest.fixture
def ledger(store: Store) -> Store:
    """A chat call and three side calls over two days, one of them of unknown cost."""
    conv = store.create()
    store.messages.append(
        conv.id,
        Message(role="assistant", content="ok"),
        "2026-09-20T09:00:00+00:00",
        "openrouter",
        "m1",
        0.05,
        50,
        10,
    )
    for call, stamp in (
        (SideCall("default", "title", "openrouter", "m1", 0.01, 20, 4, None, conv.id), "09:00:05"),
        (SideCall("default", "image", "vision", "eyes", 0.002, 800, 30, 700, conv.id), "09:00:03"),
    ):
        store.side_calls.record(call, f"2026-09-20T{stamp}+00:00")
    upkeep = SideCall("default", "consolidate", "openrouter", "m1", None, 300, 60)
    store.side_calls.record(upkeep, "2026-09-19T20:00:00+00:00")
    return store


def test_the_daily_totals_add_side_calls_to_the_message_log(ledger: Store):
    days = ledger.usage.by_day(2, today=datetime(2026, 9, 20, 12, tzinfo=UTC))

    assert [d["day"] for d in days] == ["2026-09-19", "2026-09-20"]
    assert days[0]["calls"] == 1 and days[0]["unknown_cost_calls"] == 1
    assert days[0]["cost_usd"] == 0.0 and days[0]["prompt_tokens"] == 300
    assert days[1]["calls"] == 3 and days[1]["cost_usd"] == pytest.approx(0.062)
    assert days[1]["prompt_tokens"] == 870 and days[1]["cached_tokens"] == 700


def test_the_model_totals_add_side_calls_to_the_message_log(ledger: Store):
    models = {m["model"]: m for m in ledger.usage.by_model()}

    assert list(models) == ["openrouter:m1", "vision:eyes"]
    assert models["openrouter:m1"]["calls"] == 3
    assert models["openrouter:m1"]["cost_usd"] == pytest.approx(0.06)
    assert models["openrouter:m1"]["unknown_cost_calls"] == 1
    assert models["vision:eyes"]["calls"] == 1 and models["vision:eyes"]["cached_tokens"] == 700


def test_spend_is_split_by_what_it_was_for_with_the_turns_own_calls_as_chat(ledger: Store):
    purposes = ledger.usage.by_purpose()

    assert [p["purpose"] for p in purposes] == ["chat", "title", "image", "consolidate"]
    assert purposes[0]["calls"] == 1 and purposes[0]["cost_usd"] == pytest.approx(0.05)
    assert purposes[3]["cost_usd"] == 0.0 and purposes[3]["unknown_cost_calls"] == 1


def test_one_model_name_behind_two_providers_stays_two_rows(store: Store):
    conv = store.create()
    for provider in ("openrouter", "deepseek"):
        store.messages.append(
            conv.id,
            Message(role="assistant", content="ok"),
            "2026-09-20T09:00:00+00:00",
            provider,
            "deepseek-v4-flash",
            0.01,
            10,
            2,
        )

    models = sorted(m["model"] for m in store.usage.by_model())

    assert models == ["deepseek:deepseek-v4-flash", "openrouter:deepseek-v4-flash"]


def fresh_run() -> RunRecord:
    return RunRecord("r1", "default", "c1", "chat", "t", RUNNING, "2026-09-29T08:00:00")


def test_a_paid_tool_adds_its_price_to_the_run_and_to_its_step():
    run = fresh_run()
    call = {"id": "c1", "name": "image_read", "arguments": {}}
    apply_event(run, AssistantMessageEvent(1, "", [call], "p", "m", 0.001), 10.0)
    apply_event(run, ToolCallEvent("c1", "image_read", {"path": "a.png"}), 10.1)
    result = ToolResultEvent("c1", "image_read", True, "Một bát phở.", cost_usd=0.002, metered=True)
    apply_event(run, result, 11.0)

    model, tool = run.steps
    assert model["cost_usd"] == 0.001 and tool["cost_usd"] == 0.002
    assert run.spent_usd == pytest.approx(0.003) and run.unknown_cost_calls == 0


def test_a_paid_tool_without_a_price_is_unknown_and_a_free_tool_is_nothing():
    run = fresh_run()
    apply_event(run, ToolCallEvent("c1", "image_read", {}), 10.0)
    apply_event(run, ToolResultEvent("c1", "image_read", True, "…", metered=True), 10.5)
    apply_event(run, ToolCallEvent("c2", "workspace_list", {}), 10.6)
    apply_event(run, ToolResultEvent("c2", "workspace_list", True, "a.txt"), 10.7)

    paid, free = run.steps
    assert paid["cost_usd"] is None and "cost_usd" not in free
    assert run.spent_usd == 0.0 and run.unknown_cost_calls == 1
