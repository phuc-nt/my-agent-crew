"""What one agent sees of another's turn when they share a chat."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from my_agent_crew import texts
from my_agent_crew.agents.profile import AgentProfile, default_profile
from my_agent_crew.llm.types import Message
from my_agent_crew.memory.shared_chat import MAX_LINE_CHARS, shared_chat_section
from my_agent_crew.store.db import Store

CHANNEL = "telegram:42"
# Messages are stamped in UTC when appended; the section takes the UTC stamp the person's
# day began at, so here "today" starts at UTC midnight.
TODAY = datetime.now(UTC).date().isoformat()


def start_of(day: str) -> str:
    return f"{day}T00:00:00+00:00"


@pytest.fixture
def peers(settings) -> dict[str, AgentProfile]:
    base = default_profile(settings)
    coach = AgentProfile(**{**base.__dict__, "id": "coach", "name": "HLV"})
    pong = AgentProfile(**{**base.__dict__, "id": "pong", "name": "Pong"})
    return {"coach": coach, "pong": pong}


def say(store: Store, agent_id: str, *texts_: str, channel: str = CHANNEL) -> None:
    conv = store.create(agent_id=agent_id, channel=channel)
    for index, text in enumerate(texts_):
        store.append(conv.id, Message(role="user" if index % 2 == 0 else "assistant", content=text))


def section(store: Store, peers, agent_id: str = "coach", channel: str = CHANNEL, **kwargs):
    return shared_chat_section(store, peers, channel, agent_id, start_of(TODAY), **kwargs)


def test_an_agent_sees_what_the_other_said_but_not_its_own_lines(store, peers):
    say(store, "pong", "Sếp ăn gì chưa?", "Em ghi rồi.")
    say(store, "coach", "Hôm nay tập gì?")

    found = section(store, peers)
    assert found is not None
    title, body = found
    assert title == texts.SHARED_CHAT_SECTION_TITLE
    assert body.splitlines() == ["[Pong] user: Sếp ăn gì chưa?", "[Pong] assistant: Em ghi rồi."]
    # The coach's own line is already in its history; repeating it would only cost tokens.
    assert "Hôm nay tập gì?" not in body


def test_a_turn_with_no_channel_has_no_shared_section(store, peers):
    """On the web there is no shared thread to read, so nothing is added."""
    say(store, "pong", "Sếp ăn gì chưa?")
    assert section(store, peers, channel="") is None


def test_only_what_was_said_today_is_carried_over(store, peers):
    say(store, "pong", "Chuyện hôm nay.")
    yesterday = start_of((date.fromisoformat(TODAY) - timedelta(days=1)).isoformat())
    assert shared_chat_section(store, peers, CHANNEL, "coach", yesterday) is not None
    tomorrow = start_of((date.fromisoformat(TODAY) + timedelta(days=1)).isoformat())
    assert shared_chat_section(store, peers, CHANNEL, "coach", tomorrow) is None


def test_another_chat_is_another_conversation_entirely(store, peers):
    say(store, "pong", "Chuyện nhà.", channel="telegram:99")
    assert section(store, peers) is None


def test_only_the_last_few_lines_are_carried(store, peers):
    say(store, "pong", *[f"dòng {n}" for n in range(14)])
    found = section(store, peers, limit=10)
    assert found is not None
    lines = found[1].splitlines()
    assert len(lines) == 10
    assert lines[-1].endswith("dòng 13")  # the newest line is the last one read


def test_a_long_message_is_cut_rather_than_swallowing_the_prompt(store, peers):
    say(store, "pong", "x" * 900)
    found = section(store, peers)
    assert found is not None
    (line,) = found[1].splitlines()
    assert len(line) <= MAX_LINE_CHARS + len("[Pong] user: ")


def test_tool_traffic_is_not_part_of_what_the_chat_saw(store, peers):
    conv = store.create(agent_id="pong", channel=CHANNEL)
    store.append(conv.id, Message(role="user", content="Ghi hộ."))
    store.append(conv.id, Message(role="tool", content="đã ghi 4kB", tool_call_id="t1", name="w"))

    found = section(store, peers)
    assert found is not None
    assert "4kB" not in found[1]


def test_an_agent_that_no_longer_exists_keeps_its_id(store, peers):
    say(store, "ghost", "Còn đây.")
    found = section(store, peers)
    assert found is not None and found[1].startswith("[ghost] ")


def test_nothing_said_means_no_section_at_all(store, peers):
    assert section(store, peers) is None
