"""The client the bench and the behaviour evals share: how a turn follows its approvals, and
what a server it starts is given: what a program needs to run and the model key, nothing else
of the caller's environment."""

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

    first, second = (body for _method, _path, body, _query in server.requests)
    assert first == {"agent_id": "coach"}
    assert second == {"agent_id": "coach", "autonomous": False}


def test_a_server_gets_what_a_program_needs_and_the_model_key_and_nothing_else(tmp_path: Path):
    needed = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/Users/owner",
        "LANG": "vi_VN.UTF-8",
        "LC_ALL": "vi_VN.UTF-8",
        "LC_CTYPE": "UTF-8",
        "TERM": "xterm-256color",
        "TMPDIR": "/var/folders/x/T/",
        "USER": "owner",
        "LOGNAME": "owner",
        "SHELL": "/bin/zsh",
        "TZ": "Asia/Saigon",
        "OPENROUTER_API_KEY": "x",
    }
    kept_out = {
        "MY_AGENT_HOME": "/live/home",
        "MY_AGENT_COST_CAP_USD": "5",
        "MY_AGENT_SHELL_ALLOW_PATTERNS": "python3 ",
        "TELEGRAM_BOT_TOKEN": "x",
        "COACH_BOT_TOKEN": "x",
        "BRAVE_API_KEY": "x",
        "GEMINI_API_KEY": "x",
        "LINEAR_API_KEY": "x",
        "CLAUDE_CODE_MESSAGING_TOKEN": "x",
        "SSH_AUTH_SOCK": "/tmp/agent.sock",
    }
    server = Server(
        tmp_path,
        tmp_path / "home",
        8798,
        extra_args=["--no-schedule"],
        extra_env={"HOME": str(tmp_path / "run")},
    )

    env = server.environment({**needed, **kept_out})

    homes = {"HOME": str(tmp_path / "run"), "MY_AGENT_HOME": str(tmp_path / "home")}
    assert env == {**needed, **homes}
    assert server.command()[-3:] == ["--port", "8798", "--no-schedule"]
    assert server.log_path == tmp_path / "home" / "server.log"


def test_a_server_reads_the_environment_of_the_process_starting_it(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/agent.sock")

    env = Server(tmp_path, tmp_path / "home", 8798).environment()

    assert env.get("OPENROUTER_API_KEY") == "x"
    assert env.get("SSH_AUTH_SOCK") is None


def test_a_server_can_log_outside_its_home(tmp_path: Path):
    server = Server(tmp_path, tmp_path / "home", 8798, log_path=tmp_path / "logs" / "s.log")

    assert server.log_path == tmp_path / "logs" / "s.log"
