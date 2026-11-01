"""The watch that pushes, and the sender that posts to each push service."""

from __future__ import annotations

import asyncio

import httpx

from my_agent_crew.activity.hub import ActivityHub
from my_agent_crew.store.db import Store
from my_agent_crew.webpush import crypto
from my_agent_crew.webpush.notices import Notice
from my_agent_crew.webpush.notifier import Notifier
from my_agent_crew.webpush.sender import send_all
from my_agent_crew.webpush.store import PushStore, Subscription
from tests.test_webpush_notices import request, run

NOTICE = Notice("t", "b", "/#/inbox", "request")


def subscribed(tmp_path, *endpoints: str) -> PushStore:
    push = PushStore(tmp_path)
    ua = crypto.public_raw(crypto.new_key())
    for endpoint in endpoints:
        push.add(Subscription(endpoint, ua, crypto.b64url(b"0" * 16), "https://crew.example"))
    return push


def test_a_request_or_a_run_is_pushed_once(tmp_path):
    notifier = Notifier(ActivityHub(Store()), Store(), subscribed(tmp_path, "https://p/1"), None)
    assert notifier.consider(request()) is not None
    assert notifier.consider(request()) is None
    first = notifier.consider(run(summary=""))
    assert first is None
    assert notifier.consider(run()) is not None
    assert notifier.consider(run()) is None


def test_nothing_is_pushed_before_a_device_subscribed(tmp_path):
    notifier = Notifier(ActivityHub(Store()), Store(), PushStore(tmp_path), None)
    assert notifier.consider(request()) is None


async def test_the_watch_pushes_what_the_stream_tells(tmp_path):
    store = Store()
    hub = ActivityHub(store)
    sent: list[Notice] = []
    told = asyncio.Event()

    async def send(notice: Notice) -> int:
        sent.append(notice)
        told.set()
        return 1

    notifier = Notifier(hub, store, subscribed(tmp_path, "https://p/1"), send)
    task = asyncio.create_task(notifier.run())
    await asyncio.sleep(0.01)
    job = hub.start("default", "job:brief", "Bản tin", None)
    hub.finish(job, status="done", summary="Có tin mới")
    await asyncio.wait_for(told.wait(), 2)
    task.cancel()
    assert [n.tag for n in sent] == ["job"]


async def test_the_sender_encrypts_signs_and_drops_a_gone_device(tmp_path):
    push = subscribed(tmp_path, "https://push.example/live", "https://push.example/gone")
    seen: list[httpx.Request] = []

    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(410 if req.url.path == "/gone" else 201)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        assert await send_all(client, push, NOTICE) == 1
    assert [s.endpoint for s in push.subscriptions()] == ["https://push.example/live"]
    first = seen[0]
    assert first.headers["content-encoding"] == "aes128gcm"
    assert first.headers["urgency"] == "high"
    assert first.headers["authorization"].startswith("vapid t=")
    assert b"/#/inbox" not in first.content


async def test_an_unreachable_push_service_is_left_for_the_next_notice(tmp_path):
    push = subscribed(tmp_path, "https://push.example/down")

    def handle(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        assert await send_all(client, push, NOTICE) == 0
    assert len(push.subscriptions()) == 1
