"""The web app stops a save the server would refuse, and stops a message the chat route would
refuse, from two numbers it keeps in `web/src/lib/canvas-caps.ts`. Nothing at runtime reads both
sides, so this is what notices one changing alone."""

from __future__ import annotations

import re
from pathlib import Path

from my_agent_crew.artifacts.kinds import KB, KINDS, MB, cap_bytes
from my_agent_crew.server.routes_chat import ChatBody

SOURCE = Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "canvas-caps.ts"
ENTRY = re.compile(r"^  (\w+): (\d+) \* (KB|MB),$", re.MULTILINE)
UNITS = {"KB": KB, "MB": MB}


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_the_web_holds_every_kind_to_the_cap_the_server_holds_it_to():
    web = {kind: int(count) * UNITS[unit] for kind, count, unit in ENTRY.findall(_source())}
    assert web == {kind: cap_bytes(kind) for kind in KINDS}


def test_the_web_message_limit_is_the_one_the_chat_route_takes():
    found = re.search(r"^export const MESSAGE_MAX = (\d+);$", _source(), re.MULTILINE)
    assert found is not None
    limits = [
        m.max_length for m in ChatBody.model_fields["text"].metadata if hasattr(m, "max_length")
    ]
    assert limits == [int(found.group(1))]
