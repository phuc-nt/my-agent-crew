"""A save and the file the next start reads (`agents/profile_read_back.py`,
`agents/profile_write.py`, `server/routes_agents_edit.py`).

The file is written by one library and read at the start by another. What the writer is kept
from is tried here through the door a person uses, and so is the look at the file before it
is written: a save the next start would read as anything but the edit is refused, and leaves
the file and the running crew as they were.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from ruamel.yaml import YAML

from my_agent_crew import texts
from my_agent_crew.agents import profile_write
from my_agent_crew.agents.profile_edit import apply_patch
from my_agent_crew.agents.profile_read_back import check_read_back
from my_agent_crew.agents.profile_write import read_raw
from my_agent_crew.config import load_settings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime_build import build_runtime

# A script a person wrote as a block, its lines indented with tabs. A block cannot carry a
# tab back, so a save writes the script in quotes, on one line longer than a line of a file.
TABBED = """\
name: Thợ mã
schedules:
  - id: due
    cron: "0 7 * * *"
    script: |
      rows = [1, 2, 3]
      limit = 0
      seen = 0
      total_{pad} = 0
      for amount in rows:
      \tif amount > limit and seen < 100 and total_{pad} < 1000 and len(rows) > limit:
      \t\ttotal_{pad} = total_{pad} + amount
      \t\tseen = seen + 1
      print(total_{pad}, seen)
    then_prompt: Viết lại cho gọn rồi nhắn
  - id: chao
    cron: "0 8 * * *"
    prompt: chào
"""
# To the reader the server starts with, `010` is eight and `no` a false. To the library a
# save reads and writes with, the one is ten and the other a text.
READ_TWO_WAYS = """\
name: Thợ mã
max_steps: 010
schedules:
  - id: chao
    cron: "0 8 * * *"
    prompt: chào
    enabled: no
"""


@pytest.fixture
def crew(tmp_path: Path):
    """An agent `coder` whose file a person wrote."""
    home = tmp_path / "home"
    manifest = home / "agents" / "coder" / "agent.yaml"
    manifest.parent.mkdir(parents=True)
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}

    def serve(written: str = "name: Thợ mã\n"):
        manifest.write_text(written, encoding="utf-8")
        runtime = build_runtime(load_settings(env=env))
        return TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1")

    return serve, manifest


def booted(manifest: Path) -> dict[str, Any]:
    """The file as the next start reads it."""
    return yaml.safe_load(manifest.read_text("utf-8"))


def declared(client: TestClient) -> list[dict[str, Any]]:
    """The agent's rows as the editor shows them and sends them back: no key a row lacks."""
    rows = client.get("/api/agents/coder").json()["declared"]["schedules"]
    return [{key: value for key, value in row.items() if value is not None} for row in rows]


def switching_off_the_other_row(client: TestClient):
    """The save of a person who touched one row: the editor sends the whole list."""
    due, hello = declared(client)
    rows = [due, {**hello, "enabled": False}]
    return client.patch("/api/agents/coder", json={"profile": {"schedules": rows}})


def test_a_script_indented_with_tabs_is_still_that_script_after_a_save_of_another_row(crew):
    """Folded where a line of the file would end, the quoted script was read back with a
    space it never had. The save had answered that it worked, and the next start refused
    the file: `unexpected indent`. Where the fold falls goes by the length of every name
    before it, so the script is tried at each."""
    serve, manifest = crew
    for pad in range(40):
        with serve(TABBED.format(pad="x" * pad)) as client:
            script = booted(manifest)["schedules"][0]["script"]
            assert "\n\tif amount" in script

            reply = switching_off_the_other_row(client)

        assert reply.status_code == 200, (pad, reply.json())
        due, hello = booted(manifest)["schedules"]
        assert (due["script"], hello["enabled"]) == (script, False), pad
        with serve(manifest.read_text("utf-8")) as client:
            assert declared(client)[0]["script"] == script


def test_words_the_start_reads_as_no_text_are_saved_as_the_words(crew):
    """A row whose prompt is `No` stood in the file as a false, and a row with no text for a
    prompt is a file the server does not start with."""
    serve, manifest = crew
    script = {"id": "due", "cron": "0 7 * * *", "script": 'print("x")\n', "then_prompt": "No"}
    told = {"id": "chao", "cron": "0 8 * * *", "prompt": "1:30"}
    with serve() as client:
        reply = client.patch("/api/agents/coder", json={"profile": {"schedules": [script, told]}})

    assert reply.status_code == 200, reply.json()
    due, hello = booted(manifest)["schedules"]
    assert (due["then_prompt"], hello["prompt"]) == ("No", "1:30")
    with serve(manifest.read_text("utf-8")) as client:
        assert [row.get("then_prompt") or row["prompt"] for row in declared(client)] == [
            "No",
            "1:30",
        ]


def test_a_save_the_next_start_would_read_otherwise_is_refused_and_changes_nothing(
    crew, monkeypatch
):
    """The writer folding its lines again stands for whatever the two libraries next come
    to disagree about. No save answers that it worked and leaves another script behind."""
    serve, manifest = crew
    monkeypatch.setattr(profile_write, "NEVER_FOLDED", 80)
    refused = []
    for pad in range(40):
        written = TABBED.format(pad="x" * pad)
        with serve(written) as client:
            script = booted(manifest)["schedules"][0]["script"]

            reply = switching_off_the_other_row(client)

            if reply.status_code == 200:
                assert booted(manifest)["schedules"][0]["script"] == script, pad
                continue
            refused.append(pad)
            said = texts.SAVE_READS_BACK_CHANGED.format(what="schedules")
            assert (reply.status_code, reply.json()["detail"]) == (422, said)
            assert manifest.read_text("utf-8") == written
            assert [row["enabled"] for row in declared(client)] == [True, True]

    assert refused


def test_what_a_person_wrote_that_the_two_libraries_read_differently_holds_up_no_save(crew):
    """Both sides of the look are read by the start's own reader. Measured against what the
    save's library made of the file, every save of this agent would be refused for a line
    the edit never touched."""
    serve, manifest = crew
    with serve(READ_TWO_WAYS) as client:
        reply = client.patch("/api/agents/coder", json={"profile": {"description": "Viết mã"}})

    assert reply.status_code == 200, reply.json()
    after = booted(manifest)
    assert (after["max_steps"], after["schedules"][0]["enabled"]) == (8, False)
    assert after["description"] == "Viết mã"


# --- the look itself ---


def edited(manifest: Path, patch: dict[str, Any]) -> Any:
    return apply_patch(read_raw(manifest), patch)


def test_the_file_to_be_is_the_file_as_it_stands_with_the_edits_keys_set(tmp_path):
    manifest = tmp_path / "agent.yaml"
    manifest.write_text("name: A\ndescription: cũ\nmax_steps: 010\n", encoding="utf-8")

    for patch in ({"description": "mới"}, {"description": None}, {"tools": ["a"]}, {}):
        check_read_back(manifest, edited(manifest, patch), patch)


def test_a_new_agents_file_is_the_edit_and_nothing_else(tmp_path):
    absent = tmp_path / "agent.yaml"
    patch = {"name": "Mới", "description": None}

    check_read_back(absent, edited(absent, patch), patch)
    with pytest.raises(ValueError, match="name"):
        check_read_back(absent, edited(absent, {"name": "Khác"}), patch)


def test_every_key_that_would_read_back_otherwise_is_named(tmp_path):
    """A key the edit set, one it did not, one that is gone and one nobody asked for."""
    manifest = tmp_path / "agent.yaml"
    manifest.write_text("name: A\nmax_steps: 5\ntools: [a]\n", encoding="utf-8")
    patch = {"description": "mới"}
    raw = edited(manifest, patch)
    raw["description"] = "khác"
    raw["name"] = "B"
    raw["workspace"] = "khac"
    del raw["max_steps"]

    with pytest.raises(ValueError) as refused:
        check_read_back(manifest, raw, patch)

    what = "description, max_steps, name, workspace"
    assert str(refused.value) == texts.SAVE_READS_BACK_CHANGED.format(what=what)


def test_a_file_the_start_could_not_read_is_the_persons_to_mend(tmp_path):
    """The library a save reads with takes a tag it does not know; the start's does not."""
    manifest = tmp_path / "agent.yaml"
    manifest.write_text("name: !mine A\n", encoding="utf-8")

    with pytest.raises(ValueError) as refused:
        check_read_back(manifest, edited(manifest, {"description": "x"}), {"description": "x"})

    assert str(refused.value).startswith(texts.MANIFEST_BROKEN.format(error=""))


def test_a_file_to_be_that_the_start_could_not_read_is_not_written(tmp_path):
    raw = YAML().load("name: !mine A\n")

    with pytest.raises(ValueError) as refused:
        check_read_back(tmp_path / "agent.yaml", raw, {})

    opening = texts.SAVE_READS_BACK_CHANGED.partition("{what}")[0]
    assert str(refused.value).startswith(opening) and "!mine" in str(refused.value)
