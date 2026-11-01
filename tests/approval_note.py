"""A tool result as the model reads it once a person approved the call."""

from __future__ import annotations

from my_agent_crew.texts_approval import APPROVED_NOTE, DECIDED_VIA


def approved_output(output: str, via: str = "") -> str:
    note = " ".join(APPROVED_NOTE.format(via=DECIDED_VIA.get(via, "")).split())
    return f"{output.rstrip()}\n\n{note}"
