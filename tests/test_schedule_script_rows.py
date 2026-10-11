"""A schedule row that runs a script: the keys `script` and `then_prompt`.

One reading serves the file at boot and a save from the web (`agents/profile_yaml.py`), so a
row is refused by both or by neither. A row does exactly one of three things, the prompt a
script's output goes on with stands only beside a script, and a script that could not be
read is turned away when it is written, not each morning its job comes round. The web editor
shows a script and never edits one: it sends the row back as it read it, and the file must
then hold the script it held, to the character. What such a job does when it is due is in
`test_script_job.py`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from my_agent_crew.config import Settings, load_settings
from my_agent_crew.script.check import parse
from my_agent_crew.script.limits import MAX_SOURCE_CHARS, ScriptError
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime_build import build_runtime
from tests.test_approval_ttl import parsed_schedule
from tests.test_profile_write_blocks import is_block

ROOT = Path(__file__).resolve().parents[1]
TIMED = {"id": "due", "cron": "0 7 * * *"}
# Indented, with a line that ends on a space and a last line that ends: a script is read by
# its white space, and a writer that tidied any of it would hand back another script.
SCRIPT = 'due = load("due") or []\nfor item in due: \n    print("hạn:", item)\n'
THEN = "Viết lại cho gọn:\nrồi nhắn"
ONE_OF = "schedule needs exactly one of prompt / command / script"
ONLY_BESIDE = "schedule takes then_prompt only beside script"


def refused(raw: dict[str, Any], settings: Settings, tmp_path: Path) -> str:
    with pytest.raises(ValueError) as caught:
        parsed_schedule({**TIMED, **raw}, settings, tmp_path)
    return str(caught.value)


# --- as the file is read ---


@pytest.mark.parametrize("unused", [{}, {"prompt": "", "command": ""}])
def test_a_row_with_a_script_is_a_script_job_and_takes_no_other_action(settings, tmp_path, unused):
    """A blank a form sent for an action the row does not take is no action, and not kept."""
    raw = {**TIMED, "script": SCRIPT, "then_prompt": THEN, **unused}

    schedule = parsed_schedule(raw, settings, tmp_path)

    assert (schedule.kind, schedule.script, schedule.then_prompt) == ("script", SCRIPT, THEN)
    assert (schedule.prompt, schedule.command) == (None, None)
    row = schedule.to_dict()
    assert (row["kind"], row["script"], row["then_prompt"]) == ("script", SCRIPT, THEN)
    assert (row["prompt"], row["command"]) == (None, None)


@pytest.mark.parametrize("unset", [{}, {"then_prompt": None}])
def test_a_script_needs_no_prompt_to_go_on_with(settings, tmp_path, unset):
    schedule = parsed_schedule({**TIMED, "script": SCRIPT, **unset}, settings, tmp_path)

    assert (schedule.kind, schedule.then_prompt) == ("script", None)


@pytest.mark.parametrize(
    ("action", "kind"), [({"prompt": "chào"}, "prompt"), ({"command": "/compact"}, "command")]
)
def test_a_row_that_runs_no_script_still_says_so(settings, tmp_path, action, kind):
    """Both keys, empty: the editor tells a script row by them, and so must find them."""
    blank = {"script": "", "then_prompt": None}  # as a form sends what it does not use

    for raw in (action, {**action, **blank}):
        row = parsed_schedule({**TIMED, **raw}, settings, tmp_path).to_dict()

        assert (row["kind"], row["script"], row["then_prompt"]) == (kind, None, None)


NOT_ONE = [
    {},
    {"script": ""},
    {"prompt": "", "command": None, "script": None},
    {"prompt": "chào", "command": "/compact"},
    {"prompt": "chào", "script": SCRIPT},
    {"command": "/compact", "script": SCRIPT},
    {"prompt": "chào", "command": "/compact", "script": SCRIPT},
]


@pytest.mark.parametrize("actions", NOT_ONE)
def test_a_row_does_one_of_three_things_and_never_none_or_two(settings, tmp_path, actions):
    assert refused(actions, settings, tmp_path) == f"agent a: {ONE_OF}"


@pytest.mark.parametrize(
    "row",
    [
        {"prompt": "chào", "then_prompt": THEN},
        {"command": "/compact", "then_prompt": THEN},
        # Blank is still a key the row has no use for: only absent or null is "none".
        {"prompt": "chào", "then_prompt": ""},
    ],
)
def test_the_prompt_a_scripts_output_goes_on_with_stands_only_beside_a_script(
    settings, tmp_path, row
):
    assert refused(row, settings, tmp_path) == f"agent a: {ONLY_BESIDE}"


@pytest.mark.parametrize("then_prompt", ["", "  \n", 5, ["Viết lại"]])
def test_a_prompt_to_go_on_with_is_words_or_is_not_there(settings, tmp_path, then_prompt):
    said = refused({"script": SCRIPT, "then_prompt": then_prompt}, settings, tmp_path)

    assert said == "agent a: schedule due: then_prompt must be a non-empty string"


@pytest.mark.parametrize("script", ["  \n\t", 5, True, ['print("a")']])
def test_a_script_is_text_with_something_in_it(settings, tmp_path, script):
    said = refused({"script": script}, settings, tmp_path)

    assert said == "agent a: schedule due: script must be a non-empty string"


def test_a_script_is_as_long_as_a_turns_script_may_be_and_no_longer(settings, tmp_path):
    fits = "x = 1  #" + "x" * (MAX_SOURCE_CHARS - len("x = 1  #"))

    assert parsed_schedule({**TIMED, "script": fits}, settings, tmp_path).script == fits
    said = refused({"script": fits + "x"}, settings, tmp_path)
    assert said == f"agent a: schedule due: script is longer than {MAX_SOURCE_CHARS} characters"


@pytest.mark.parametrize("script", ['print("chưa đóng"', "import os\nprint(os.getcwd())"])
def test_a_script_that_could_not_be_run_is_refused_with_the_checks_own_words(
    settings, tmp_path, script
):
    """What a turn's script is told before it runs, here told to whoever wrote the file."""
    with pytest.raises(ScriptError) as checked:
        parse(script)

    said = refused({"script": script}, settings, tmp_path)

    assert said == f"agent a: schedule due: script: {checked.value}"


def test_a_row_without_an_id_is_named_by_its_place(settings, tmp_path):
    with pytest.raises(ValueError) as caught:
        parsed_schedule({"cron": "0 7 * * *", "script": " "}, settings, tmp_path)

    assert str(caught.value) == "agent a: schedule job-0: script must be a non-empty string"


def test_the_web_fakes_refuse_a_row_in_the_servers_own_words():
    """The editor's tests check what a person is shown against these two sentences
    (web/src/test/schedule-contract.ts). Reworded on one side only, they would go on
    checking words the server no longer says."""
    contract = (ROOT / "web" / "src" / "test" / "schedule-contract.ts").read_text("utf-8")

    said = set(re.findall(r'return \{ error: "([^"]+)" \};', contract))

    assert {ONE_OF, ONLY_BESIDE} <= said


# --- as the web saves it ---


@pytest.fixture
def crew(tmp_path: Path):
    """An agent `coder` whose file a person wrote, with a script job in it."""
    home = tmp_path / "home"
    manifest = home / "agents" / "coder" / "agent.yaml"
    manifest.parent.mkdir(parents=True)
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}

    def serve(written: str = "name: Thợ mã\n"):
        manifest.write_text(written, encoding="utf-8")
        runtime = build_runtime(load_settings(env=env))
        return TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1")

    return serve, manifest


def in_file(manifest: Path) -> list[dict[str, Any]]:
    """The rows as the next boot reads them."""
    return yaml.safe_load(manifest.read_text("utf-8")).get("schedules") or []


def saving(client: TestClient, *rows: dict[str, Any]):
    return client.patch("/api/agents/coder", json={"profile": {"schedules": list(rows)}})


def as_the_editor_sends(row: dict[str, Any]) -> dict[str, Any]:
    """`sendableRow` in web/src/hooks/schedule-row-shape.ts: no key a row does not use."""
    return {key: value for key, value in row.items() if value is not None}


BAD_ROWS = [
    ({"prompt": "chào", "script": SCRIPT}, f"agent coder: {ONE_OF}"),
    ({}, f"agent coder: {ONE_OF}"),
    ({"prompt": "chào", "then_prompt": THEN}, f"agent coder: {ONLY_BESIDE}"),
    (
        {"script": SCRIPT, "then_prompt": ""},
        "agent coder: schedule due: then_prompt must be a non-empty string",
    ),
    ({"script": " \n"}, "agent coder: schedule due: script must be a non-empty string"),
    (
        {"script": "x = 1  #" + "x" * MAX_SOURCE_CHARS},
        f"agent coder: schedule due: script is longer than {MAX_SOURCE_CHARS} characters",
    ),
]


@pytest.mark.parametrize(("row", "said"), BAD_ROWS)
def test_a_row_the_file_would_be_refused_for_is_refused_before_it_is_written(crew, row, said):
    serve, manifest = crew
    with serve() as client:
        reply = saving(client, {**TIMED, **row})

        assert (reply.status_code, reply.json()["detail"]) == (422, said)
        assert in_file(manifest) == []
        assert client.get("/api/agents/coder").json()["declared"]["schedules"] == []


def test_a_saved_script_that_could_not_be_run_is_refused_before_it_is_written(crew):
    serve, manifest = crew
    with serve() as client:
        reply = saving(client, {**TIMED, "script": "import os"})

        assert reply.status_code == 422
        assert reply.json()["detail"].startswith("agent coder: schedule due: script: ")
        assert in_file(manifest) == []


@pytest.mark.parametrize("then_prompt", [THEN, None])
def test_a_script_row_sent_back_as_it_was_read_is_written_as_it_was(crew, then_prompt):
    serve, manifest = crew
    row = {**TIMED, "name": "Nhắc hạn", "script": SCRIPT}
    row |= {"then_prompt": then_prompt} if then_prompt else {}
    with serve() as client:
        assert saving(client, row).status_code == 200
        [declared] = client.get("/api/agents/coder").json()["declared"]["schedules"]
        # Read: the script whole, and nothing where a script row has nothing.
        assert (declared["script"], declared["then_prompt"]) == (SCRIPT, then_prompt)
        assert (declared["prompt"], declared["command"]) == (None, None)

        # The whole row as it was read, nulls and all, and the row as the editor trims it.
        for sent in (declared, as_the_editor_sends(declared)):
            reply = saving(client, sent)

            assert reply.status_code == 200, reply.json()
            [written] = in_file(manifest)
            assert written["script"] == SCRIPT and written.get("then_prompt") == then_prompt
            assert not written.get("prompt") and not written.get("command")
            assert reply.json()["profile"]["declared"]["schedules"] == [declared]


def test_a_saved_script_stands_in_the_file_as_its_lines(crew):
    """A person opens the file to read the job, and one line with `\\n` in it is no script
    to read. The same for the words a job's turn opens with."""
    serve, manifest = crew
    told = {"id": "chao", "cron": "0 8 * * *", "prompt": "Chào buổi sáng.\nNhắc việc hôm nay.\n"}
    with serve() as client:
        reply = saving(client, {**TIMED, "script": SCRIPT, "then_prompt": THEN}, told)

    assert reply.status_code == 200, reply.json()
    assert all(is_block(manifest, key) for key in ("script", "then_prompt", "prompt"))
    due, hello = in_file(manifest)
    assert (due["script"], due["then_prompt"], hello["prompt"]) == (SCRIPT, THEN, told["prompt"])


HAND_WRITTEN = """\
name: Thợ mã
schedules:
  - id: due
    cron: "0 7 * * *"
    script: |
      due = load("due") or []
      for item in due:
          print("hạn:", item)
    then_prompt: Viết lại cho gọn rồi nhắn
  - id: chao
    cron: "0 8 * * *"
    prompt: chào
"""
WRITTEN_BY_HAND = 'due = load("due") or []\nfor item in due:\n    print("hạn:", item)\n'


def test_a_script_a_person_wrote_in_the_file_is_still_that_script_after_a_save(crew):
    """The save is of another row: the editor sends the whole list, the script's row as it
    read it."""
    serve, manifest = crew
    with serve(HAND_WRITTEN) as client:
        assert in_file(manifest)[0]["script"] == WRITTEN_BY_HAND
        due, hello = client.get("/api/agents/coder").json()["declared"]["schedules"]
        assert (due["script"], due["then_prompt"]) == (WRITTEN_BY_HAND, "Viết lại cho gọn rồi nhắn")

        reply = saving(
            client, as_the_editor_sends(due), {**as_the_editor_sends(hello), "cron": "0 9 * * *"}
        )

        assert reply.status_code == 200, reply.json()
        assert is_block(manifest, "script")
        written, moved = in_file(manifest)
        assert (written["script"], written["then_prompt"]) == (
            WRITTEN_BY_HAND,
            "Viết lại cho gọn rồi nhắn",
        )
        assert (moved["prompt"], moved["cron"]) == ("chào", "0 9 * * *")


def test_the_jobs_list_tells_a_script_job_by_its_script(crew):
    """As a command job's row carries its command: the page needs no second question."""
    serve, _ = crew
    with serve(HAND_WRITTEN) as client:
        due, hello = client.get("/api/jobs").json()

    assert (due["id"], due["kind"], due["schedule_id"]) == ("coder/due", "script", "due")
    assert (due["script"], due["then_prompt"]) == (WRITTEN_BY_HAND, "Viết lại cho gọn rồi nhắn")
    assert (due["prompt"], due["command"]) == (None, None)
    # Every row has both keys, so the page reads them without asking what kind it is.
    assert (hello["kind"], hello["script"], hello["then_prompt"]) == ("prompt", None, None)
    assert set(due) == set(hello)
