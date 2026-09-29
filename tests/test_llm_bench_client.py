"""The client the bench and the behaviour evals share: how a turn follows its approvals, and
what a server it starts is given."""

from __future__ import annotations

from pathlib import Path

from llm_bench_client import Api
from llm_bench_server import Server

from tests.http_fake import FakeServer, as_json, question, say, sse, tool_approval

MESSAGES = "/api/conversations/c1/messages"


def api_over(server: FakeServer, **kwargs) -> Api:
    return Api("http://test/api", 5.0, transport=server.transport, **kwargs)


def test_a_turn_approves_every_tool_it_is_stopped_on_and_counts_them():
    server = (
        FakeServer()
        .on(MESSAGES, sse(tool_approval("a1", command="ls")))
        .on("/api/conversations/c1/approvals/a1", sse(tool_approval("a2", command="pwd")))
        .on("/api/conversations/c1/approvals/a2", sse(say("done")))
    )

    turn = api_over(server).turn("c1", "hi")

    assert server.body_of("/api/conversations/c1/approvals/a1") == {"approve": True}
    assert server.body_of("/api/conversations/c1/approvals/a2") == {"approve": True}
    assert (turn.approvals, turn.answer, turn.error) == (2, "done", "")


def test_a_question_to_the_person_ends_the_turn_as_a_failure_nothing_answers_it():
    server = FakeServer().on(MESSAGES, sse(question("q1")))

    turn = api_over(server).turn("c1", "hi")

    assert turn.error == "asked the person a question"
    assert server.posted() == [MESSAGES]


def test_an_error_or_a_halt_is_the_turns_error():
    errored = FakeServer().on(MESSAGES, sse(("error", {"message": "boom"})))
    halted = FakeServer().on(MESSAGES, sse(("halted", {"reason": "loop"})))

    assert api_over(errored).turn("c1", "hi").error == "boom"
    assert api_over(halted).turn("c1", "hi").error == "halted: loop"


def test_a_conversation_is_autonomous_only_when_the_caller_says_so():
    server = FakeServer().on("/api/conversations", as_json({"id": "c1"}), as_json({"id": "c2"}))
    api = api_over(server)

    api.create_conversation("coach")
    api.create_conversation("coach", autonomous=False)

    first, second = (body for _path, body in server.requests)
    assert first == {"agent_id": "coach"}
    assert second == {"agent_id": "coach", "autonomous": False}


def test_a_server_gets_the_bench_environment_plus_what_it_is_told(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MY_AGENT_HOME", "/live/home")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("COACH_BOT_TOKEN", "x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    server = Server(
        tmp_path,
        tmp_path / "home",
        8798,
        extra_args=["--no-schedule"],
        extra_env={"HOME": str(tmp_path / "run")},
        dropped_env=["COACH_BOT_TOKEN"],
    )

    env = server.environment()

    assert env["MY_AGENT_HOME"] == str(tmp_path / "home")
    assert env["HOME"] == str(tmp_path / "run")
    assert "OPENROUTER_API_KEY" in env
    assert "TELEGRAM_BOT_TOKEN" not in env
    assert "COACH_BOT_TOKEN" not in env
    assert server.command()[-3:] == ["--port", "8798", "--no-schedule"]
    assert server.log_path == tmp_path / "home" / "server.log"


def test_a_shell_allow_list_in_the_callers_environment_does_not_reach_the_server(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setenv("MY_AGENT_SHELL_ALLOW_PATTERNS", "python3 ")

    env = Server(tmp_path, tmp_path / "home", 8798).environment()

    assert "MY_AGENT_SHELL_ALLOW_PATTERNS" not in env


def test_a_server_can_log_outside_its_home(tmp_path: Path):
    server = Server(tmp_path, tmp_path / "home", 8798, log_path=tmp_path / "logs" / "s.log")

    assert server.log_path == tmp_path / "logs" / "s.log"
