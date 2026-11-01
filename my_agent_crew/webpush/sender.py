"""Sends one notice to every browser that subscribed, and forgets those that left.

A push service answers 201 when it took the message, and 404 or 410 when the subscription
is gone (the app was removed, the permission withdrawn): such a subscription is dropped so
it is not tried again. Any other failure is logged and the next notice tries again."""

from __future__ import annotations

import json
import logging

import httpx

from my_agent_crew.webpush import crypto
from my_agent_crew.webpush.notices import Notice
from my_agent_crew.webpush.store import PushStore, Subscription

logger = logging.getLogger(__name__)
GONE = (404, 410)
# How long the push service keeps a message for a device that is off, in seconds.
TTL_SECONDS = 24 * 3600
SEND_TIMEOUT = 15.0


async def send_one(
    client: httpx.AsyncClient, store: PushStore, sub: Subscription, notice: Notice
) -> int:
    body = crypto.encrypt(json.dumps(notice.payload()).encode(), sub.p256dh, sub.auth)
    headers = {
        "Authorization": crypto.vapid_header(sub.endpoint, store.key(), sub.subject),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(TTL_SECONDS),
        # A request waits on the person; the rest can wait for the phone to wake.
        "Urgency": "high" if notice.tag == "request" else "normal",
        "Topic": notice.tag,
    }
    try:
        response = await client.post(
            sub.endpoint, content=body, headers=headers, timeout=SEND_TIMEOUT
        )
    except httpx.HTTPError as exc:
        logger.warning("webpush: send failed: %s", type(exc).__name__)
        return 0
    if response.status_code in GONE:
        store.remove(sub.endpoint)
        logger.info("webpush: a subscription is gone; dropped")
    elif response.status_code >= 300:
        logger.warning("webpush: push service answered %s", response.status_code)
    return response.status_code


async def send_all(client: httpx.AsyncClient, store: PushStore, notice: Notice) -> int:
    """How many push services took the notice."""
    taken = 0
    for sub in store.subscriptions():
        if 200 <= await send_one(client, store, sub, notice) < 300:
            taken += 1
    return taken
