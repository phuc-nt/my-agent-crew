"""Web Push: the key a page subscribes with, a device's subscription kept or dropped, and a
test push so the person sees on the spot that the device hears it.

A subscription is the browser's own: an https address at its maker's push service and the
keys that encrypt for it. Only the page that subscribed can hand it over, and it is only
ever posted to; nothing in it is shown back."""

from __future__ import annotations

import binascii

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from my_agent_crew import texts_push
from my_agent_crew.server.deps import Rt
from my_agent_crew.webpush import crypto, push_store
from my_agent_crew.webpush.notices import INBOX_URL, Notice
from my_agent_crew.webpush.sender import send_one
from my_agent_crew.webpush.store import Subscription

router = APIRouter(tags=["push"])
# Where a push service reaches whoever runs a server that has no https origin of its own.
LOCAL_SUBJECT = "mailto:crew@localhost"
MAX_ENDPOINT = 2048
P256DH_BYTES, AUTH_BYTES = 65, 16


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)


class SubscriptionBody(BaseModel):
    endpoint: str = Field(max_length=MAX_ENDPOINT)
    keys: SubscriptionKeys


class EndpointBody(BaseModel):
    endpoint: str = Field(max_length=MAX_ENDPOINT)


def _decoded_length(text: str) -> int:
    try:
        return len(crypto.unb64url(text))
    except (binascii.Error, ValueError):
        return -1


def subject_for(request: Request) -> str:
    """The page's own https origin, which is the person's; a plain-http server has none."""
    origin = request.headers.get("origin", "")
    return origin if origin.startswith("https://") else LOCAL_SUBJECT


def _subscription(rt: Rt, endpoint: str) -> Subscription:
    for sub in push_store(rt.settings.home).subscriptions():
        if sub.endpoint == endpoint:
            return sub
    raise HTTPException(404, "subscription not found")


@router.get("/push/key")
def push_key(rt: Rt) -> dict[str, str]:
    return {"key": push_store(rt.settings.home).public_key()}


@router.post("/push/subscriptions", status_code=201)
def subscribe(body: SubscriptionBody, request: Request, rt: Rt) -> dict[str, bool]:
    if not body.endpoint.startswith("https://"):
        raise HTTPException(422, "a push endpoint is an https address")
    if _decoded_length(body.keys.p256dh) != P256DH_BYTES:
        raise HTTPException(422, "p256dh is not a P-256 public key")
    if _decoded_length(body.keys.auth) != AUTH_BYTES:
        raise HTTPException(422, "auth is not a 16-byte secret")
    sub = Subscription(body.endpoint, body.keys.p256dh, body.keys.auth, subject_for(request))
    push_store(rt.settings.home).add(sub)
    return {"subscribed": True}


@router.delete("/push/subscriptions")
def unsubscribe(body: EndpointBody, rt: Rt) -> dict[str, bool]:
    return {"removed": push_store(rt.settings.home).remove(body.endpoint)}


@router.post("/push/test")
async def push_test(body: EndpointBody, rt: Rt) -> dict[str, int]:
    """Pushes a notice to this one device; `status` is what its push service answered, 0
    when it could not be reached."""
    sub = _subscription(rt, body.endpoint)
    notice = Notice(texts_push.TEST_TITLE, texts_push.TEST_BODY, INBOX_URL, "test")
    store = push_store(rt.settings.home)
    if rt.client is not None:
        return {"status": await send_one(rt.client, store, sub, notice)}
    async with httpx.AsyncClient() as client:
        return {"status": await send_one(client, store, sub, notice)}
