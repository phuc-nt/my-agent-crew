"""An agent's browser as a person sees it: whether it is up, what each of its tabs shows, and
the two things a person may do to it — stop it, and close one tab. The window a person signs
in through is in `routes_browser_login.py`.

Nothing here starts a browser or sends a tab anywhere: an agent's own call does that, through
the gate. A tab is told by its host and its title and not by its whole address, which may
carry what signs a person in. What a person stops or closes goes at once, a call that is
using it included: that call ends in words that say the browser failed it.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException

from my_agent_crew import texts_browser_web as t
from my_agent_crew.browser.policy import host_of
from my_agent_crew.browser.pool import Session
from my_agent_crew.browser.tabs import JOB_OWNER, Tab
from my_agent_crew.server.agent_edit_common import existing
from my_agent_crew.server.deps import Rt
from my_agent_crew.server.routes_browser_login import login_told, logins_told
from my_agent_crew.server.runtime import Runtime

router = APIRouter(tags=["agents"])
# How long a page is waited on for its title: one that hangs is told without one.
TITLE_SECONDS = 1.0
TITLE_CHARS = 200


def _session(rt: Runtime, agent_id: str) -> Session | None:
    """The agent's browser if it is up now. An agent the crew does not have is a 404."""
    existing(rt, agent_id)
    pool = rt.browsers.pool
    return pool.running(agent_id) if pool is not None else None


async def _title(page: Any) -> str:
    try:
        return (await asyncio.wait_for(page.title(), TITLE_SECONDS))[:TITLE_CHARS]
    except Exception:  # noqa: BLE001 - a page that closed, crashed or hangs has none to tell
        return ""


def _idle(now: float, used: float) -> int:
    return max(0, int(now - used))


def _told(tab: Tab, title: str, now: float) -> dict[str, Any]:
    return {
        "id": tab.id,
        "label": tab.label,
        # A tab a scheduled run opened belongs to no conversation.
        "conversation_id": None if tab.owner == JOB_OWNER else tab.owner,
        "host": host_of(tab.page.url),
        "title": title,
        "idle_seconds": _idle(now, tab.used),
        "busy": tab.lock.locked(),
    }


@router.get("/agents/{agent_id}/browser")
async def read_browser(agent_id: str, rt: Rt) -> dict[str, Any]:
    session, browsers = _session(rt, agent_id), rt.browsers
    now = browsers.pool.clock() if browsers.pool is not None else 0.0
    tabs = session.tabs.all() if session else []
    tabs.sort(key=lambda tab: (tab.used, tab.id), reverse=True)
    titles = await asyncio.gather(*(_title(tab.page) for tab in tabs))
    return {
        "mode": rt.deps_for(agent_id).agent.settings.browser.mode,
        # Why an agent that asks for a browser has none: the machine's file, or what is missing.
        "enabled": browsers.settings.enabled,
        "installed": browsers.found.ok,
        "running": session is not None,
        "busy": bool(session and session.busy),
        "idle_seconds": _idle(now, session.used) if session else None,
        "tabs": [_told(tab, title, now) for tab, title in zip(tabs, titles, strict=True)],
        "login": login_told(rt, agent_id),
        "logins": await logins_told(rt, agent_id),
    }


@router.post("/agents/{agent_id}/browser/stop")
async def stop_browser(agent_id: str, rt: Rt) -> dict[str, bool]:
    """What it is signed in to stays in its profile; its next call starts it again."""
    existing(rt, agent_id)
    return {"stopped": await rt.browsers.stop(agent_id)}


@router.delete("/agents/{agent_id}/browser/tabs/{tab_id}")
async def close_tab(agent_id: str, tab_id: int, rt: Rt) -> dict[str, int]:
    session = _session(rt, agent_id)
    tab = next((tab for tab in session.tabs.all() if tab.id == tab_id), None) if session else None
    if session is None or tab is None:
        raise HTTPException(404, t.TAB_UNKNOWN)
    await session.tabs.close(tab)
    return {"closed": tab_id}
