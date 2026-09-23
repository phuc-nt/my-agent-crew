"""The HTTP side of changing a running crew's connections, shared by the routes that do:
the keys and hosts, and the model routes every agent falls back on.

Both try the change before keeping it. `prepared_or_refused` builds the crew as it would
be and turns a failure into a 409 that says why, so nothing is written for a change the
crew cannot run with; `apply` swaps the prepared crew in once the change is on disk.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

from fastapi import HTTPException
from ruamel.yaml import YAMLError

from my_agent_crew import texts
from my_agent_crew import texts_credentials as t
from my_agent_crew.config_parse import Route
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.server.runtime_connections import ChannelKey, Prepared, commit, prepare

logger = logging.getLogger(__name__)


def prepared_or_refused(
    rt: Runtime,
    env: Mapping[str, str],
    routes: Sequence[Route] | None = None,
    *,
    refusal: str = t.NOT_APPLICABLE,
    **fields: str,
) -> Prepared | None:
    """The crew rebuilt from `env` (and `routes`, when given), a 409 built from `refusal`
    naming why it cannot be, or None for a runtime that is never rebuilt live (a test app
    with no HTTP client). `refusal` is formatted with `error` and `fields`."""
    if rt.client is None:
        return None
    try:
        return prepare(rt, env, routes)
    except (ValueError, OSError, YAMLError) as exc:
        raise HTTPException(409, refusal.format(error=str(exc), **fields)) from None


async def apply(rt: Runtime, prepared: Prepared | None, before: ChannelKey) -> str | None:
    """Swap the prepared crew in; the reason it could not be, when it could not. The change
    is on disk by then, so a failure here costs a restart, not the change."""
    if prepared is None:
        return t.APPLY_FAILED.format(error=texts.RUNTIME_CANNOT_GROW)
    try:
        await commit(rt, prepared, before)
    except (RuntimeError, ValueError, OSError) as exc:
        logger.warning("connections saved but not applied: %s", type(exc).__name__)
        return t.APPLY_FAILED.format(error=str(exc))
    return None
