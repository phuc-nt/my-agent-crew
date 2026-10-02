"""Canvas steps in an eval case: what the person does on a canvas between two messages, over the
REST routes the web uses, and how the canvases a run leaves behind are judged."""

from __future__ import annotations

import httpx
import pytest
from eval_canvas import NoteDue, Panel, parse_step, perform
from eval_cases import parse_case
from eval_check import RUN, Failure, Observed, check
from eval_client import EvalApi
from eval_paste import Canvas, pasted_share
from eval_play import stalled
from eval_report import RunResult

from tests.http_fake import FakeServer, as_json

LIST = "/api/artifacts"
ART = "/api/artifacts/a1"
WEEKEND = "# Weekend\n- Clean the fridge\n- Wash the curtains\n"


def api_over(server: FakeServer) -> EvalApi:
    return EvalApi("http://test/api", 5.0, transport=server.transport)


def canvas(content: str, version: int = 1, artifact_id: str = "a1") -> httpx.Response:
    return as_json({"id": artifact_id, "head_version": version, "content": content})


def run_step(server: FakeServer, raw: dict, panel: Panel | None = None) -> str:
    return perform(api_over(server), "c1", parse_step(raw, "test"), panel or Panel())


def judge(expect: dict, canvases: list[Canvas | str], *said: str) -> list[Failure]:
    raw = {"id": "c", "agent": "default", "messages": ["hi"], "expect": expect}
    held = tuple(c if isinstance(c, Canvas) else Canvas("Plan", c) for c in canvases)
    seen = Observed(reply=said[-1] if said else "", said=said, canvases=held)
    return check(parse_case(raw, "test"), seen)


# --- steps ----------------------------------------------------------------------------------


def test_create_canvas_makes_the_canvas_in_the_conversation_and_opens_it():
    server = FakeServer().on(LIST, canvas("- a\n"))
    panel = Panel()

    error = run_step(server, {"create_canvas": {"title": "Weekend", "content": "- a\n"}}, panel)

    assert error == ""
    assert server.body_of(LIST) == {
        "title": "Weekend",
        "kind": "markdown",
        "content": "- a\n",
        "conversation_id": "c1",
    }
    assert panel.carry() == {"canvas": {"artifact_id": "a1", "selection": None}}


def test_edit_canvas_saves_the_change_on_the_version_it_read_from_the_open_canvas():
    server = FakeServer().on(ART, canvas(WEEKEND, version=3), as_json({"version": 4}))
    edit = {"edit_canvas": {"old": "Wash the curtains", "new": "Wash the blankets"}}

    assert run_step(server, edit, Panel("a1")) == ""

    assert server.calls() == [("GET", ART), ("PUT", ART)]
    assert server.body_of(ART, "PUT") == {
        "content": "# Weekend\n- Clean the fridge\n- Wash the blankets\n",
        "base_version": 3,
    }


def test_with_no_canvas_open_a_step_works_on_the_newest_canvas_of_the_conversation_and_opens_it():
    newest = "/api/artifacts/a2"
    server = (
        FakeServer()
        .on(LIST, as_json([{"id": "a2"}, {"id": "a1"}]))
        .on(newest, canvas(WEEKEND, artifact_id="a2"), as_json({"version": 2}))
    )
    panel = Panel()

    assert run_step(server, {"edit_canvas": {"old": "Clean", "new": "Empty"}}, panel) == ""

    assert server.query_of(LIST) == {"conversation_id": "c1"}
    assert ("PUT", newest) in server.calls()
    assert panel.carry() == {"canvas": {"artifact_id": "a2", "selection": None}}


def test_a_step_in_a_conversation_without_a_canvas_fails_the_run():
    server = FakeServer().on(LIST, as_json([]))

    error = run_step(server, {"select_canvas": "fridge"})

    assert "no canvas" in error
    assert server.calls() == [("GET", LIST)]


@pytest.mark.parametrize(("content", "times"), [("# Empty\n", 0), ("Wash, Wash\n", 2)])
def test_an_edit_whose_old_text_is_not_there_exactly_once_fails_and_saves_nothing(content, times):
    server = FakeServer().on(ART, canvas(content))

    error = run_step(server, {"edit_canvas": {"old": "Wash", "new": "Dry"}}, Panel("a1"))

    assert f"{times} times" in error
    assert ("PUT", ART) not in server.calls()


def test_a_save_the_server_refuses_fails_the_run_without_stopping_the_eval():
    stale = {"detail": {"head_version": 5, "author": "agent", "content": "x"}}
    server = FakeServer().on(ART, canvas(WEEKEND), httpx.Response(409, json=stale))

    error = run_step(server, {"edit_canvas": {"old": "Clean", "new": "Empty"}}, Panel("a1"))

    assert "409" in error
    assert not stalled(RunResult(1, (Failure(RUN, error),)))


@pytest.mark.parametrize(
    ("server", "raw", "panel", "unread"),
    [
        (
            FakeServer().on(LIST, as_json({"head_version": 1})),
            {"create_canvas": {"title": "Weekend", "content": WEEKEND}},
            Panel(),
            "KeyError",
        ),
        (
            FakeServer().on(LIST, httpx.Response(200, text="<html>Bad gateway</html>")),
            {"create_canvas": {"title": "Weekend", "content": WEEKEND}},
            Panel(),
            "JSONDecodeError",
        ),
        (
            FakeServer().on(ART, canvas(WEEKEND), as_json({"version": None})),
            {"edit_canvas": {"old": "Clean", "new": "Empty"}},
            Panel("a1"),
            "TypeError",
        ),
        (
            FakeServer().on(LIST, as_json([{"title": "Weekend"}])),
            {"select_canvas": "fridge"},
            Panel(),
            "KeyError",
        ),
    ],
    ids=["made-without-an-id", "not-json", "saved-without-a-version", "listed-without-an-id"],
)
def test_an_answer_the_panel_cannot_read_fails_the_run_without_stopping_the_eval(
    server, raw, panel, unread
):
    error = run_step(server, raw, panel)

    action = next(iter(raw))
    assert error.startswith(f"{action}: the server's answer cannot be read ({unread}")
    assert not stalled(RunResult(1, (Failure(RUN, error),)))


def test_a_server_that_cannot_be_reached_raises_as_a_lost_turn_does():
    def refuse() -> httpx.Response:
        raise httpx.ConnectError("refused")

    server = FakeServer().on(ART, refuse)

    with pytest.raises(httpx.ConnectError):
        run_step(server, {"select_canvas": "fridge"}, Panel("a1"))


@pytest.mark.parametrize(
    ("text", "start", "end"),
    [("Wash the curtains", 3, 3), ("Clean the fridge\n- Wash", 2, 3), ("Weekend", 1, 1)],
)
def test_select_canvas_sends_the_lines_of_the_passage_with_the_next_message_only(text, start, end):
    server = FakeServer().on(ART, canvas(WEEKEND, version=2))
    panel = Panel("a1")

    assert run_step(server, {"select_canvas": text}, panel) == ""

    picked = {"version": 2, "text": text, "line_start": start, "line_end": end}
    assert panel.carry() == {"canvas": {"artifact_id": "a1", "selection": picked}}
    assert panel.carry() == {"canvas": {"artifact_id": "a1", "selection": None}}
    assert ("PUT", ART) not in server.calls()


def test_a_selection_found_more_than_once_fails_the_run():
    server = FakeServer().on(ART, canvas("- Wash\n- Wash\n"))

    assert "2 times" in run_step(server, {"select_canvas": "Wash"}, Panel("a1"))


def test_before_any_canvas_is_open_a_message_carries_nothing_and_leaves_the_conversations_own():
    assert Panel().carry() == {}


def test_a_selection_stays_with_its_canvas_and_is_dropped_when_another_one_opens():
    picked = {"version": 1, "text": "x", "line_start": 1, "line_end": 1}
    same, other = Panel("a1", dict(picked)), Panel("a1", dict(picked))

    same.open("a1")
    other.open("a2")

    assert same.carry() == {"canvas": {"artifact_id": "a1", "selection": picked}}
    assert other.carry() == {"canvas": {"artifact_id": "a2", "selection": None}}


def test_each_message_owes_a_note_of_what_the_person_made_saved_and_selected_since_the_last():
    edited = WEEKEND.replace("curtains", "blankets")
    server = (
        FakeServer()
        .on(LIST, canvas(WEEKEND))
        .on(ART, canvas(WEEKEND), as_json({"version": 2}), canvas(edited, version=2))
    )
    panel = Panel()

    run_step(server, {"create_canvas": {"title": "Weekend", "content": WEEKEND}}, panel)
    run_step(server, {"edit_canvas": {"old": "curtains", "new": "blankets"}}, panel)
    panel.carry()
    panel.carry()
    run_step(server, {"select_canvas": "Clean the fridge"}, panel)
    panel.carry()

    assert panel.due == [NoteDue({"a1": 2}), NoteDue(), NoteDue({}, "Clean the fridge")]


def test_a_message_before_any_canvas_owes_nothing_and_two_new_canvases_are_both_owed():
    server = FakeServer().on(LIST, canvas("- a\n"), canvas("- b\n", artifact_id="a2"))
    panel = Panel()

    panel.carry()
    run_step(server, {"create_canvas": {"title": "A", "content": "- a\n"}}, panel)
    run_step(server, {"create_canvas": {"title": "B", "content": "- b\n"}}, panel)
    panel.carry()

    assert panel.due == [NoteDue(), NoteDue({"a1": 1, "a2": 1})]


# --- what the canvases hold ---------------------------------------------------------------


def test_canvas_contains_ignores_case_and_accents_and_looks_in_every_canvas():
    canvases = ["# Việc\n- Tưới cây\n", "- Gọi điện cho bà\n"]

    assert judge({"canvas_contains": ["tuoi cay", "GỌI ĐIỆN cho ba"]}, canvases) == []
    missed = judge({"canvas_contains": ["giặt chăn"]}, canvases)
    assert [f.assertion for f in missed] == ["canvas_contains"]
    assert "giặt chăn" in missed[0].detail


def test_canvas_not_contains_fails_when_any_canvas_still_holds_it():
    failures = judge({"canvas_not_contains": ["31/2"]}, ["fine", "on Saturday 31/2"])

    assert [f.assertion for f in failures] == ["canvas_not_contains"]
    assert judge({"canvas_not_contains": ["31/2"]}, ["on Saturday 28/2"]) == []


def test_canvas_count_is_the_number_of_canvases_the_conversation_has():
    failures = judge({"canvas_count": 1}, ["one", "two"])

    assert [(f.assertion, f.detail) for f in failures] == [("canvas_count", "2 canvases, not 1")]
    assert [f.detail for f in judge({"canvas_count": 0}, ["one"])] == ["1 canvas, not 0"]
    assert judge({"canvas_count": 0}, []) == []


LUNCH = Canvas(
    "Lunch plan",
    "# Lunch plan\n\n"
    "- Monday: chicken rice with greens\n"
    "- Tuesday: beef noodle soup, extra herbs\n"
    "- Wednesday: grilled fish and rice\n"
    "- Thursday: pho\n",
)


def test_a_reply_that_pastes_a_canvas_fails_whatever_the_markup_and_names_the_canvas():
    reply = (
        "Here it is:\n1. **Monday**: chicken rice with greens\n"
        "2. Tuesday: Beef noodle soup, extra herbs\n* Wednesday:  grilled fish and rice"
    )

    assert pasted_share(LUNCH, reply) == 14 / 16
    (failure,) = judge({"canvas_not_in_chat": True}, [LUNCH], reply)
    assert (failure.assertion, failure.detail) == (
        "canvas_not_in_chat",
        "the chat repeats 88% of the canvas 'Lunch plan'",
    )
    assert judge({}, [LUNCH], reply) == []


def test_a_canvas_pasted_over_two_messages_is_still_in_the_chat():
    pasted = "Writing it:\nMonday: chicken rice with greens\nTuesday: beef noodle soup, extra herbs"
    later = "Wednesday: grilled fish and rice. Done, it is in the canvas."

    assert [f.assertion for f in judge({"canvas_not_in_chat": True}, [LUNCH], pasted, later)] == [
        "canvas_not_in_chat"
    ]


def test_quoting_one_line_or_naming_short_lines_is_not_a_paste():
    one = "I added: Wednesday: grilled fish and rice."
    short = "Thursday: pho, and the Lunch plan title."

    assert pasted_share(LUNCH, one) == 0.0
    assert pasted_share(LUNCH, short) == 0.0
    assert pasted_share(LUNCH, one, short) == 0.0  # no run of words spans two messages
    assert judge({"canvas_not_in_chat": True}, [LUNCH], one, short) == []


def test_each_canvas_is_judged_on_its_own_and_the_one_pasted_is_named():
    weekend = Canvas("Weekend", "- Clean out the fridge on Saturday\n- Wash the blankets\n")
    said = "Sure: clean out the fridge on Saturday, wash the blankets."

    failures = judge({"canvas_not_in_chat": True}, [LUNCH, weekend], said)

    assert [f.detail for f in failures] == ["the chat repeats 100% of the canvas 'Weekend'"]
