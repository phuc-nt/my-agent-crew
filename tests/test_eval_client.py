"""How an eval case answers what its turns run into, and what the client reports back."""

from __future__ import annotations

import threading
import time

import eval_client
import httpx
import pytest
from eval_client import EvalApi

from tests.http_fake import FakeServer, as_json, held, opens, question, say, sse, tool_approval

MESSAGES = "/api/conversations/c1/messages"
A1 = "/api/conversations/c1/approvals/a1"
Q1 = "/api/conversations/c1/approvals/q1/answer"
RUNS = "/api/activity/runs"
CHILD = "/api/conversations/k1"
K1 = "/api/conversations/k1/approvals/ka1"
K2 = "/api/conversations/k1/approvals/ka2"
KQ = "/api/conversations/k1/approvals/kq1/answer"
LIVE = "/Users/someone/.my-agent-crew"


def api_over(server: FakeServer, **kwargs) -> EvalApi:
    return EvalApi("http://test/api", 5.0, transport=server.transport, **kwargs)


def one_approval(**arguments) -> FakeServer:
    return FakeServer().on(MESSAGES, sse(tool_approval("a1", **arguments))).on(A1, sse(say("done")))


def test_a_case_that_approves_lets_the_tool_run_and_keeps_what_was_asked():
    server = one_approval(command="ls")
    api = api_over(server)
    api.start_case("approve", [])

    turn = api.turn("c1", "hi")

    assert server.body_of(A1) == {"approve": True}
    assert (turn.approvals, turn.answer, turn.error) == (1, "done", "")
    assert [(a["name"], a["arguments"], a["turn"]) for a in api.asked] == [
        ("shell_run", {"command": "ls"}, 1)
    ]


def test_a_case_denies_by_default_and_still_records_the_approval():
    server = one_approval(command="rm notes.txt")
    api = api_over(server)
    api.start_case("deny", [])

    api.turn("c1", "hi")

    assert server.body_of(A1) == {"approve": False}
    assert len(api.asked) == 1


def test_approving_is_refused_for_a_command_that_names_a_live_path_whatever_its_case():
    server = one_approval(command=f"cat {LIVE.upper()}/agent.yaml")
    api = api_over(server, live_paths=[LIVE])
    api.start_case("approve", [])

    api.turn("c1", "hi")

    assert server.body_of(A1) == {"approve": False}
    assert len(api.asked) == 1


def test_an_approval_that_names_no_live_path_is_approved_even_with_live_paths_known():
    server = one_approval(command="cat notes.txt")
    api = api_over(server, live_paths=[LIVE])
    api.start_case("approve", [])

    api.turn("c1", "hi")

    assert server.body_of(A1) == {"approve": True}


def test_turns_count_from_one_in_a_case_and_a_new_case_starts_over():
    server = (
        FakeServer()
        .on(MESSAGES, sse(say("one")), sse(say("two")), sse(tool_approval("a1", command="ls")))
        .on(A1, sse(say("three")))
    )
    api = api_over(server)
    api.start_case("approve", [])
    api.turn("c1", "first")
    api.turn("c1", "second")

    api.start_case("approve", [])
    api.turn("c1", "again")

    assert [a["turn"] for a in api.asked] == [1]


def test_a_question_takes_the_next_answer_of_the_case_and_is_not_an_approval():
    server = FakeServer().on(MESSAGES, sse(question("q1"))).on(Q1, sse(say("thanks")))
    api = api_over(server)
    api.start_case("deny", ["blue", "green"])

    turn = api.turn("c1", "hi")

    assert server.body_of(Q1) == {"answer": "blue"}
    assert api.answers == ["green"]
    assert api.asked == []
    assert (turn.approvals, turn.answer, turn.error) == (0, "thanks", "")


def test_a_question_with_no_answer_left_fails_the_turn_without_answering():
    server = FakeServer().on(MESSAGES, sse(question("q1")))
    api = api_over(server)
    api.start_case("deny", [])

    turn = api.turn("c1", "hi")

    assert "no answer left" in turn.error
    assert server.posted() == [MESSAGES]


def test_the_ledger_adds_up_every_purpose_and_the_calls_with_no_price():
    purposes = [
        {"purpose": "chat", "cost_usd": 0.01, "unknown_cost_calls": 0},
        {"purpose": "title", "cost_usd": 0.002, "unknown_cost_calls": 1},
    ]
    server = FakeServer().on("/api/stats", as_json({"purposes": purposes}), as_json({}))
    api = api_over(server)

    cost, unknown = api.ledger()

    assert (round(cost, 6), unknown) == (0.012, 1)
    assert api.ledger() == (0.0, 0)


def test_the_agents_the_server_knows_are_listed_by_id():
    server = FakeServer().on("/api/agents", as_json([{"id": "default"}, {"id": "coach"}]))

    assert api_over(server).agent_ids() == ["default", "coach"]


def test_a_turn_that_outlasts_its_time_is_cut_off_even_while_the_stream_keeps_talking():
    def endless():
        for _ in range(200):
            time.sleep(0.01)
            yield b"event: tool_call\ndata: {}\n\n"

    server = FakeServer().on(
        MESSAGES,
        httpx.Response(200, content=endless(), headers={"content-type": "text/event-stream"}),
    )
    api = api_over(server, turn_seconds=0.1)
    api.start_case("deny", [])

    turn = api.turn("c1", "hi")

    assert turn.error.startswith("timed out")
    assert turn.wall_s < 1.5


@pytest.fixture
def fast_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eval_client, "POLL_SECONDS", 0.005)


def run_of(conv_id: str, status: str, started_at: str) -> dict:
    return {"conversation_id": conv_id, "status": status, "started_at": started_at}


def waiting_on(approval_id: str, name: str = "shell_run", kind: str = "tool", **arguments) -> dict:
    """What `GET /conversations/<id>` says of an approval nobody has answered yet."""
    pending = {"id": approval_id, "tool_name": name, "arguments": arguments, "kind": kind}
    return {"pending_approval": pending}


def delegating(gate: threading.Event, child: dict) -> FakeServer:
    """A parent that holds its stream open, sending keep-alives, until `gate` opens, and a
    child that is waiting on `child`'s approval until it is answered."""
    runs = [run_of("c1", "running", "1"), run_of("k1", "awaiting_approval", "2")]
    return (
        FakeServer()
        .on(MESSAGES, held(gate, say("all done")))
        .always(RUNS, lambda: as_json(runs))
        .on(CHILD, as_json(child))
        .always(CHILD, lambda: as_json({"pending_approval": None}))
    )


def test_what_a_delegated_child_asks_is_answered_in_its_own_conversation_and_kept(fast_polling):
    gate = threading.Event()
    child_done = opens(gate, sse(say("child done")))
    server = delegating(gate, waiting_on("ka1", command="ls")).on(K1, child_done)
    api = api_over(server, turn_seconds=5)
    api.start_case("deny", [])

    turn = api.turn("c1", "hi")

    assert server.body_of(K1) == {"approve": False}
    assert (turn.answer, turn.error) == ("all done", "")
    assert [(a["name"], a["arguments"], a["turn"]) for a in api.asked] == [
        ("shell_run", {"command": "ls"}, 1)
    ]


def test_a_case_that_approves_lets_a_delegated_childs_tool_run(fast_polling):
    gate = threading.Event()
    server = delegating(gate, waiting_on("ka1", command="ls"))
    server.on(K1, opens(gate, sse(say("child done"))))
    api = api_over(server, turn_seconds=5)
    api.start_case("approve", [])

    api.turn("c1", "hi")

    assert server.body_of(K1) == {"approve": True}


def test_a_delegated_childs_question_takes_the_next_answer_of_the_case(fast_polling):
    gate = threading.Event()
    server = delegating(gate, waiting_on("kq1", "ask_user", "question", question="which one?"))
    server.on(KQ, opens(gate, sse(say("child done"))))
    api = api_over(server, turn_seconds=5)
    api.start_case("deny", ["blue", "green"])

    turn = api.turn("c1", "hi")

    assert server.body_of(KQ) == {"answer": "blue"}
    assert (api.answers, api.asked, turn.error) == (["green"], [], "")


def test_a_child_that_asks_again_in_the_turn_it_resumes_is_answered_each_time(fast_polling):
    gate = threading.Event()
    server = delegating(gate, waiting_on("ka1", command="ls"))
    server.on(K1, sse(tool_approval("ka2", command="pwd"))).on(K2, opens(gate, sse(say("ok"))))
    api = api_over(server, turn_seconds=5)
    api.start_case("deny", [])

    turn = api.turn("c1", "hi")

    assert [a["arguments"]["command"] for a in api.asked] == ["ls", "pwd"]
    assert (server.body_of(K1), server.body_of(K2)) == ({"approve": False}, {"approve": False})
    assert turn.error == ""


def test_an_approval_of_the_conversation_itself_is_left_to_its_own_stream(fast_polling):
    gate = threading.Event()
    server = (
        FakeServer()
        .on(MESSAGES, held(gate, tool_approval("a1", command="ls")))
        .always(RUNS, lambda: as_json([run_of("c1", "awaiting_approval", "1")]))
        .on(A1, sse(say("done")))
    )
    api = api_over(server, turn_seconds=5)
    api.start_case("deny", [])
    threading.Timer(0.05, gate.set).start()

    turn = api.turn("c1", "hi")

    assert (turn.answer, turn.error) == ("done", "")
    assert "/api/conversations/c1" not in server.posted()


def test_nothing_is_asked_of_the_server_once_the_turn_is_over(fast_polling):
    server = FakeServer().on(MESSAGES, sse(say("hi"))).always(RUNS, lambda: as_json([]))
    api = api_over(server)

    api.turn("c1", "hi")
    asked = len(server.requests)
    time.sleep(0.05)

    assert len(server.requests) == asked


def test_a_child_that_asks_what_the_case_cannot_answer_ends_the_turn_at_once(fast_polling):
    gate = threading.Event()  # never opens: the parent would wait for its child for ever
    server = delegating(gate, waiting_on("kq1", "ask_user", "question", question="which one?"))
    api = api_over(server, turn_seconds=5)
    api.start_case("deny", [])

    turn = api.turn("c1", "hi")

    assert "no answer left" in turn.error
    assert not any(path.endswith("/answer") for path in server.posted())
    assert turn.wall_s < 4


def test_a_failure_to_reach_the_server_while_watching_ends_the_turn(fast_polling):
    gate = threading.Event()
    server = FakeServer().on(MESSAGES, held(gate, say("never")))
    server.always(RUNS, lambda: httpx.Response(500))
    api = api_over(server, turn_seconds=5)

    turn = api.turn("c1", "hi")

    assert turn.error.startswith("http:")
    assert turn.wall_s < 4


def test_a_child_waiting_on_something_that_cannot_be_read_ends_the_turn(fast_polling):
    gate = threading.Event()
    server = delegating(gate, {"pending_approval": {"id": "ka1"}})
    api = api_over(server, turn_seconds=5)

    turn = api.turn("c1", "hi")

    assert "could not read" in turn.error
    assert turn.wall_s < 4
