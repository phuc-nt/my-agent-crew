"""A host that keeps the clock and the bot's inbox itself: with the clock outside no job
fires on its own while approvals still lapse, and a bot on a webhook polls nothing and
takes the updates it is handed, each once."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from my_agent_crew.config import load_settings
from my_agent_crew.hosting import external_clock, telegram_webhook
from my_agent_crew.server import build_runtime, routes_telegram_updates
from my_agent_crew.server import external_clock as clock_module
from my_agent_crew.server.external_clock import start_clock
from tests.telegram_fake import message, settle


def test_both_switches_default_to_a_server_on_one_machine():
    assert not external_clock({}) and not telegram_webhook({})
    assert external_clock({"MY_AGENT_SCHEDULER": "External "})
    assert telegram_webhook({"MY_AGENT_TELEGRAM": "webhook"})
    with pytest.raises(ValueError, match="MY_AGENT_SCHEDULER"):
        external_clock({"MY_AGENT_SCHEDULER": "cron"})
    with pytest.raises(ValueError, match="MY_AGENT_TELEGRAM"):
        telegram_webhook({"MY_AGENT_TELEGRAM": "poll"})


def _runtime(tmp_path: Path):
    agent = tmp_path / "agents" / "coach"
    agent.mkdir(parents=True)
    (agent / "agent.yaml").write_text(
        "name: Coach\nroutes: [fake:echo]\n"
        "schedules:\n  - id: brief\n    every: 1m\n    prompt: hi\n"
    )
    env = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"}
    return build_runtime(load_settings(env=env))


async def test_an_external_clock_starts_no_scheduler_but_lapses_approvals(tmp_path, monkeypatch):
    lapsed = asyncio.Event()

    async def expire(agents, hub, deliver):
        lapsed.set()

    monkeypatch.setattr(clock_module, "expire_overdue", expire)
    runtime = _runtime(tmp_path)
    task = start_clock(runtime, {"MY_AGENT_SCHEDULER": "external"})
    assert task is not None and runtime.scheduler._task is None
    await asyncio.wait_for(lapsed.wait(), timeout=1)
    task.cancel()
    assert runtime.hub.recent() == []  # the job is due by its own clock, and did not run


async def test_the_usual_clock_is_the_schedulers_own(tmp_path):
    runtime = _runtime(tmp_path)
    assert start_clock(runtime, {}) is None
    assert runtime.scheduler._task is not None
    await runtime.scheduler.stop()


async def test_a_webhook_bot_takes_each_update_once_and_never_polls(make_channel, fake):
    channel = make_channel()
    channel.webhook = True
    channel.start()
    await asyncio.wait_for(channel._task, timeout=1)
    assert fake.calls == ["setMyCommands"]

    assert await channel.receive([message(7, "xin chào")]) == 1
    await settle(channel)
    assert fake.sent == ["(echo) xin chào"]
    assert await channel.receive([message(7, "xin chào")]) == 0  # the webhook said it twice
    await settle(channel)
    assert fake.sent == ["(echo) xin chào"] and "getUpdates" not in fake.calls
    await channel.stop()


def _app(channel, live: bool = True) -> httpx.AsyncClient:
    app = FastAPI()
    app.state.runtime = SimpleNamespace(channel=channel, channel_live=live)
    app.include_router(routes_telegram_updates.router, prefix="/api")
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_the_route_hands_updates_to_a_webhook_bot_only(make_channel, fake):
    channel = make_channel()
    url, body = "/api/channels/telegram/updates", {"updates": [message(3, "hi")]}
    async with _app(channel) as client:
        assert (await client.post(url, json=body)).status_code == 409  # it polls
        channel.webhook = True
        assert (await client.post(url, json={"updates": [{"message": {}}]})).status_code == 422
        answer = await client.post(url, json=body)
        assert answer.status_code == 200 and answer.json() == {"handled": 1}
        await settle(channel)
    assert fake.sent == ["(echo) hi"]
    async with _app(None) as client:
        assert (await client.post(url, json=body)).status_code == 503
    async with _app(channel, live=False) as client:
        assert (await client.post(url, json=body)).status_code == 503
