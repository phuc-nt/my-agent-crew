"""`/api/push/*`: the key a page subscribes with, a subscription kept and dropped, and the
test push."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.server import create_app, routes_push
from my_agent_crew.webpush import crypto, push_store

ENDPOINT = "https://push.example/abc"


def body(endpoint: str = ENDPOINT, p256dh: str | None = None, auth: str | None = None) -> dict:
    p256dh = p256dh or crypto.public_raw(crypto.new_key())
    auth = auth or crypto.b64url(b"1" * 16)
    return {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}


@pytest.fixture
def api(deps_factory):
    deps = deps_factory()
    with TestClient(create_app(deps, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, deps.settings.home


def test_the_key_is_the_one_the_home_keeps(api):
    client, home = api
    key = client.get("/api/push/key").json()["key"]
    assert key == push_store(home).public_key()
    assert len(crypto.unb64url(key)) == 65


def test_a_subscription_is_kept_with_the_page_origin_and_dropped(api):
    client, home = api
    answer = client.post(
        "/api/push/subscriptions", json=body(), headers={"origin": "http://127.0.0.1"}
    )
    assert answer.status_code == 201
    [sub] = push_store(home).subscriptions()
    assert (sub.endpoint, sub.subject) == (ENDPOINT, routes_push.LOCAL_SUBJECT)
    gone = client.request("DELETE", "/api/push/subscriptions", json={"endpoint": ENDPOINT})
    assert gone.json() == {"removed": True}
    assert push_store(home).subscriptions() == []


def test_an_https_page_is_its_own_subject():
    class Req:
        headers = {"origin": "https://crew.example"}

    assert routes_push.subject_for(Req()) == "https://crew.example"


@pytest.mark.parametrize(
    "bad",
    [
        body(endpoint="http://push.example/abc"),
        body(p256dh=crypto.b64url(b"short")),
        body(auth=crypto.b64url(b"x" * 8)),
        body(p256dh="!!not base64!!"),
    ],
)
def test_a_subscription_that_cannot_be_pushed_to_is_refused(api, bad):
    client, home = api
    assert client.post("/api/push/subscriptions", json=bad).status_code == 422
    assert push_store(home).subscriptions() == []


def test_the_test_push_goes_to_that_device_alone(api, monkeypatch):
    client, home = api
    client.post("/api/push/subscriptions", json=body())
    client.post("/api/push/subscriptions", json=body(endpoint="https://push.example/other"))
    sent = []

    async def fake_send(http, store, sub, notice):
        sent.append((sub.endpoint, notice.tag))
        return 201

    monkeypatch.setattr(routes_push, "send_one", fake_send)
    answer = client.post("/api/push/test", json={"endpoint": ENDPOINT})
    assert answer.json() == {"status": 201}
    assert sent == [(ENDPOINT, "test")]
    missing = client.post("/api/push/test", json={"endpoint": "https://push.example/none"})
    assert missing.status_code == 404
