"""One Telegram bot serving several agents: `@<agent id>` picks the agent, the pick sticks
until the next mention, every reply carries the agent's name, and the server builds one
poller for the whole group."""

import asyncio
from dataclasses import replace
from datetime import date
from pathlib import Path

import httpx
import pytest

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agents.channels import TelegramConfig
from my_agent_crew.channels import CHANNELS_DIR, TelegramApi, TelegramChannel, build_channels
from my_agent_crew.channels.telegram_commands import parse_mention
from my_agent_crew.config import Route, load_settings
from my_agent_crew.memory.shared_chat import shared_chat_section
from my_agent_crew.server import build_runtime
from my_agent_crew.server.runtime import Runtime
from tests.test_app_wiring import env_for
from tests.test_channels_telegram import CHAT, TOKEN, FakeTelegram, message


def named(deps, agent_id: str, name: str):
    return replace(deps, profile=replace(deps.profile, id=agent_id, name=name))


@pytest.fixture
def fake() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture
def shared(deps_factory, fake, tmp_path: Path) -> TelegramChannel:
    base = deps_factory(routes=(Route("fake", "echo"),))
    agents = {"coach": named(base, "coach", "Coach"), "pong": named(base, "pong", "Pong")}
    peers = {agent_id: deps.agent for agent_id, deps in agents.items()}
    for deps in agents.values():
        deps.peers = peers
    api = TelegramApi(TOKEN, httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)))
    return TelegramChannel(agents, ActivityHub(base.store), api, CHAT, tmp_path / "offset")


def test_parse_mention_reads_a_leading_agent_id_only():
    assert parse_mention("@pong  hỏi gì đó") == ("pong", "hỏi gì đó")
    assert parse_mention("@Pong") == ("pong", "")
    assert parse_mention("@health-coach /status") == ("health-coach", "/status")
    assert parse_mention("email me @ noon") == (None, "email me @ noon")
    assert parse_mention("hỏi @pong nhé") == (None, "hỏi @pong nhé")


async def test_mention_routes_to_that_agent_and_sticks_for_bare_messages(shared, fake):
    fake.updates = [message(1, "@pong ping"), message(2, "again"), message(3, "@coach hi")]
    await shared.poll_once()
    assert fake.sent == ["[Pong]\n(echo) ping", "[Pong]\n(echo) again", "[Coach]\n(echo) hi"]
    convs = {c.agent_id: c for c in shared.store.list()}
    assert set(convs) == {"coach", "pong"}
    assert convs["pong"].channel == f"telegram:{CHAT}" == convs["coach"].channel
    assert [run.agent_id for run in shared.hub.recent()] == ["coach", "pong", "pong"]
    assert shared.current_agent() == "coach" and shared.deps.agent.id == "coach"


async def test_first_agent_answers_before_any_mention(shared, fake):
    fake.updates = [message(1, "hello")]
    await shared.poll_once()
    assert fake.sent == ["[Coach]\n(echo) hello"]


async def test_bare_mention_switches_and_announces_without_a_model_call(shared, fake):
    fake.updates = [message(1, "@pong"), message(2, "later")]
    await shared.poll_once()
    switched = texts.TELEGRAM_AGENT_SWITCHED.format(name="Pong", agent_id="pong")
    assert fake.sent == [switched, "[Pong]\n(echo) later"]
    assert [run.agent_id for run in shared.hub.recent()] == ["pong"]


async def test_unknown_mention_lists_the_agents(shared, fake):
    fake.updates = [message(1, "@nobody hi")]
    await shared.poll_once()
    [reply] = fake.sent
    assert reply.startswith("Không có agent @nobody")
    assert "▶ @coach — Coach" in reply and "• @pong — Pong" in reply
    assert shared.hub.recent() == []


async def test_help_and_agents_commands_come_from_the_bot_itself(shared, fake):
    fake.updates = [message(1, "@pong"), message(2, "/help"), message(3, "/agents")]
    await shared.poll_once()
    _, help_reply, agents_reply = fake.sent
    assert help_reply.startswith("/new") and not help_reply.startswith("[")
    assert agents_reply == texts.TELEGRAM_AGENTS.format(agents="• @coach — Coach\n▶ @pong — Pong")
    assert agents_reply in help_reply


async def test_agent_commands_apply_to_the_mentioned_or_current_agent(shared, fake):
    fake.updates = [message(1, "@pong hi"), message(2, "@coach /new"), message(3, "/status")]
    await shared.poll_once()
    one = texts.TELEGRAM_NEW_CONVERSATION_ONE.format(name="Coach")
    assert fake.sent[1] == f"[Coach]\n{one}"
    assert fake.sent[2].startswith("[Coach]\n")
    assert {c.agent_id for c in shared.store.list()} == {"coach", "pong"}


async def test_a_new_without_a_mention_cuts_every_agent_on_the_bot(shared, fake):
    """The chat is one window: asking for a fresh start means the window, not whichever
    agent happens to be current. `@id /new` is how a single agent is cut."""
    fake.updates = [message(1, "@pong hi"), message(2, "@coach hi"), message(3, "/new")]
    await shared.poll_once()
    every = texts.TELEGRAM_NEW_CONVERSATION_ALL.format(agents="Coach, Pong")
    assert fake.sent[2] == f"[Coach]\n{every}"
    assert len(shared.store.list("coach")) == 2 and len(shared.store.list("pong")) == 2


async def test_a_mentioned_new_leaves_the_other_agents_alone(shared, fake):
    fake.updates = [message(1, "@pong hi"), message(2, "@coach hi"), message(3, "@pong /new")]
    await shared.poll_once()
    assert len(shared.store.list("pong")) == 2 and len(shared.store.list("coach")) == 1


async def test_deliver_uses_the_prefix_of_the_conversation_agent(shared, fake):
    fake.updates = [message(1, "@pong ping")]
    await shared.poll_once()
    fake.sent.clear()
    [conv] = shared.store.list("pong")
    assert await shared.deliver(conv.id) is True
    assert fake.sent == ["[Pong]\n(echo) ping"]
    other = shared.store.create(agent_id="stranger")
    assert await shared.deliver(other.id) is False


def test_build_channels_groups_agents_by_token_env(tmp_path: Path, caplog):
    for agent_id, name in (("coach", "Coach"), ("pong", "Pong")):
        agent = tmp_path / "agents" / agent_id
        agent.mkdir(parents=True)
        (agent / "agent.yaml").write_text(
            f"name: {name}\nroutes: [fake:echo]\ntelegram:\n  token_env: BOT\n  chat_id: 42\n"
        )
    (tmp_path / "agents" / "coach" / "telegram.offset").write_text("120")
    settings = load_settings(env=env_for(tmp_path))
    with caplog.at_level("INFO"):
        rt = build_runtime(settings, env=env_for(tmp_path, BOT="1:abc"))
    assert set(rt.channels) == {"coach", "pong"}
    assert rt.channels["coach"] is rt.channels["pong"] and len(rt.unique_channels()) == 1
    assert rt.channels["coach"].shared and rt.channels["coach"].label == "coach+pong"
    assert (tmp_path / CHANNELS_DIR / "telegram-bot.offset").read_text() == "120"
    assert rt.channels["coach"]._offset == 120
    assert "telegram channel enabled for coach, pong" in caplog.text


def test_agents_on_one_bot_must_share_its_chat(tmp_path: Path, deps_factory):
    base = deps_factory(routes=(Route("fake", "echo"),))
    coach = named(base, "coach", "Coach")
    pong = named(base, "pong", "Pong")
    agents = {
        "coach": replace(coach, profile=replace(coach.profile, telegram=TelegramConfig("BOT", 1))),
        "pong": replace(pong, profile=replace(pong.profile, telegram=TelegramConfig("BOT", 2))),
    }
    with pytest.raises(ValueError, match="chat_id"):
        build_channels(agents, ActivityHub(base.store), httpx.AsyncClient(), {"BOT": "1:abc"})


async def test_a_shared_channel_polls_and_registers_the_menu_once(shared, fake):
    rt = Runtime(shared.deps.settings, shared.store, shared.agents, shared.hub)
    rt.channels = {"coach": shared, "pong": shared}
    fake.status = 409
    rt.start_channels()
    await asyncio.sleep(0.02)
    await rt.stop_channels()
    assert fake.calls.count("setMyCommands") == 1


async def test_the_second_agent_reads_what_the_first_one_was_told(shared, fake):
    """The person asks Pong something, then turns to the coach: the coach sees the ask.

    Both agents answer through the echo provider, which keeps no record of its prompts, so
    this checks the section the coach's next turn would be given.
    """
    fake.updates = [message(1, "@pong sáng nay ăn phở"), message(2, "@coach vậy trưa ăn gì?")]
    await shared.poll_once()

    coach = shared.agents["coach"]
    found = shared_chat_section(
        shared.store, coach.peers, f"telegram:{CHAT}", "coach", date.today().isoformat()
    )
    assert found is not None
    title, body = found
    assert title == texts.SHARED_CHAT_SECTION_TITLE
    assert "[Pong] user: sáng nay ăn phở" in body
    # Its own question stays where it already is, in the conversation history.
    assert "[Coach]" not in body
