"""What the jobs reported, as the phone's inbox reads it: the words each run's turn sent to
the chat, and nothing for a run the chat was not sent (`activity/reports.py`)."""

from __future__ import annotations

from my_agent_crew.activity.reports import job_reports, turn_text
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store.db import Store
from my_agent_crew.store.runs import DONE, FAILED, RunRecord

STAMP = "2026-11-02T07:00:00+00:00"


def job_run(store: Store, run_id: str, conv_id: str | None, **fields) -> RunRecord:
    after = store.messages.max_seq(conv_id) if conv_id else None
    base = dict(
        id=run_id,
        agent_id="coach",
        conversation_id=conv_id,
        source="job:coach/brief",
        title=f"[lịch] {run_id}",
        status=DONE,
        started_at=STAMP,
        finished_at=STAMP,
        after_seq=after,
    )
    run = RunRecord(**(base | fields))
    store.runs.save(run)
    return run


def turn(store: Store, conv_id: str, *replies: Message) -> None:
    store.append(conv_id, Message(role="user", content="Viết bản tin sáng"))
    for reply in replies:
        store.append(conv_id, reply)


def say(text: str) -> Message:
    return Message(role="assistant", content=text)


def test_a_report_is_every_word_of_the_turn_in_order():
    store = Store()
    conv = store.create(title="[lịch] Bản tin").id
    run = job_run(store, "r1", conv)
    call = ToolCall(id="t1", name="shell_run", arguments={"command": "date"})
    turn(
        store,
        conv,
        Message(role="assistant", content="Đang xem lịch.", tool_calls=(call,)),
        Message(role="tool", content="07:00", tool_call_id="t1", name="shell_run"),
        say("**Hôm nay** có 3 cuộc họp."),
    )
    assert [r.to_dict() for r in job_reports(store)] == [
        {"run_id": run.id, "text": "Đang xem lịch.\n\n**Hôm nay** có 3 cuộc họp."}
    ]


def test_an_answer_given_later_in_its_conversation_is_not_the_report():
    store = Store()
    conv = store.create().id
    run = job_run(store, "r1", conv)
    turn(store, conv, say("Giá vàng tăng 2%."))
    store.append(conv, Message(role="user", content="Vì sao?"))
    store.append(conv, say("Vì USD giảm."))
    assert turn_text(store.history(conv), run.after_seq) == "Giá vàng tăng 2%."


def test_what_the_chat_was_not_sent_is_no_report():
    store = Store()
    quiet, failed = store.create().id, store.create().id
    job_run(store, "ok", quiet)
    turn(store, quiet, say("OK."))
    job_run(store, "failed", failed, status=FAILED)
    turn(store, failed, say("Hỏng giữa chừng"))
    job_run(store, "command", None, summary="synced 0 mail")
    job_run(store, "chat", store.create().id, source="web")
    assert job_reports(store) == []


def test_the_newest_come_first_and_the_limit_counts_reports():
    store = Store()
    for n in range(3):
        conv = store.create().id
        job_run(store, f"r{n}", conv, started_at=f"2026-11-02T0{n}:00:00+00:00")
        turn(store, conv, say(f"Tin {n}"))
    assert [r.run_id for r in job_reports(store, limit=2)] == ["r2", "r1"]
