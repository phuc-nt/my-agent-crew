"""`--no-schedule` starts a server that runs no jobs and opens no channels."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from my_agent_crew import __main__ as entry


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch, tmp_path) -> dict[str, object]:
    seen: dict[str, object] = {}
    monkeypatch.setenv("MY_AGENT_HOME", str(tmp_path))
    monkeypatch.setattr(entry, "build_runtime", lambda settings: SimpleNamespace(agents={}))

    def create_app(runtime: object, schedule: bool = True) -> object:
        seen["schedule"] = schedule
        return object()

    def run(app: object, **kwargs: object) -> None:
        seen["port"] = kwargs["port"]

    monkeypatch.setattr(entry, "create_app", create_app)
    monkeypatch.setattr(entry.uvicorn, "run", run)
    return seen


def start(monkeypatch: pytest.MonkeyPatch, *flags: str) -> None:
    monkeypatch.setattr(sys, "argv", ["my-agent-crew", *flags])
    assert entry.main() == 0


def test_a_plain_start_keeps_the_scheduler_and_the_channels_on(served, monkeypatch):
    start(monkeypatch)

    assert served == {"schedule": True, "port": 8765}


def test_no_schedule_turns_both_off(served, monkeypatch):
    start(monkeypatch, "--no-schedule")

    assert served == {"schedule": False, "port": 8765}


def test_no_schedule_leaves_the_port_flag_alone(served, monkeypatch):
    start(monkeypatch, "--port", "8798", "--no-schedule")

    assert served == {"schedule": False, "port": 8798}
