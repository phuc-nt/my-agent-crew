"""The runtime hands its queue drain to the master's bot: the one it builds at start and the
one it builds again when the connections change. What waited in the bot's chat is answered
by whichever bot polls now."""

from pathlib import Path

import httpx
import pytest

from my_agent_crew.agent.turn_context import TELEGRAM
from my_agent_crew.config import load_settings
from my_agent_crew.server import runtime_connections
from my_agent_crew.server.runtime_build import build_runtime
from my_agent_crew.store.queue import FOLLOW_UP
from tests.queue_helpers import until
from tests.telegram_fake import CHAT, TOKEN

PROFILE = f"name: Thư ký\ntelegram:\n  token_env: CREW_BOT_TOKEN\n  chat_id: {CHAT}\n"


@pytest.fixture
async def runtime(tmp_path: Path, fake, monkeypatch):
    monkeypatch.setenv("CREW_BOT_TOKEN", TOKEN)
    fake.status = 409  # the loop backs off instead of spinning on an empty fake
    home = tmp_path / "home"
    home.mkdir()
    (home / "agent.yaml").write_text(PROFILE, encoding="utf-8")
    settings = load_settings(env={"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"})
    client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    runtime = build_runtime(settings, client, env={"CREW_BOT_TOKEN": TOKEN})
    yield runtime
    await runtime.stop_channel()
    await client.aclose()


def wait_in_the_chat(runtime) -> None:
    conv = runtime.channel.conversation()
    runtime.store.queue.add(conv.id, FOLLOW_UP, "tin chờ bot", TELEGRAM)
    runtime.drain.schedule(conv.id)


async def test_the_bot_built_at_start_answers_what_waited_in_its_chat(runtime, fake):
    wait_in_the_chat(runtime)
    runtime.start_channel()
    await until(lambda: fake.sent == ["(echo) tin chờ bot"])


async def test_a_rebuilt_bot_answers_what_waits_in_its_chat(runtime, fake):
    runtime.start_channel()
    first = runtime.channel
    await runtime_connections.restart_channel(runtime)
    assert runtime.channel is not first and runtime.channel_live
    wait_in_the_chat(runtime)
    await until(lambda: fake.sent == ["(echo) tin chờ bot"])
