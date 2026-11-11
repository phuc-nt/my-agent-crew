"""Whether a page address is one the agent was handed or one it put together.

`fetch_url` reads and changes nothing, so it ran unasked. But an address is also a message:
an agent told by a page it read to open `https://elsewhere.example/?q=<what it knows>` has
sent what it knows. An address that stands word for word in what the conversation was handed
from outside the model says nothing new to the server that receives it, and runs as before.
One the model wrote itself stops for a person, unless its host is one of the agent's
`outbound_hosts`.

Handed from outside: what a person wrote (a job's prompt too) and what a search or a page
answered. Not what the shell, a file or another server's tool answered: the agent decides
what those say, and an address echoed through one is still its own. A turn another agent
asked for is told its task by a model, so its own first message does not count; what the
conversation above it was handed does."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from my_agent_crew import texts_outbound as t
from my_agent_crew.agent.turn_context import DELEGATE, turn_conversation_id
from my_agent_crew.browser.policy import host_allowed, host_of

if TYPE_CHECKING:
    from my_agent_crew.store import Store

# Tools whose answer is written by the web, not by the agent.
WEB_TOOLS = ("web_search", "fetch_url")
WEB_PREFIX = "browser_"
# How far up a chain of delegated turns the text is read.
MAX_PARENTS = 5
Seen = Callable[[], str]


def outside_text(store: Store, conv_id: str | None = None) -> str:
    """Everything the turn's conversation was handed from outside the model, and what the
    conversations that delegated it were. Nothing outside a turn."""
    parts: list[str] = []
    conv_id = turn_conversation_id() if conv_id is None else conv_id
    for _ in range(MAX_PARENTS):
        if not conv_id:
            break
        run = store.runs.latest_for_conversation(conv_id)
        source = run.source if run is not None else ""
        child = source.startswith(f"{DELEGATE}:")
        for stored in store.history(conv_id):
            message = stored.message
            name = message.name or ""
            if message.role == "user" and not child:
                parts.append(message.content)
            elif message.role == "tool" and (name in WEB_TOOLS or name.startswith(WEB_PREFIX)):
                parts.append(message.content)
        conv_id = source.split(":", 1)[1] if child else ""
    return "\n".join(parts)


def composed_reason(url: str, hosts: Sequence[str], seen: Seen | None) -> str | None:
    """Why this address stops for a person, or None. An address `fetch_url` refuses anyway
    asks nobody; one whose host cannot be read the one way a browser reads it is nobody's
    listed host."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None
    host = host_of(url)
    if host_allowed(host, hosts):
        return None
    handed = url.split("#", 1)[0].rstrip("/")
    if seen is not None and handed and handed in seen():
        return None
    return t.FETCH_COMPOSED.format(host=host or parts.hostname[:80])
