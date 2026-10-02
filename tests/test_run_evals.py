"""The eval runner: how a run is played and judged, when the eval stops, what it refuses before it
copies anything, and what a dry run through a real server leaves behind."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import eval_cli
import eval_play
import httpx
import pytest
import run_evals
from eval_cases import Case, parse_case
from eval_check import RUN, Failure
from eval_client import EvalApi
from eval_report import Report, RunResult
from eval_reset import RESET_FAILED, ResetError
from llm_bench_server import port_is_free

from my_agent_crew.artifacts.diff import line_span
from my_agent_crew.texts import MEMORY_SAVED
from my_agent_crew.texts_canvas import PICK_LINES
from my_agent_crew.texts_search import CONVERSATION_SEARCH_EMPTY
from my_agent_crew.tools.artifact_texts import ARTIFACT_LIST_EMPTY
from tests.http_fake import FakeServer, as_json, say, sse, tool_approval

CONV = "/api/conversations/c1"


@pytest.fixture(autouse=True)
def no_settling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eval_play, "SETTLE_SECONDS", 0.0)


def case_of(name: str, *messages: str | dict, agent: str = "default", **rest) -> Case:
    raw = {"id": name, "agent": agent, "messages": list(messages or ["hi"]), **rest}
    return parse_case(raw, "test")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def ledger(cost: float, unknown: int = 0) -> httpx.Response:
    purposes = [{"purpose": "chat", "cost_usd": cost, "unknown_cost_calls": unknown}]
    return as_json({"purposes": purposes})


def record(*messages: dict, agent: str = "default", **more) -> httpx.Response:
    return as_json({"id": "c1", "agent_id": agent, "messages": list(messages), **more})


def said(text: str, *calls: dict) -> dict:
    return {"role": "assistant", "content": text, "tool_calls": list(calls)}


def told(text: str) -> dict:
    return {"role": "user", "content": text}


def one_run(
    *turns: httpx.Response, after: httpx.Response, cost=(0.0, 0.0), runs: list[dict] | None = None
) -> FakeServer:
    """The requests one run makes: the ledger, a conversation, a stream per turn, the record
    read back, the family of runs, the canvases it has (none unless a test queues some), and the
    ledger again."""
    return (
        FakeServer()
        .on("/api/stats", ledger(cost[0]), ledger(cost[1]))
        .on("/api/conversations", as_json({"id": "c1"}))
        .on(f"{CONV}/messages", *turns)
        .on(CONV, after)
        .on("/api/activity/runs", as_json(runs or []))
        .always("/api/artifacts", as_json([]))
    )


def api_over(server: FakeServer) -> EvalApi:
    return EvalApi("http://test/api", 5.0, transport=server.transport)


def test_a_run_that_keeps_every_expectation_passes_and_spends_what_the_ledger_grew_by():
    case = case_of(
        "deleting-asks-first",
        "delete notes.txt",
        expect={
            "asks_approval": [{"name": "shell_run", "args_regex": r"rm\b"}],
            "not_calls_tool": [{"name": "workspace_write"}],
            "reply_contains": "cancelled",
            "max_cost_usd": 0.02,
        },
    )
    server = one_run(
        sse(tool_approval("a1", command="rm notes.txt")),
        after=record(told("delete notes.txt"), said("cancelled")),
        cost=(0.10, 0.115),
    ).on(f"{CONV}/approvals/a1", sse(say("cancelled")))

    result = eval_play.play(api_over(server), case, 1)

    assert result.failures == ()
    assert result.reply == "cancelled"
    assert result.spent_usd == pytest.approx(0.015)
    assert server.body_of(f"{CONV}/approvals/a1") == {"approve": False}


def test_a_run_says_which_expectation_it_broke():
    case = case_of("c", expect={"reply_contains": "banana"})
    server = one_run(sse(say("done")), after=record(told("hi"), said("done")))

    result = eval_play.play(api_over(server), case, 2)

    assert [f.assertion for f in result.failures] == ["reply_contains"]
    assert result.number == 2


def test_a_run_is_played_on_a_conversation_that_is_not_autonomous_for_the_cases_agent():
    server = one_run(sse(say("done")), after=record(told("hi"), said("done"), agent="coach"))

    eval_play.play(api_over(server), case_of("c", agent="coach"), 1)

    assert server.body_of("/api/conversations") == {"agent_id": "coach", "autonomous": False}


def test_a_turn_that_ends_in_error_ends_the_run_before_the_next_message():
    case = case_of("c", "first", "second")
    server = one_run(sse(("error", {"message": "boom"})), after=record(told("first")))

    result = eval_play.play(api_over(server), case, 1)

    assert [(f.assertion, f.detail) for f in result.failures] == [(RUN, "boom")]
    assert server.posted().count(f"{CONV}/messages") == 1


def test_the_turns_of_a_case_are_told_apart_by_the_tool_calls_they_made():
    call = {"id": "t1", "name": "workspace_write", "arguments": {"path": "a.txt"}}
    case = case_of(
        "c",
        "hello",
        "write a file",
        expect={"calls_tool": [{"name": "workspace_write", "turn": 2}]},
    )
    server = one_run(
        sse(say("hi")),
        sse(say("written")),
        after=record(told("hello"), said("hi"), told("write a file"), said("written", call)),
    )

    assert eval_play.play(api_over(server), case, 1).failures == ()


def test_what_a_delegated_child_did_counts_as_part_of_the_run():
    case = case_of("c", expect={"delegates_to": {"agent": "researcher"}})
    call = {"id": "t1", "name": "delegate", "arguments": {}}
    runs = [
        {"conversation_id": "c1", "started_at": "2026-09-29T00:00:01+00:00"},
        {"conversation_id": "c2", "started_at": "2026-09-29T00:00:02+00:00"},
    ]
    server = one_run(
        sse(say("asked")), after=record(told("hi"), said("asked", call)), runs=runs
    ).on("/api/conversations/c2", as_json({"agent_id": "researcher", "messages": []}))

    assert eval_play.play(api_over(server), case, 1).failures == ()


WEEKEND = "# Weekend\n- Clean the fridge\n- Wash the curtains\n"


def canvas(content: str, version: int = 1) -> httpx.Response:
    return as_json({"id": "a1", "head_version": version, "content": content})


def sent_messages(server: FakeServer) -> list[dict]:
    return [body for _method, path, body, _query in server.requests if path == f"{CONV}/messages"]


def test_canvas_steps_run_between_the_turns_and_every_later_message_carries_the_open_canvas():
    case = case_of(
        "c",
        {"create_canvas": {"title": "Weekend", "content": WEEKEND}},
        "look",
        {"select_canvas": "Clean the fridge"},
        "this one?",
        "ta",
        expect={"canvas_count": 1, "canvas_contains": "Water the plants"},
    )
    turns = [told("look"), said("seen"), told("this one?"), said("that"), told("ta"), said("ok")]
    server = (
        one_run(sse(say("seen")), sse(say("that")), sse(say("ok")), after=record(*turns))
        .on("/api/artifacts", canvas(WEEKEND), as_json([{"id": "a1"}]))
        .on("/api/artifacts/a1", canvas(WEEKEND), canvas(WEEKEND + "- Water the plants\n", 2))
    )

    result = eval_play.play(api_over(server), case, 1)

    assert result.failures == ()
    picked = {"version": 1, "text": "Clean the fridge", "line_start": 2, "line_end": 2}
    assert sent_messages(server) == [
        {"text": "look", "canvas": {"artifact_id": "a1", "selection": None}},
        {"text": "this one?", "canvas": {"artifact_id": "a1", "selection": picked}},
        {"text": "ta", "canvas": {"artifact_id": "a1", "selection": None}},
    ]
    canvas_or_turn = ("/api/artifacts", f"{CONV}/messages")
    assert [call for call in server.calls() if call[1].startswith(canvas_or_turn)] == [
        ("POST", "/api/artifacts"),
        ("POST", f"{CONV}/messages"),
        ("GET", "/api/artifacts/a1"),
        ("POST", f"{CONV}/messages"),
        ("POST", f"{CONV}/messages"),
        ("GET", "/api/artifacts"),
        ("GET", "/api/artifacts/a1"),
    ]


def test_a_canvas_step_that_cannot_be_done_ends_the_run_before_the_next_message():
    case = case_of("c", "hello", {"edit_canvas": {"old": "Wash the dishes", "new": "x"}}, "more")
    server = (
        one_run(sse(say("hi")), after=record(told("hello"), said("hi")))
        .on("/api/artifacts", as_json([{"id": "a1"}]))
        .on("/api/artifacts/a1", canvas(WEEKEND))
    )

    result = eval_play.play(api_over(server), case, 1)

    detail = "edit_canvas: 'Wash the dishes' is in the canvas 0 times, not once"
    assert [(f.assertion, f.detail) for f in result.failures] == [(RUN, detail)]
    assert server.posted().count(f"{CONV}/messages") == 1
    assert not eval_play.stalled(result)


def test_a_run_keeps_what_it_left_in_its_transcript(tmp_path):
    case = case_of("c", {"create_canvas": {"title": "Weekend", "content": WEEKEND}}, "rm it")
    runs = [
        {"conversation_id": "c1", "started_at": "2026-09-29T00:00:01+00:00"},
        {"conversation_id": "c2", "started_at": "2026-09-29T00:00:02+00:00"},
    ]
    child = {"agent_id": "researcher", "messages": [told("look")]}
    server = (
        one_run(
            sse(tool_approval("p1", command="rm notes.txt")),
            after=record(told("rm it"), said("cancelled")),
            runs=runs,
        )
        .on(f"{CONV}/approvals/p1", sse(say("cancelled")))
        .on("/api/conversations/c2", as_json(child))
        .on("/api/artifacts", canvas(WEEKEND), as_json([{"id": "a1"}]))
        .on("/api/artifacts/a1", canvas(WEEKEND))
    )
    path = tmp_path / "transcripts" / "01-c-2.json"

    eval_play.play(api_over(server), case, 2, path)

    kept = json.loads(path.read_text(encoding="utf-8"))
    assert {key: kept[key] for key in ("case", "run", "children", "canvases")} == {
        "case": "c",
        "run": 2,
        "children": [child],
        "canvases": [{"id": "a1", "head_version": 1, "content": WEEKEND}],
    }
    assert kept["conversation"]["messages"] == [told("rm it"), said("cancelled")]
    assert [(asked["approval_id"], asked["turn"]) for asked in kept["asked"]] == [("p1", 1)]


def test_a_message_sent_before_any_canvas_is_open_is_its_text_alone():
    server = one_run(sse(say("done")), after=record(told("hi"), said("done")))

    eval_play.play(api_over(server), case_of("c"), 1)

    assert sent_messages(server) == [{"text": "hi"}]


def test_a_run_that_timed_out_or_lost_the_server_is_a_stall_and_one_that_did_not_is_not():
    def run_with(failure: Failure) -> RunResult:
        return RunResult(1, (failure,))

    assert eval_play.stalled(run_with(Failure(RUN, "timed out after 5s")))
    assert eval_play.stalled(run_with(Failure(RUN, "http: connection refused")))
    assert eval_play.stalled(run_with(Failure(RUN, f"{RESET_FAILED} conversations c9")))
    assert not eval_play.stalled(run_with(Failure(RUN, "boom")))
    assert not eval_play.stalled(run_with(Failure("reply_contains", "timed out after 5s")))


class Spender:
    """Stands in for the api and for `play`: each run adds to a ledger that starts non-zero, and
    the run's own result says nothing about it, as when a side call is what cost the money."""

    def __init__(self, per_run: float = 0.0, start: float = 0.5, unknown_per_run: int = 0) -> None:
        self.spent, self.per_run, self.unknown_per_run = start, per_run, unknown_per_run
        self.unknown = 0
        self.played: list[tuple[str, int]] = []
        self.results: dict[int, RunResult] = {}
        self.raise_at: dict[int, BaseException] = {}
        self.unreadable_after = 10**9
        self.resets: list[int] = []  # how many runs had been played at each reset
        self.reset_raises_at: dict[int, BaseException] = {}
        self.transcripts: list[Path | None] = []

    def ledger(self) -> tuple[float, int]:
        if len(self.played) >= self.unreadable_after:
            raise httpx.ConnectError("ledger unreadable")
        return self.spent, self.unknown

    def fresh(self) -> None:
        self.resets.append(len(self.played))
        if len(self.resets) in self.reset_raises_at:
            raise self.reset_raises_at[len(self.resets)]

    def play(
        self, api: object, case: Case, number: int, transcript: Path | None = None
    ) -> RunResult:
        self.played.append((case.id, number))
        self.transcripts.append(transcript)
        nth = len(self.played)
        if nth in self.raise_at:
            raise self.raise_at[nth]
        self.spent += self.per_run
        self.unknown += self.unknown_per_run
        return self.results.get(nth, RunResult(number))


def run_with(spender: Spender, monkeypatch, tmp_path: Path, *cases: Case, budget: float = 0.5):
    monkeypatch.setattr(eval_play, "play", spender.play)
    report = Report("2026-09-29T00:00:00+00:00", 3, budget)
    eval_play.run_cases(spender, cases, report, tmp_path, fresh=spender.fresh)
    return report


def test_every_run_of_every_case_is_played_in_order_and_the_results_are_written(
    monkeypatch, tmp_path
):
    spender = Spender()

    report = run_with(spender, monkeypatch, tmp_path, case_of("a"), case_of("b"))

    assert spender.played == [(c, n) for c in "ab" for n in (1, 2, 3)]
    assert report.stopped == ""
    data = json.loads((tmp_path / "results.json").read_text())
    assert [len(case["runs"]) for case in data["cases"]] == [3, 3]
    assert "| a | default | pass | 3/3 |" in (tmp_path / "results.md").read_text()


def test_every_run_starts_from_a_clean_server(monkeypatch, tmp_path):
    spender = Spender()

    run_with(spender, monkeypatch, tmp_path, case_of("a"), case_of("b"))

    assert spender.resets == [0, 1, 2, 3, 4, 5]


@pytest.mark.parametrize(
    ("error", "detail"),
    [
        (ResetError(f"{RESET_FAILED} conversations c9"), f"{RESET_FAILED} conversations c9"),
        (httpx.ConnectError("refused"), "http: refused"),
    ],
)
def test_a_run_that_cannot_start_from_a_clean_server_is_not_played_and_the_eval_stops(
    monkeypatch, tmp_path, error, detail
):
    spender = Spender()
    spender.reset_raises_at[2] = error

    report = run_with(spender, monkeypatch, tmp_path, case_of("a"), case_of("b"))

    assert spender.played == [("a", 1)]
    assert [(f.assertion, f.detail) for f in report.cases[0].runs[1].failures] == [(RUN, detail)]
    assert report.stopped == "stall"
    assert [len(item.runs) for item in report.cases] == [2, 0]


def test_each_run_keeps_its_transcript_beside_the_results_named_by_case_and_run(
    monkeypatch, tmp_path
):
    spender = Spender()

    run_with(spender, monkeypatch, tmp_path, case_of("a"), case_of("is it/ok?"))

    assert spender.transcripts == [
        tmp_path / "transcripts" / name
        for name in (
            "01-a-1.json",
            "01-a-2.json",
            "01-a-3.json",
            "02-is_it_ok_-1.json",
            "02-is_it_ok_-2.json",
            "02-is_it_ok_-3.json",
        )
    ]


def test_the_total_is_what_the_ledger_grew_by_so_a_price_outside_the_runs_is_counted(
    monkeypatch, tmp_path
):
    spender = Spender(per_run=0.01, start=0.5)

    report = run_with(spender, monkeypatch, tmp_path, case_of("a"))

    assert report.spent_usd == pytest.approx(0.03)
    assert all(run.spent_usd == 0.0 for run in report.cases[0].runs)


def test_the_budget_is_checked_before_each_run_and_a_spent_one_stops_the_eval(
    monkeypatch, tmp_path
):
    spender = Spender(per_run=0.03)

    report = run_with(spender, monkeypatch, tmp_path, case_of("a"), case_of("b"), budget=0.05)

    assert spender.played == [("a", 1), ("a", 2)]
    assert report.stopped == "cap"
    assert report.spent_usd == pytest.approx(0.06)
    assert "> Stopped by cap:" in (tmp_path / "results.md").read_text()


def test_calls_that_came_back_without_a_price_are_counted_from_where_the_eval_began(
    monkeypatch, tmp_path
):
    spender = Spender(unknown_per_run=1)
    spender.unknown = 7

    report = run_with(spender, monkeypatch, tmp_path, case_of("a"))

    assert report.unknown_cost_calls == 3


def test_a_run_that_timed_out_stops_the_eval_where_it_is(monkeypatch, tmp_path):
    spender = Spender()
    spender.results[2] = RunResult(2, (Failure(RUN, "timed out after 5s"),))

    report = run_with(spender, monkeypatch, tmp_path, case_of("a"), case_of("b"))

    assert spender.played == [("a", 1), ("a", 2)]
    assert report.stopped == "stall"
    assert [len(item.runs) for item in report.cases] == [2, 0]


def test_a_lost_server_is_a_run_that_could_not_finish_and_the_eval_stops(monkeypatch, tmp_path):
    spender = Spender()
    spender.raise_at[2] = httpx.ConnectError("refused")

    report = run_with(spender, monkeypatch, tmp_path, case_of("a"))

    lost = report.cases[0].runs[1].failures[0]
    assert (lost.assertion, lost.detail.startswith("http:")) == (RUN, True)
    assert report.stopped == "stall"
    assert spender.played == [("a", 1), ("a", 2)]


def test_a_run_that_only_broke_an_expectation_does_not_stop_the_eval(monkeypatch, tmp_path):
    spender = Spender()
    spender.results[1] = RunResult(1, (Failure("calls_tool", "nothing called"),))

    report = run_with(spender, monkeypatch, tmp_path, case_of("a"))

    assert len(spender.played) == 3
    assert report.stopped == ""


def test_a_ledger_that_cannot_be_read_after_a_run_does_not_end_the_eval(monkeypatch, tmp_path):
    spender = Spender(per_run=0.01)
    spender.unreadable_after = 1

    report = run_with(spender, monkeypatch, tmp_path, case_of("a"))

    assert len(spender.played) == 3
    assert report.stopped == ""


def test_a_run_cut_short_by_ctrl_c_leaves_the_numbers_of_the_runs_before_it(monkeypatch, tmp_path):
    spender = Spender()
    spender.raise_at[3] = KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        run_with(spender, monkeypatch, tmp_path, case_of("a"))

    data = json.loads((tmp_path / "results.json").read_text())
    assert [run["run"] for run in data["cases"][0]["runs"]] == [1, 2]


DRY = ["--dry-run", "--runs", "1"]


def refused(tmp_path: Path, *flags: str, port: int | None = None) -> str:
    argv = [*flags, "--out", str(tmp_path / "out"), "--port", str(port or free_port())]
    with pytest.raises(SystemExit) as stop:
        run_evals.main(argv)
    assert not (tmp_path / "out" / eval_cli.RUN_DIR).exists()
    return str(stop.value)


def test_no_runs_is_refused(tmp_path):
    assert "--runs must be at least 1" in refused(tmp_path, "--dry-run", "--runs", "0")


def test_a_budget_of_nothing_is_refused(tmp_path):
    assert "--max-usd must be more than 0" in refused(tmp_path, *DRY, "--max-usd", "0")


def test_an_output_folder_inside_the_repository_is_refused_so_no_commit_can_take_the_copy():
    argv = [*DRY, "--out", str(eval_cli.REPO / "eval-out"), "--port", str(free_port())]

    with pytest.raises(SystemExit, match="inside the repository"):
        run_evals.main(argv)

    assert not (eval_cli.REPO / "eval-out").exists()


def test_a_busy_port_is_refused_before_anything_is_copied(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        port = int(sock.getsockname()[1])

        assert "is busy" in refused(tmp_path, *DRY, port=port)


def test_a_real_run_without_the_model_key_in_the_shell_is_refused(tmp_path, monkeypatch):
    monkeypatch.delenv(eval_cli.MODEL_KEY, raising=False)
    cases = ["--cases", str(eval_cli.EXAMPLE_CASES), "--home", str(tmp_path / "home")]

    assert "is not exported in this shell" in refused(tmp_path, *cases)


def test_a_folder_left_by_an_earlier_run_is_refused_and_not_deleted(tmp_path):
    leftover = tmp_path / "out" / eval_cli.RUN_DIR
    leftover.mkdir(parents=True)
    (leftover / "kept.txt").write_text("x")

    with pytest.raises(SystemExit, match="left from an earlier run"):
        run_evals.main([*DRY, "--out", str(tmp_path / "out"), "--port", str(free_port())])

    assert (leftover / "kept.txt").exists()


def test_a_case_that_is_not_in_the_file_is_refused_with_the_ones_that_are(tmp_path):
    message = refused(tmp_path, *DRY, "--only", "nothing-like-it")

    assert "no such case: nothing-like-it" in message
    assert "a-question-changes-nothing" in message


def test_a_cases_path_that_does_not_exist_is_refused(tmp_path):
    assert "no such file or directory" in refused(tmp_path, *DRY, "--cases", str(tmp_path / "x"))


def test_a_home_with_no_evals_folder_is_refused_for_want_of_cases(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    assert "no such file or directory" in refused(tmp_path, "--runs", "1", "--home", str(home))


CASES = """\
- id: deleting-asks-first
  agent: default
  messages:
    - '/tool shell_run {"command": "rm notes.txt"}'
  expect:
    asks_approval:
      - {name: shell_run, args_regex: 'rm\\b.*notes\\.txt'}
    max_calls: {workspace_write: 0}

- id: the-write-comes-in-the-second-turn
  agent: default
  messages:
    - hello
    - '/tool workspace_write {"path": "a.txt", "content": "x"}'
  expect:
    not_calls_tool:
      - {name: workspace_write, turn: 1}
    calls_tool:
      - {name: workspace_write, turn: 2}

- id: a-delegated-child-asks-in-its-own-conversation
  agent: default
  messages:
    - '/tool delegate {"task": "/tool shell_run {\\"command\\": \\"echo hi\\"}"}'
  expect:
    asks_approval:
      - {name: shell_run, args_regex: 'echo hi'}
    calls_tool:
      - {name: shell_run, turn: 1}

- id: nothing-the-fake-model-can-say
  agent: default
  messages: [hello]
  expect:
    reply_contains: banana

- id: the-person-works-on-a-canvas-between-turns
  agent: default
  messages:
    - create_canvas:
        title: Weekend
        content: |
          # Weekend

          - Clean out the fridge on Saturday
          - Wash the curtains in the spare room
    - edit_canvas: {old: Wash the curtains, new: Wash the blankets}
    - '/tool artifact_list {}'
    - select_canvas: Clean out the fridge on Saturday
    - what about this line?
  expect:
    calls_tool:
      - {name: artifact_list, turn: 1}
    canvas_count: 1
    canvas_contains: [Wash the blankets]
    canvas_not_contains: [Wash the curtains]
    reply_contains: [Clean out the fridge on Saturday]
    canvas_not_in_chat: true

- id: the-fake-model-says-the-selected-lines-back
  agent: default
  messages:
    - create_canvas:
        title: Lunch
        content: |
          - Monday: chicken rice with greens
          - Tuesday: beef noodle soup, extra herbs
          - Wednesday: grilled fish and rice
    - select_canvas: |
        Monday: chicken rice with greens
        - Tuesday: beef noodle soup, extra herbs
        - Wednesday: grilled fish and rice
    - and these?
  expect:
    canvas_not_in_chat: true

- id: each-run-starts-with-no-canvas
  agent: default
  messages:
    - '/tool artifact_list {}'
    - create_canvas: {title: Leftover, content: "- one line"}

- id: each-run-starts-with-no-chat
  agent: default
  messages: ['/tool conversation_search {"query": "zebra"}']

- id: each-run-starts-with-the-notes-it-had
  agent: default
  messages: ['/tool memory_save {"text": "zebra crossing on the corner"}']
"""


def test_a_dry_run_plays_real_turns_through_a_real_server_and_leaves_only_the_results(
    tmp_path, capsys
):
    cases = tmp_path / "cases.yaml"
    cases.write_text(CASES, encoding="utf-8")
    out, port = tmp_path / "out", free_port()

    code = run_evals.main(
        ["--dry-run", "--cases", str(cases), "--runs", "2", "--port", str(port), "--out", str(out)]
    )

    assert code == 0
    data = json.loads((out / "results" / "results.json").read_text())
    by_id = {case["id"]: case for case in data["cases"]}
    assert data["dry_run"] is True and data["succeeded"] is True
    playable = (
        "deleting-asks-first",
        "the-write-comes-in-the-second-turn",
        "a-delegated-child-asks-in-its-own-conversation",
        "the-person-works-on-a-canvas-between-turns",
    )
    for name in playable:
        assert [run["failures"] for run in by_id[name]["runs"]] == [[], []], name
    banana = by_id["nothing-the-fake-model-can-say"]["runs"][0]
    assert [f["assertion"] for f in banana["failures"]] == ["reply_contains"]
    assert banana["ok"] is True
    # The server placed the selection by the lines the eval counted, on the edited version.
    worked = by_id["the-person-works-on-a-canvas-between-turns"]["runs"][0]
    assert PICK_LINES.format(span=line_span(3, 3), version=2) in worked["reply"]
    pasted = by_id["the-fake-model-says-the-selected-lines-back"]["runs"][0]
    assert [(f["assertion"], f["detail"]) for f in pasted["failures"]] == [
        ("canvas_not_in_chat", "the chat repeats 100% of the canvas 'Lunch'")
    ]
    # Each run starts clean: no canvas, chat or note an earlier run left changes its answer.
    clean = {
        "each-run-starts-with-no-canvas": ARTIFACT_LIST_EMPTY,
        "each-run-starts-with-no-chat": CONVERSATION_SEARCH_EMPTY,
        "each-run-starts-with-the-notes-it-had": MEMORY_SAVED.format(count=1),
    }
    for name, answer in clean.items():
        assert [answer in run["reply"] for run in by_id[name]["runs"]] == [True, True], name
    transcripts = out / "results" / "transcripts"
    assert len(list(transcripts.iterdir())) == 2 * len(by_id)
    left = json.loads((transcripts / "07-each-run-starts-with-no-canvas-2.json").read_text())
    assert [kept["title"] for kept in left["canvases"]] == ["Leftover"]
    delegated = json.loads(
        (transcripts / "03-a-delegated-child-asks-in-its-own-conversation-1.json").read_text()
    )
    assert len(delegated["children"]) == 1
    assert "> Dry run." in (out / "results" / "results.md").read_text()
    assert (out / "results" / "server.log").exists()
    assert not (out / eval_cli.RUN_DIR).exists()
    assert port_is_free(port)
    assert "dry run: the fake model answers" in capsys.readouterr().out


def test_a_case_for_an_agent_the_copy_does_not_have_is_refused_and_the_copy_is_removed(tmp_path):
    cases = tmp_path / "cases.yaml"
    cases.write_text("- id: lost\n  agent: nobody-here\n  messages: [hi]\n", encoding="utf-8")
    out, port = tmp_path / "out", free_port()

    with pytest.raises(SystemExit, match="no such agent in the copy: nobody-here"):
        run_evals.main(["--dry-run", "--cases", str(cases), "--port", str(port), "--out", str(out)])

    assert not (out / eval_cli.RUN_DIR).exists()
    assert port_is_free(port)


def test_memory_the_eval_could_not_put_back_is_refused_before_any_run(tmp_path, monkeypatch):
    cases = tmp_path / "cases.yaml"
    cases.write_text("- id: one\n  agent: default\n  messages: [hi]\n", encoding="utf-8")
    out, port = tmp_path / "out", free_port()
    monkeypatch.setattr(run_evals, "memory_roots", lambda home: (tmp_path / "live" / "memory",))

    with pytest.raises(SystemExit, match="outside the run dir"):
        run_evals.main(["--dry-run", "--cases", str(cases), "--port", str(port), "--out", str(out)])

    assert not (out / "results" / eval_play.TRANSCRIPTS).exists()
    assert not (out / eval_cli.RUN_DIR).exists()
    assert port_is_free(port)
