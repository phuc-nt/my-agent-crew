"""What the agent is actually told, as reported to the screen that shows it.

The prompt is assembled fresh on every turn from files on disk, so a preview that
rebuilt it its own way would agree today and drift the first time a section is added.
These tests pin it to the turn's own builder, and pin the persona names an editor needs
to create a file that does not exist yet — the state every new agent starts in.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.agent.prompt import system_prompt_for, turn_messages
from my_agent_crew.config import load_settings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime_build import build_runtime


@pytest.fixture
def crew(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, runtime, home


def test_the_reported_prompt_is_the_one_a_turn_would_be_given(crew) -> None:
    """Not a lookalike: the same builder, so a new section cannot appear in one only."""
    client, runtime, _ = crew
    # The master reads its persona from the home root, which is its profile directory.
    client.put("/api/agents/default/files/AGENTS.md", json={"content": "Luôn trả lời ngắn."})

    reported = client.get("/api/agents/default/prompt").json()
    built = system_prompt_for(runtime.deps_for("default"))

    assert reported["prompt"] == built
    assert reported["chars"] == len(built)
    # And the persona really is carried, so this is not two empty strings agreeing.
    assert "Luôn trả lời ngắn." in reported["prompt"]


def test_the_preview_matches_what_the_loop_sends_for_a_real_conversation(crew) -> None:
    """The loop's own first message, compared against the preview for the same agent."""
    client, runtime, _ = crew
    client.put("/api/agents/default/files/SOUL.md", json={"content": "Giọng điệu điềm tĩnh."})
    deps = runtime.deps_for("default")
    conv = deps.store.create(agent_id="default", channel="", title="thử")

    sent = turn_messages(deps, deps.store.get(conv.id), [])[0].content
    preview = client.get("/api/agents/default/prompt").json()["prompt"]

    # A fresh conversation attaches no skills and has no previous session to summarise,
    # so the standing prompt and the turn's prompt are the same text.
    assert sent == preview


def test_an_agent_that_has_written_no_persona_still_offers_every_file_to_write(crew) -> None:
    """The chicken and egg: a form that lists only existing files can never make one."""
    client, _, _ = crew
    client.post("/api/agents", json={"agent_id": "fresh", "profile": {"name": "Mới"}})

    described = client.get("/api/agents/fresh").json()

    # Nothing on disk yet ...
    assert described["persona_files"] == []
    # ... but the editor is still told what it may create, and the read route serves an
    # unwritten file as empty rather than as an error, so the first line can be typed.
    assert "AGENTS.md" in described["persona_names"]
    blank = client.get("/api/agents/fresh/files/AGENTS.md")
    assert blank.status_code == 200
    assert blank.json()["content"] == ""


def test_writing_the_first_persona_file_shows_up_in_the_prompt(crew) -> None:
    """The whole point of the editor: what is typed reaches the model on the next turn."""
    client, _, _ = crew
    client.post("/api/agents", json={"agent_id": "fresh", "profile": {"name": "Mới"}})

    client.put("/api/agents/fresh/files/AGENTS.md", json={"content": "Chỉ nói tiếng Việt."})

    assert "Chỉ nói tiếng Việt." in client.get("/api/agents/fresh/prompt").json()["prompt"]
    # And it now counts as written, so the editor can mark it as having content.
    assert client.get("/api/agents/fresh").json()["persona_files"] == ["AGENTS.md"]


def test_the_prompt_of_an_unknown_agent_is_a_404_not_a_traceback(crew) -> None:
    client, _, _ = crew
    assert client.get("/api/agents/nobody/prompt").status_code == 404
