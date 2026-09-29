"""Secrets in an exported run are covered, and the export is a file download that says
where it came from — never the process environment itself."""

import json
import os

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.activity.redact import env_secrets, redact
from my_agent_crew.activity.trajectory import RESULT_LIMIT
from my_agent_crew.config import Route
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.server import create_app
from my_agent_crew.store.db import now_iso
from my_agent_crew.store.runs import DONE, RunRecord
from my_agent_crew.texts import TRAJECTORY_REDACTED

FAKE_KEY = "sk-or-v1-" + "0123456789abcdef" * 4
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"


def test_only_long_values_of_variables_named_as_secrets_are_gathered():
    environ = {
        "OPENROUTER_API_KEY": "abc123456789",
        "db_password": "hunter2hunter2",
        "SHORT_TOKEN": "abc",
        "HOME": "/Users/someone",
    }

    assert env_secrets(environ) == ["hunter2hunter2", "abc123456789"]


def test_a_secret_that_contains_another_is_covered_whole():
    secrets = env_secrets({"A_KEY": "abcdefgh", "B_KEY": "abcdefgh1234"})

    assert redact("x abcdefgh1234 y abcdefgh", secrets) == (
        f"x {TRAJECTORY_REDACTED} y {TRAJECTORY_REDACTED}"
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"key={FAKE_KEY}", f"key={TRAJECTORY_REDACTED}"),
        ("Authorization: Bearer abc.def-ghi_jkl", f"Authorization: Bearer {TRAJECTORY_REDACTED}"),
        (f"token {JWT} end", f"token {TRAJECTORY_REDACTED} end"),
    ],
)
def test_common_key_shapes_are_covered_without_knowing_the_value(text: str, expected: str):
    assert redact(text, []) == expected


@pytest.mark.parametrize(
    "text", ["task-management-system-for-all", "ask-me-anything-anytime", "the bearer of news"]
)
def test_words_that_only_look_a_little_like_keys_are_left_alone(text: str):
    assert redact(text, []) == text


@pytest.fixture
def client(deps_factory):
    deps = deps_factory(routes=(Route("fake", "echo"),))
    with TestClient(create_app(deps), base_url="http://127.0.0.1") as c:
        yield c, deps.store


def exported_run(store, tool_result: str) -> str:
    conv = store.create()
    run = RunRecord("r1", "default", conv.id, "chat", "Đọc cấu hình", DONE, now_iso(), after_seq=0)
    store.runs.save(run)
    store.append(conv.id, Message(role="user", content="đọc cấu hình"))
    call = ToolCall("t1", "shell_run", {"command": "cat config"})
    store.append(conv.id, Message(role="assistant", tool_calls=(call,)), "fake", "echo")
    store.append(
        conv.id, Message(role="tool", content=tool_result, tool_call_id="t1", name="shell_run")
    )
    store.append(conv.id, Message(role="assistant", content="Xong."), "fake", "echo")
    return run.id


def download(c: TestClient, run_id: str, **params: str):
    return c.get(f"/api/activity/runs/{run_id}/trajectory", params=params)


def test_a_missing_run_is_not_found(client):
    c, _ = client

    assert download(c, "nope").status_code == 404
    assert download(c, "nope", format="md").status_code == 404


def test_both_formats_come_as_files_to_save(client):
    c, store = client
    run_id = exported_run(store, "ok")

    as_json, as_md = download(c, run_id), download(c, run_id, format="md")

    assert as_json.headers["content-type"] == "application/json"
    assert as_json.headers["content-disposition"] == f'attachment; filename="run-{run_id}.json"'
    assert as_json.json()["run"]["id"] == run_id
    assert as_md.headers["content-type"] == "text/markdown; charset=utf-8"
    assert as_md.headers["content-disposition"] == f'attachment; filename="run-{run_id}.md"'
    assert "shell_run" in as_md.text
    assert as_json.headers["cache-control"] == as_md.headers["cache-control"] == "no-store"


def test_a_secret_from_the_environment_and_a_key_shaped_string_are_covered_in_both(
    client, monkeypatch
):
    c, store = client
    secret = "value-that-must-not-leak-1234"
    monkeypatch.setenv("TRAJECTORY_TEST_API_KEY", secret)
    run_id = exported_run(store, f"API_KEY={secret}\nOPENROUTER={FAKE_KEY}")

    for body in (download(c, run_id).text, download(c, run_id, format="md").text):
        assert secret not in body and FAKE_KEY not in body
        assert body.count(TRAJECTORY_REDACTED) >= 2


def test_a_secret_where_a_long_result_is_cut_is_covered_before_the_cut(client, monkeypatch):
    """Cutting first would keep the secret's head in the file, where no net can see it."""
    c, store = client
    secret = "value-that-must-not-leak-1234"
    monkeypatch.setenv("TRAJECTORY_TEST_API_KEY", secret)
    run_id = exported_run(store, "a" * (RESULT_LIMIT - 10) + secret + "b" * 3000)

    for body in (download(c, run_id).text, download(c, run_id, format="md").text):
        assert secret[:10] not in body


def test_nothing_from_the_environment_comes_along_unless_a_message_held_it(client, monkeypatch):
    c, store = client
    monkeypatch.setenv("TRAJECTORY_UNRELATED_SETTING", "distinct-value-4242-abc")
    run_id = exported_run(store, "ok")

    bodies = download(c, run_id).text + download(c, run_id, format="md").text

    for name, value in os.environ.items():
        if len(name) >= 6:
            assert name not in bodies
        if len(value) >= 12:
            assert value not in bodies


def test_the_full_export_keeps_a_long_result_whole(client):
    c, store = client
    run_id = exported_run(store, "z" * 4500)

    def result(**params: str) -> str:
        return json.loads(download(c, run_id, **params).text)["messages"][2]["content"]

    assert len(result()) < 4500 and result(full="1") == "z" * 4500
