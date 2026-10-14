"""The window a person signs in through on an agent's browser: opening it, saying one is done
with it, and what the agent's browser card is told of it and of where the browser may still
be signed in.

The window is a Chromium on the agent's own profile, shown on the screen of the machine the
crew runs on (`browser/login.py`); nothing of it passes through here but the moment it closes
by itself. Of a cookie only its host and when it runs out are ever told (`browser/logins.py`).
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from my_agent_crew import texts_browser_login as t
from my_agent_crew.browser import logins
from my_agent_crew.browser.kit import first_line, from_browser
from my_agent_crew.browser.launch import Stuck
from my_agent_crew.browser.login import (
    BUSY,
    GONE,
    NO_CONSOLE,
    SCREEN_LOCKED,
    STOPPING,
    LoginWindows,
    Refused,
)
from my_agent_crew.config_browser import profile_dir
from my_agent_crew.server.agent_edit_common import existing
from my_agent_crew.server.deps import Rt
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.tools.registry import ToolError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["agents"])
# The agent has no browser to sign in on: its own file gives it none, or the machine has none.
OFF = "off"
SAID = {
    NO_CONSOLE: t.LOGIN_NO_CONSOLE,
    SCREEN_LOCKED: t.LOGIN_LOCKED,
    BUSY: t.LOGIN_BUSY,
    STOPPING: t.LOGIN_STOPPING,
    GONE: t.LOGIN_CHANGED,
}


class LoginRequest(BaseModel):
    # Where the window starts; without one it opens empty.
    url: str = ""


def _windows(rt: Runtime, agent_id: str) -> LoginWindows | None:
    """The crew's windows, where the agent has a browser. An unknown agent is a 404."""
    existing(rt, agent_id)
    reads = rt.deps_for(agent_id).agent.settings.browser.reads
    return rt.browsers.windows if reads else None


def _moment(when: datetime) -> str:
    return when.isoformat(timespec="seconds")


def login_told(rt: Runtime, agent_id: str) -> dict[str, Any]:
    """Whether a window is open on the agent's profile and until when; whether one could be
    opened now, and what is in the way when none can."""
    windows = _windows(rt, agent_id)
    window = windows.window(agent_id) if windows is not None else None
    if window is not None:
        return {"open": True, "until": _moment(window.until), "available": False, "why": ""}
    why = windows.why_not(agent_id) if windows is not None else OFF
    return {"open": False, "until": None, "available": not why, "why": why}


async def logins_told(rt: Runtime, agent_id: str) -> list[dict[str, str | None]] | None:
    """The hosts the agent's browser may still be signed in to: asked of the browser or the
    window that is up now, else read from what was written when one last closed. None where
    the agent has no browser, and where none has ever closed on its profile."""
    windows = _windows(rt, agent_id)
    if windows is None:
        return None
    pool = windows.pool
    window, session = windows.window(agent_id), pool.running(agent_id)
    context = window.context if window else session.context if session else None
    hosts = await logins.read(context) if context is not None else None
    if hosts is None:
        hosts = await asyncio.to_thread(logins.recalled, profile_dir(pool.root, agent_id))
    if hosts is None:
        return None
    own = rt.deps_for(agent_id).agent.settings.browser.hosts
    return logins.told(hosts, own, time.time())


@router.post("/agents/{agent_id}/browser/login")
async def open_login(agent_id: str, rt: Rt, body: LoginRequest | None = None) -> dict[str, Any]:
    """Stops the agent's own browser and opens a window on its profile. One already open is
    told as it is: asking again does not keep it open longer."""
    windows = _windows(rt, agent_id)
    if windows is None:
        raise HTTPException(409, t.LOGIN_OFF)
    try:
        window = await windows.open(agent_id, body.url.strip() if body else "")
    except ToolError as error:  # the address is one no browser of the crew goes to
        raise HTTPException(422, str(error)) from error
    except Refused as error:
        # One that left while it was asked for is answered as the agent is now: the 404 of
        # an agent the crew does not have, or the words of one that has no browser.
        if error.why == GONE and _windows(rt, agent_id) is None:
            raise HTTPException(409, t.LOGIN_OFF) from error
        raise HTTPException(409, SAID[error.why]) from error
    except Exception as error:
        if not (from_browser(error) or isinstance(error, Stuck)):
            raise
        logger.warning("login window of agent %s did not open: %s", agent_id, first_line(error))
        raise HTTPException(409, t.LOGIN_FAILED.format(error=first_line(error))) from error
    return {"open": True, "until": _moment(window.until)}


@router.post("/agents/{agent_id}/browser/login/done")
async def close_login(agent_id: str, rt: Rt) -> dict[str, bool]:
    """Closes the window; the agent's next call starts its own browser, signed in as the
    window left it."""
    windows = _windows(rt, agent_id)
    return {"closed": windows is not None and await windows.done(agent_id)}
