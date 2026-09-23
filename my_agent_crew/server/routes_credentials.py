"""Setting, replacing and removing the keys the crew connects with, from the web.

Values are write-only. A request carries a value in; nothing carries one out — the list
says which names are set and where from, and only non-secrets (a host address) are
echoed. The value goes to `<home>/env`, owner-only, and into this process's environment,
then the crew is rebuilt from it so the new key works on the next message rather than
after a restart.

A change is tried before it is kept: the crew is rebuilt from the environment as it
would be, and only when that works is the file written. Removing the one key the routes
need is refused with the reason, rather than saved and leaving a crew that cannot answer
and a server that will not start. Requests from other sites are turned away app-wide by
`local_guard`; the file written here is sourced by a shell at the next start.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from my_agent_crew import texts_credentials as t
from my_agent_crew.env_file import (
    MAX_VALUE_CHARS,
    NAME_RE,
    check_value,
    env_path,
    read_env,
    remove_env,
)
from my_agent_crew.env_file import set_env as write_env
from my_agent_crew.server.agent_edit_common import write_lock
from my_agent_crew.server.connection_apply import apply, prepared_or_refused
from my_agent_crew.server.credential_catalog import catalog, describe, name_allowed
from my_agent_crew.server.credential_checks import (
    CHECK_TIMEOUT_SECONDS,
    default_value,
    run_check,
)
from my_agent_crew.server.deps import Rt
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.server.runtime_connections import channel_key

router = APIRouter(tags=["credentials"])


class ValueRequest(BaseModel):
    value: str


def _checked_name(name: str) -> None:
    if not name_allowed(name):
        if not NAME_RE.match(name):
            raise HTTPException(422, t.NAME_INVALID)
        raise HTTPException(422, t.NAME_RESERVED.format(name=name))


def _checked_value(rt: Runtime, name: str, raw: str) -> str:
    """The value to store, or a 422 that never repeats it."""
    try:
        value = check_value(raw)
    except ValueError as exc:
        reason = exc.args[0]
        if reason == "empty":
            raise HTTPException(422, t.VALUE_EMPTY) from None
        if reason == "multiline":
            raise HTTPException(422, t.VALUE_MULTILINE) from None
        raise HTTPException(422, t.VALUE_TOO_LONG.format(limit=MAX_VALUE_CHARS)) from None
    known = catalog(rt).get(name)
    if known is not None and known.url and urlsplit(value).scheme not in ("http", "https"):
        raise HTTPException(422, t.VALUE_NOT_URL.format(name=name))
    return value.rstrip("/") if known is not None and known.url else value


def _answer(rt: Runtime, problem: str | None) -> dict[str, Any]:
    return {**describe(rt), "restart_required": problem}


@router.get("/credentials")
def list_credentials(rt: Rt) -> dict[str, Any]:
    return _answer(rt, None)


@router.put("/credentials/{name}")
async def put_credential(name: str, body: ValueRequest, rt: Rt) -> dict[str, Any]:
    _checked_name(name)
    value = _checked_value(rt, name, body.value)
    async with write_lock:
        prepared = prepared_or_refused(rt, {**os.environ, name: value})
        before = channel_key(rt.agents, os.environ)
        write_env(env_path(rt.settings.home), name, value)
        os.environ[name] = value
        problem = await apply(rt, prepared, before)
    return _answer(rt, problem)


@router.delete("/credentials/{name}")
async def delete_credential(name: str, rt: Rt) -> dict[str, Any]:
    _checked_name(name)
    async with write_lock:
        path = env_path(rt.settings.home)
        stored = read_env(path).get(name)
        if stored is None:
            if os.environ.get(name):
                raise HTTPException(409, t.NOT_IN_FILE.format(name=name))
            raise HTTPException(404, t.NOT_SET.format(name=name))
        # Only unset what the file put there; a value the process was started with is
        # the person's own override and stays.
        unset = os.environ.get(name) == stored
        after = {k: v for k, v in os.environ.items() if not (unset and k == name)}
        prepared = prepared_or_refused(rt, after, refusal=t.NOT_REMOVABLE, name=name)
        before = channel_key(rt.agents, os.environ)
        remove_env(path, name)
        if unset:
            os.environ.pop(name, None)
        problem = await apply(rt, prepared, before)
    return _answer(rt, problem)


@router.post("/credentials/{name}/check")
async def check_credential(name: str, rt: Rt) -> dict[str, Any]:
    known = catalog(rt).get(name)
    if known is None or known.check is None:
        raise HTTPException(404, t.NOT_CHECKABLE.format(name=name))
    value = os.environ.get(name) or default_value(known.check)
    if not value:
        raise HTTPException(409, t.NOT_SET.format(name=name))
    if rt.client is not None:
        return await run_check(known.check, value, rt.client)
    async with httpx.AsyncClient(timeout=CHECK_TIMEOUT_SECONDS) as client:
        return await run_check(known.check, value, client)
