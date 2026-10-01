"""Each module the canvas note is built from imports first thing in a fresh interpreter, so no
import cycle hides behind the order the app happens to load them in. The store's part loads
nothing of the agent, which sits above the store, so the note names the web chat's turn source
itself and a test keeps that name the agent's own."""

from __future__ import annotations

import subprocess
import sys

import pytest

from my_agent_crew.agent.turn_context import CHAT
from my_agent_crew.store.canvas_note import WEB_CHAT

PROBE = """
import importlib
import sys
importlib.import_module({module!r})
print(sorted(n for n in sys.modules if n.split(".")[:2] == ["my_agent_crew", "agent"]))
"""
BELOW_THE_AGENT = [
    "my_agent_crew.store.canvas_note",
    "my_agent_crew.store.canvas_quote",
    "my_agent_crew.store.artifact_authors",
    "my_agent_crew.artifacts.diff",
]


@pytest.mark.parametrize(
    ("module", "below_the_agent"),
    [(module, True) for module in BELOW_THE_AGENT]
    + [("my_agent_crew.tools.artifact_scope", False)],
)
def test_each_part_of_the_note_imports_first_and_the_store_without_the_agent(
    module: str, below_the_agent: bool
):
    probe = PROBE.format(module=module)
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    if below_the_agent:
        assert result.stdout.strip() == "[]"


def test_the_note_names_the_turn_source_the_web_chat_runs_under():
    assert WEB_CHAT == CHAT
