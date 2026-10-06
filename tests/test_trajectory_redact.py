"""Secrets in an exported run are covered, and the export is a file download that says
where it came from — never the process environment itself."""

import json
import os
from dataclasses import asdict, replace

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.activity.redact import MIN_SECRET_CHARS, env_secrets, redact
from my_agent_crew.activity.step_previews import argument_preview, preview
from my_agent_crew.activity.trajectory import RESULT_LIMIT
from my_agent_crew.config import Route
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.script.tool import SCRIPT_TOOL
from my_agent_crew.server import create_app
from my_agent_crew.store.db import now_iso
from my_agent_crew.store.runs import DONE, RunRecord
from my_agent_crew.texts import TRAJECTORY_REDACTED
from my_agent_crew.tools.result import NestedCall
from tests.trajectory_fake import delegating_turn

FAKE_KEY = "sk-or-v1-" + "0123456789abcdef" * 4
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
# Letters no id, stamp or label holds, so any run of them left in a file is the secret's.
PLANTED = "planted-secret-" + "klmnopqrstuvwxyz" * 4
QUOTED = 'quoted"and\\slashed-planted-value'


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


def test_each_form_a_runs_record_can_hold_a_secret_in_is_gathered():
    """A preview collapses whitespace; a mapping argument is kept as JSON, which escapes
    quotes and backslashes; one inside a preview is both."""
    value = 'pass  "word"\\x'

    assert set(env_secrets({"DB_PASSWORD": value})) == {
        value,
        'pass "word"\\x',
        'pass  \\"word\\"\\\\x',
        'pass \\"word\\"\\\\x',
    }


def test_the_head_or_the_tail_a_cut_left_of_a_secret_is_covered():
    secrets = env_secrets({"PLANTED_API_KEY": PLANTED})
    covered = TRAJECTORY_REDACTED

    assert redact("cắt ở " + PLANTED[:20], secrets) == f"cắt ở {covered}"
    assert redact(f"xem {PLANTED[:12]}… rồi tiếp", secrets) == f"xem {covered}… rồi tiếp"
    assert redact(PLANTED[-12:] + " là phần cuối", secrets) == f"{covered} là phần cuối"


@pytest.mark.parametrize(
    "text",
    [
        "Đang tải… xong rồi…",
        "planted-secret là tên một biến, không phải khoá",
        "…và câu này kết thúc bằng stuvwxyz",
    ],
)
def test_text_that_only_shares_a_start_or_an_end_with_a_secret_is_left_alone(text: str):
    assert redact(text, env_secrets({"PLANTED_API_KEY": PLANTED})) == text


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


def pieces(secret: str) -> set[str]:
    """Every run of characters of the secret long enough to be covered."""
    width = MIN_SECRET_CHARS
    return {secret[at : at + width] for at in range(len(secret) - width + 1)}


def test_a_secret_cut_short_anywhere_in_a_runs_record_is_covered_in_both(client, monkeypatch):
    """The record keeps previews, not whole texts: a title cut to fit a row, a summary kept
    from the end of an output, outputs and arguments cut with an ellipsis. Each can hold a
    head or a tail of a secret that the whole value no longer matches."""
    c, store = client
    monkeypatch.setenv("TRAJECTORY_TEST_API_KEY", PLANTED)
    conv = store.create()
    step = {
        "kind": "tool",
        "name": "shell_run",
        "ok": True,
        "arguments": argument_preview({"command": "echo " + "x" * 140 + PLANTED, PLANTED: "v"}),
        "output": preview("in ra " + "y" * 140 + PLANTED),
        "duration_ms": 3,
    }
    run = RunRecord(
        "r1",
        "default",
        conv.id,
        "chat",
        ("Xem " + PLANTED)[:60],
        DONE,
        now_iso(),
        steps=[step],
        summary=("in " + PLANTED + " rồi dừng")[-40:],
        after_seq=0,
    )
    store.runs.save(run)
    call = ToolCall("t1", "shell_run", {"command": f"echo {PLANTED}", PLANTED: "v"})
    store.append(conv.id, Message(role="assistant", tool_calls=(call,)), "fake", "echo")
    delegating_turn(store, conv.id, "call_0", "đọc khoá", f"Khoá là {PLANTED}")

    as_json, as_md = download(c, "r1"), download(c, "r1", format="md")

    assert len(as_json.json()["children"]) == 1
    for body in (as_json.text, as_md.text):
        assert not [piece for piece in pieces(PLANTED) if piece in body]
        assert TRAJECTORY_REDACTED in body


def test_a_secret_in_what_a_script_called_is_covered_with_the_rest_of_the_record(
    client, monkeypatch
):
    """A script's own calls are kept on its step, each with a preview of what it was called
    with and of what came back. No message holds them, so the step is the one place an
    export has them from."""
    c, store = client
    monkeypatch.setenv("TRAJECTORY_TEST_API_KEY", PLANTED)
    conv = store.create()
    cut = NestedCall(
        "workspace_read",
        argument_preview({"path": "notes/" + "x" * 140 + PLANTED, PLANTED: "v"}),
        True,
        preview("khoá: " + "y" * 140 + PLANTED),
        3,
    )
    whole = replace(cut, arguments={"path": "khoa.txt"}, output=f"khoá là {PLANTED}")
    step = {"kind": "tool", "name": SCRIPT_TOOL, "ok": True, "output": "xong", "duration_ms": 9}
    step["calls"] = [asdict(cut), asdict(whole)]
    run = RunRecord("r3", "default", conv.id, "chat", "Đọc", DONE, now_iso(), steps=[step])
    run.after_seq = 0
    store.runs.save(run)

    as_json, as_md = download(c, "r3"), download(c, "r3", format="md")

    [exported] = as_json.json()["run"]["steps"]
    assert [call["name"] for call in exported["calls"]] == ["workspace_read", "workspace_read"]
    assert exported["calls"][1] == {**asdict(whole), "output": f"khoá là {TRAJECTORY_REDACTED}"}
    for body in (as_json.text, as_md.text):
        assert not [piece for piece in pieces(PLANTED) if piece in body]
        assert "workspace_read" in body and TRAJECTORY_REDACTED in body


def test_a_secret_with_quotes_or_backslashes_is_covered_where_json_escaped_it(client, monkeypatch):
    c, store = client
    monkeypatch.setenv("TRAJECTORY_TEST_PASSWORD", QUOTED)
    conv = store.create()
    arguments = {
        "note": QUOTED,
        "payload": {"password": QUOTED},
        # Cut by the preview partway through the escaped secret.
        "long": {"pad": "z" * 121, "password": QUOTED},
    }
    step = {"kind": "tool", "name": "http_post", "ok": True, "duration_ms": 1}
    step["arguments"] = argument_preview(arguments)
    run = RunRecord("r2", "default", conv.id, "chat", "Gửi", DONE, now_iso(), steps=[step])
    run.after_seq = 0
    store.runs.save(run)
    body = json.dumps({"password": QUOTED})
    call = ToolCall("t1", "http_post", {"body": body})
    store.append(conv.id, Message(role="assistant", tool_calls=(call,)), "fake", "echo")

    for text in (download(c, "r2").text, download(c, "r2", format="md").text):
        # Every form the secret is left in, and every head of it, starts with this.
        assert "quoted" not in text
        assert TRAJECTORY_REDACTED in text
