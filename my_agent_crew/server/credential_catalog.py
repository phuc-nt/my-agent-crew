"""Which environment variables the connections page knows how to set, and how each one
is reported.

A known variable carries a group (which card it sits on), whether it is a secret, and
the check that proves it works. Variables the person added themselves — a skill's user
id, a token some script reads — are listed from the env file under "other". Nothing
here ever returns a secret's value; only non-secrets (a host address) are echoed back,
because the page cannot tell "off" from "wrong host" otherwise.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from my_agent_crew.env_file import NAME_RE, env_path, read_env
from my_agent_crew.server.credential_checks import default_value
from my_agent_crew.server.runtime import Runtime


@dataclass(frozen=True)
class Known:
    name: str
    group: str  # "model" | "search" | "telegram" | "other"
    secret: bool = True
    url: bool = False
    check: str | None = None


KNOWN = (
    Known("OPENROUTER_API_KEY", "model", check="openrouter"),
    Known("OLLAMA_BASE_URL", "model", secret=False, url=True, check="ollama"),
    Known("BRAVE_API_KEY", "search"),
    Known("TAVILY_API_KEY", "search"),
    Known("FIRECRAWL_BASE_URL", "search", secret=False, url=True, check="firecrawl"),
    Known("FIRECRAWL_API_KEY", "search"),
)
# Variables that steer the process itself. Setting one from a browser would change how
# Python, the shell or this server starts — or where it looks for its own home.
RESERVED = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "PWD",
        "LANG",
        "LC_ALL",
        "TERM",
        "TMPDIR",
        "VIRTUAL_ENV",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
    }
)
RESERVED_PREFIXES = ("MY_AGENT_", "DYLD_", "LD_", "PYTHON", "UV_")


def name_allowed(name: str) -> bool:
    return bool(NAME_RE.match(name)) and not (
        name in RESERVED or name.startswith(RESERVED_PREFIXES)
    )


def catalog(rt: Runtime) -> dict[str, Known]:
    """Every variable the page shows, in the order it shows them: the known ones, each
    Telegram token a profile names, then whatever else the env file holds."""
    entries = {known.name: known for known in KNOWN}
    for profile in rt.profiles():
        if profile.telegram is not None:
            entries.setdefault(
                profile.telegram.token_env,
                Known(profile.telegram.token_env, "telegram", check="telegram"),
            )
    for name in read_env(env_path(rt.settings.home)):
        entries.setdefault(name, Known(name, "other"))
    return entries


def describe(rt: Runtime) -> dict[str, Any]:
    file_values = read_env(env_path(rt.settings.home))
    items = []
    for known in catalog(rt).values():
        live = os.environ.get(known.name) or None
        stored = file_values.get(known.name)
        present = bool(live or stored)
        # "process": set by whoever started the server rather than by the file, or set
        # there with a different value. Saving from here still works, but the next start
        # may put the old value back, and deleting from here cannot unset it.
        source = None
        if present:
            source = "file" if stored is not None and live in (None, stored) else "process"
        default = default_value(known.check) if known.check else ""
        item: dict[str, Any] = {
            "name": known.name,
            "group": known.group,
            "secret": known.secret,
            "url": known.url,
            "present": present,
            "source": source,
            # Whether a check can run now: a value to check, or a default to fall back on.
            "checkable": known.check is not None and (present or bool(default)),
        }
        if not known.secret:
            item["value"] = live or stored or ""
            item["default"] = default
        if known.group == "telegram":
            item["agents"] = [
                p.id
                for p in rt.profiles()
                if p.telegram is not None and p.telegram.token_env == known.name
            ]
        items.append(item)
    return {"file": str(env_path(rt.settings.home)), "items": items}
