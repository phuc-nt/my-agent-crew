"""What a delegated task came to, as opposed to how the child's run ended: what the child
declared in its closing `Status:` line, and what the runtime knows for certain."""

from __future__ import annotations

from dataclasses import replace

import pytest

from my_agent_crew.store.approvals import APPROVED, DENIED, EXPIRED
from my_agent_crew.store.models import QUESTION, Approval
from my_agent_crew.store.runs import DONE, FAILED, HALTED, RunRecord
from my_agent_crew.texts import DELEGATE_CANVAS_MORE, DELEGATE_TIMEOUT
from my_agent_crew.tools.delegate_outcome import (
    BLOCKED,
    DONE_WITH_CONCERNS,
    NEEDS_CONTEXT,
    Outcome,
    decide,
    declared_outcome,
    outcome_line,
    relays,
    result_text,
    timed_out,
)
from my_agent_crew.tools.delegate_outcome import DONE as OUTCOME_DONE
from my_agent_crew.tools.delegate_outcome import FAILED as OUTCOME_FAILED


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("Đã ghi.\n\nStatus: DONE", Outcome(OUTCOME_DONE)),
        ("Đã ghi.\n**Status:** DONE", Outcome(OUTCOME_DONE)),
        ("Đã ghi.\n**Status: DONE**", Outcome(OUTCOME_DONE)),
        ("Đã ghi.\nstatus: done", Outcome(OUTCOME_DONE)),
        ("Status:DONE", Outcome(OUTCOME_DONE)),
        ("- Status: BLOCKED — cần duyệt", Outcome(BLOCKED, "cần duyệt")),
        ("> Status: NEEDS_CONTEXT: thiếu ngày", Outcome(NEEDS_CONTEXT, "thiếu ngày")),
        ("* **Status:** BLOCKED, cần bạn đồng ý", Outcome(BLOCKED, "cần bạn đồng ý")),
        (
            "Chưa làm được.\n**Status**: NEEDS_CONTEXT\n**Summary**: thiếu ngày",
            Outcome(NEEDS_CONTEXT, "thiếu ngày"),
        ),
        (
            "Xong.\n**Status**: DONE_WITH_CONCERNS\n**Summary**: thiếu 2 ngày",
            Outcome(DONE_WITH_CONCERNS, "thiếu 2 ngày"),
        ),
        (
            "Xong.\nStatus: DONE WITH CONCERNS\nSummary: thiếu 2 ngày",
            Outcome(DONE_WITH_CONCERNS, "thiếu 2 ngày"),
        ),
        ("Xong.\nStatus: DONE-WITH-CONCERNS", Outcome(DONE_WITH_CONCERNS)),
        (
            "Thiếu.\nStatus: NEEDS CONTEXT\nSummary: thiếu tài khoản",
            Outcome(NEEDS_CONTEXT, "thiếu tài khoản"),
        ),
        ("Thiếu.\nStatus: `NEEDS_CONTEXT`", Outcome(NEEDS_CONTEXT)),
        ("Thiếu.\nStatus: ⚠️ NEEDS_CONTEXT", Outcome(NEEDS_CONTEXT)),
        ("Thiếu.\n## Status: NEEDS_CONTEXT", Outcome(NEEDS_CONTEXT)),
        (
            "Status: BLOCKED\n**Summary**: cần quyền tạo bảng",
            Outcome(BLOCKED, "cần quyền tạo bảng"),
        ),
        ("Status: **DONE**", Outcome(OUTCOME_DONE)),
    ],
)
def test_the_status_line_is_read_in_every_way_a_model_writes_it(answer: str, expected: Outcome):
    assert declared_outcome(answer) == expected


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (
            "Bảng việc:\n```\nGọi điện\nStatus: done\n```\n"
            "**Status**: BLOCKED\n**Summary**: cần quyền",
            Outcome(BLOCKED, "cần quyền"),
        ),
        (
            "Bảng việc:\n```\nStatus: done\n```\n**Status**: NEEDS_CONTEXT\n**Summary**: thiếu số",
            Outcome(NEEDS_CONTEXT, "thiếu số"),
        ),
        (
            "Status: BLOCKED\nSummary: cần quyền\n\nBản nháp:\n```\nStatus: DONE\n```",
            Outcome(BLOCKED, "cần quyền"),
        ),
    ],
)
def test_a_status_line_in_a_code_block_does_not_speak_over_the_closing_one(
    answer: str, expected: Outcome
):
    """What sits in a code block is what the child is showing, a task list or a draft; the
    closing lines outside it are what the child says about its own task."""
    assert declared_outcome(answer) == expected


def test_a_closing_block_the_child_put_in_a_code_block_still_counts():
    """The skill shows the closing block inside a fence, and a model copies that."""
    answer = "Đã đọc xong.\n```\nStatus: BLOCKED\nSummary: cần quyền ghi\n```"

    assert declared_outcome(answer) == Outcome(BLOCKED, "cần quyền ghi")


def test_a_lowercase_status_in_a_code_block_is_content_not_a_declaration():
    """A ticket or a YAML file the child wrote can have a `status:` field; the closing
    block writes its value in capitals, as the skill does."""
    answer = "Đã tạo phiếu:\n```yaml\ntitle: Đăng nhập lỗi\nstatus: blocked\n```"

    assert declared_outcome(answer) is None


def test_done_with_concerns_is_not_read_as_done():
    answer = "Xong phần lớn.\nStatus: DONE_WITH_CONCERNS\nSummary: bảng tháng 8 thiếu hai ngày"

    assert declared_outcome(answer) == Outcome(DONE_WITH_CONCERNS, "bảng tháng 8 thiếu hai ngày")


@pytest.mark.parametrize("word", ["DONE_FOO", "DONEISH", "MAYBE"])
def test_a_status_the_contract_does_not_name_is_not_a_declaration(word: str):
    assert declared_outcome(f"Kết quả.\nStatus: {word}") is None


def test_the_last_status_line_wins():
    answer = "Status: BLOCKED\nNgười dùng đồng ý rồi, tôi làm tiếp.\nStatus: DONE"

    assert declared_outcome(answer) == Outcome(OUTCOME_DONE)


def test_an_unknown_status_after_a_valid_one_leaves_the_valid_one_standing():
    answer = "Status: NEEDS_CONTEXT\nSummary: thiếu ngày\nStatus: MAYBE"

    assert declared_outcome(answer) == Outcome(NEEDS_CONTEXT, "thiếu ngày")


def test_the_reason_is_the_summary_line_when_the_status_line_has_none():
    answer = "Status: BLOCKED\n\nSummary: cần quyền tạo bảng\nConcerns/Blockers: chưa có bảng"

    assert declared_outcome(answer) == Outcome(BLOCKED, "cần quyền tạo bảng")


def test_the_reason_is_one_line_and_cut_like_the_unfinished_note():
    long = "chữ " * 100
    reason = declared_outcome(f"Status: BLOCKED — {long}").reason

    assert "\n" not in reason and reason.endswith("…") and len(reason) == 161


def test_an_answer_that_is_only_the_status_line_is_still_read():
    assert declared_outcome("Status: NEEDS_CONTEXT") == Outcome(NEEDS_CONTEXT)


def test_a_bare_blocked_word_counts_when_there_is_no_status_line():
    assert declared_outcome("(echo) BLOCKED: cần bạn đồng ý") == Outcome(BLOCKED, "cần bạn đồng ý")


@pytest.mark.parametrize(
    "answer",
    ["Việc bị blocked vì thiếu quyền", "Đã UNBLOCKED hàng đợi", "cờ BLOCKED_BY vẫn còn", "Xong."],
)
def test_other_spellings_of_blocked_and_plain_answers_declare_nothing(answer: str):
    assert declared_outcome(answer) is None


def test_a_status_line_beats_the_word_blocked_in_the_prose():
    """Before this, the substring alone held a relay back wherever it appeared."""
    answer = "Tệp từng BLOCKED do khoá, giờ đã mở và ghi xong.\nStatus: DONE"

    assert declared_outcome(answer) == Outcome(OUTCOME_DONE)


def run_ending(status: str, summary: str = "") -> RunRecord:
    return RunRecord(
        "r1", "worker", "c1", "delegate:p", "t", status, "2026-09-29T08:00:00", summary=summary
    )


def decision(status: str, tool: str = "workspace_write") -> Approval:
    return Approval("a1", "c1", 1, "t1", tool, {}, status, "2026-09-29T08:00:00")


def test_a_run_that_did_not_finish_failed_whatever_the_child_wrote():
    declared = Outcome(OUTCOME_DONE)

    assert decide(run_ending(HALTED, "loop"), declared, None) == Outcome(OUTCOME_FAILED, "loop")
    assert decide(run_ending(FAILED, "boom"), None, None) == Outcome(OUTCOME_FAILED, "boom")
    assert decide(run_ending(FAILED), None, None) == Outcome(OUTCOME_FAILED, FAILED)


@pytest.mark.parametrize("status", [DENIED, EXPIRED])
def test_a_refused_or_lapsed_last_decision_blocks_a_run_that_says_done(status: str):
    blocked = decide(run_ending(DONE), Outcome(OUTCOME_DONE), decision(status))

    assert blocked == Outcome(BLOCKED, f"workspace_write {status}")


def test_an_approved_last_decision_leaves_the_declaration_standing():
    declared = Outcome(NEEDS_CONTEXT, "thiếu ngày")

    assert decide(run_ending(DONE), declared, decision(APPROVED)) == declared
    assert decide(run_ending(DONE), None, decision(APPROVED)) == Outcome(OUTCOME_DONE)


def test_a_question_nobody_answered_is_not_a_refusal():
    """A lapsed question lets the child carry on with its default, so the task may be done."""
    lapsed = replace(decision(EXPIRED, "ask_user"), kind=QUESTION)

    assert decide(run_ending(DONE), None, lapsed) == Outcome(OUTCOME_DONE)


def test_a_finished_run_that_declares_nothing_is_done():
    assert decide(run_ending(DONE), None, None) == Outcome(OUTCOME_DONE)


def test_only_done_is_handed_straight_to_the_person():
    assert relays(Outcome(OUTCOME_DONE))
    for status in (DONE_WITH_CONCERNS, BLOCKED, NEEDS_CONTEXT, OUTCOME_FAILED):
        assert not relays(Outcome(status, "lý do"))


def test_the_outcome_line_names_a_reason_only_when_the_task_is_not_done():
    assert outcome_line(Outcome(OUTCOME_DONE, "mọi thứ ổn")) == "outcome=done"
    assert outcome_line(Outcome(BLOCKED, "cần duyệt")) == "outcome=blocked reason=cần duyệt"
    assert outcome_line(Outcome(NEEDS_CONTEXT)) == "outcome=needs_context"


def test_a_wait_that_runs_out_fails_and_keeps_the_header_the_card_reads():
    result = timed_out("c9", None, [], "")

    assert not result.ok and result.reply is None
    assert result.output.split("\n") == [
        "conversation=c9 status=running spent=$0.0000 steps=0",
        "outcome=failed reason=timeout",
        "",
        DELEGATE_TIMEOUT.format(conv_id="c9"),
    ]


def test_a_wait_that_runs_out_names_the_canvases_written_so_far():
    canvas = "[artifact 3f9a1c2b7d40 v1] Dàn ý"
    more = DELEGATE_CANVAS_MORE.format(n=2)

    result = timed_out("c9", None, [canvas], more)

    assert not result.ok and result.reply is None
    assert result.output.split("\n")[1:] == [
        "outcome=failed reason=timeout",
        canvas,
        "",
        more,
        "",
        DELEGATE_TIMEOUT.format(conv_id="c9"),
    ]


def test_the_blank_line_is_there_whether_or_not_a_canvas_was_written():
    """Line 1, line 2, a line for each canvas, the blank line, the body. The count of the
    canvases left out opens the body as a paragraph of its own, below the blank line, so it
    is never read as one more canvas."""
    assert result_text("h", "o", [], "", "lời") == "h\no\n\nlời"
    assert result_text("h", "o", ("c1", "c2"), "", "lời\n\nthêm") == "h\no\nc1\nc2\n\nlời\n\nthêm"
    assert result_text("h", "o", ["c1"], "còn 2", "lời") == "h\no\nc1\n\ncòn 2\n\nlời"
