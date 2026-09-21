"""Several photos sent at once. Telegram delivers an album as one update per photo, all
carrying the same `media_group_id`, and the caption rides on the first only. Handled one
by one, the agent would answer each photo separately and see the caption on just one of
them. Here the updates of one album are gathered into one group, and a poll whose last
update belongs to an album waits briefly for the rest, which may still be on their way."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from my_agent_crew.channels.telegram_api import TelegramApi

# How long to wait for the next photo of an album, and how many times. Telegram sends the
# photos of one album within a second or so of each other; three rounds cover a slow upload
# without holding every other message for long.
ALBUM_SETTLE_SECONDS = 1.0
ALBUM_SETTLE_ROUNDS = 3


def media_group_id(update: dict[str, Any]) -> str:
    return str((update.get("message") or {}).get("media_group_id") or "")


def group_updates(updates: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Consecutive updates of one album become one group; anything else is a group of one."""
    groups: list[list[dict[str, Any]]] = []
    for update in updates:
        album = media_group_id(update)
        if album and groups and media_group_id(groups[-1][-1]) == album:
            groups[-1].append(update)
        else:
            groups.append([update])
    return groups


async def complete_album(
    api: TelegramApi,
    updates: list[dict[str, Any]],
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> list[dict[str, Any]]:
    """The same updates, extended with the rest of the album the last one belongs to, if
    any of it arrives within a few short rounds. A poll that ends on a non-album message
    (or on nothing) returns at once."""
    if not updates or not media_group_id(updates[-1]):
        return updates
    sleep = sleep or asyncio.sleep  # looked up per call so a test can shorten the wait
    album = media_group_id(updates[-1])
    for _ in range(ALBUM_SETTLE_ROUNDS):
        await sleep(ALBUM_SETTLE_SECONDS)
        more = await api.get_updates(int(updates[-1]["update_id"]) + 1, timeout=0)
        updates = [*updates, *more]
        if more and media_group_id(more[-1]) != album:
            break  # something after the album arrived: the album is complete
    return updates
