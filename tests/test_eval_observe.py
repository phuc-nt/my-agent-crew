"""What one eval run did, read back from the JSON the server already serves."""

from __future__ import annotations

from typing import Any

from eval_check import Ask, Call, Delegate
from eval_observe import child_ids, observe
from eval_paste import Canvas

from my_agent_crew.texts import LOOP_REDIRECT
from my_agent_crew.tools.delegate_outcome import NEEDS_CONTEXT, Outcome, outcome_line


def message(seq: int, role: str, content: str = "", calls: list[dict] | None = None, **extra: Any):
    return {
        "id": f"m{seq}",
        "seq": seq,
        "role": role,
        "content": content,
        "tool_calls": calls or [],
        "tool_call_id": extra.get("tool_call_id"),
        "name": extra.get("name"),
    }


def tool_call(call_id: str, name: str, **arguments: Any) -> dict:
    return {"id": call_id, "name": name, "arguments": arguments}


ROOT = {
    "id": "conv-1",
    "agent_id": "default",
    "messages": [
        message(1, "user", "log my run"),
        message(2, "assistant", "", [tool_call("t1", "workspace_read", path="log.md")]),
        message(3, "tool", "text", tool_call_id="t1", name="workspace_read"),
        message(4, "assistant", "Logged."),
        message(5, "user", "and look it up"),
        message(6, "assistant", "", [tool_call("t2", "delegate", task="look it up", agent="ada")]),
        message(7, "tool", "result", tool_call_id="t2", name="delegate"),
        message(8, "assistant", "Here it is."),
    ],
}
SENT = ("log my run", "and look it up")
CHILD = {
    "id": "conv-2",
    "agent_id": "ada",
    "parent_call_id": "t2",
    "messages": [
        message(1, "user", "look it up"),
        message(2, "assistant", "", [tool_call("c1", "web_search", query="x")]),
        message(3, "tool", "hits", tool_call_id="c1", name="web_search"),
        message(4, "assistant", "found it"),
    ],
}


def test_tool_calls_carry_the_turn_and_the_agent_that_made_them():
    seen = observe(ROOT, [CHILD], [], sent=SENT, spent_usd=0.0)

    assert seen.tool_calls == (
        Call(1, "default", "workspace_read", {"path": "log.md"}),
        Call(2, "default", "delegate", {"task": "look it up", "agent": "ada"}),
        Call(2, "ada", "web_search", {"query": "x"}),
    )


def test_a_child_conversation_is_a_delegation_to_its_agent():
    assert observe(ROOT, [CHILD], [], sent=SENT, spent_usd=0.0).delegates == (
        Delegate("ada", None),
    )
    assert observe(ROOT, [], [], sent=SENT, spent_usd=0.0).delegates == ()


def test_a_delegation_carries_the_outcome_its_result_reported():
    unfinished = outcome_line(Outcome(NEEDS_CONTEXT, "thiếu ngày"))
    result = f"conversation=conv-2 status=done spent=$0.0010 steps=2\n{unfinished}\nfound it"
    answered = message(7, "tool", result, tool_call_id="t2", name="delegate")
    root = {**ROOT, "messages": [*ROOT["messages"][:6], answered, ROOT["messages"][7]]}

    assert observe(root, [CHILD], [], sent=SENT, spent_usd=0.0).delegates == (
        Delegate("ada", "needs_context"),
    )


def test_the_reply_is_the_last_text_of_the_last_turn():
    assert observe(ROOT, [], [], sent=SENT, spent_usd=0.0).reply == "Here it is."


def test_an_earlier_turns_text_is_not_the_reply_of_a_turn_that_said_nothing():
    silent = {
        **ROOT,
        "messages": [
            *ROOT["messages"][:4],
            message(5, "user", "again"),
            message(6, "assistant", "", [tool_call("t9", "workspace_read", path="x")]),
        ],
    }

    assert observe(silent, [], [], sent=("log my run", "again"), spent_usd=0.0).reply == ""


def test_the_reply_skips_a_final_message_that_only_called_tools():
    unfinished = {
        **ROOT,
        "messages": [
            message(1, "user", "go"),
            message(2, "assistant", "Working on it."),
            message(3, "assistant", "", [tool_call("t9", "workspace_read", path="x")]),
        ],
    }

    assert observe(unfinished, [], [], sent=("go",), spent_usd=0.0).reply == "Working on it."


def test_a_child_whose_parent_call_is_unknown_is_put_in_the_last_turn():
    orphan = {**CHILD, "parent_call_id": "gone"}

    seen = observe(ROOT, [orphan], [], sent=SENT, spent_usd=0.0)

    assert Call(2, "ada", "web_search", {"query": "x"}) in seen.tool_calls


def test_only_tool_approvals_count_as_asks_and_they_keep_the_turn_they_came_in():
    approvals = [
        {"kind": "tool", "turn": 1, "name": "shell_run", "arguments": {"command": "rm x"}},
        {"kind": "question", "turn": 1, "name": "ask_user", "arguments": {"question": "?"}},
        {"kind": "tool", "turn": 2, "name": "workspace_write", "arguments": {"path": "a"}},
    ]

    assert observe(ROOT, [], approvals, sent=SENT, spent_usd=0.0).approvals == (
        Ask(1, "shell_run", {"command": "rm x"}),
        Ask(2, "workspace_write", {"path": "a"}),
    )


def test_said_is_every_text_the_agent_wrote_and_each_canvas_keeps_its_title_and_text():
    canvases = [
        {"id": "a1", "title": "Plan", "kind": "markdown", "head_version": 2, "content": "# Plan\n"},
        {"id": "a2", "title": "Page", "kind": "html", "head_version": 1, "content": None},
    ]
    seen = observe(ROOT, [CHILD], [], sent=SENT, spent_usd=0.0, canvases=canvases)

    assert seen.said == ("Logged.", "Here it is.")
    assert seen.canvases == (Canvas("Plan", "# Plan\n"), Canvas("Page", ""))


def test_cost_and_error_are_carried_through():
    seen = observe(
        ROOT, [], [], sent=SENT, spent_usd=0.0123, unknown_cost_calls=2, error="halted: loop"
    )

    assert (seen.spent_usd, seen.unknown_cost_calls, seen.error) == (0.0123, 2, "halted: loop")


def guarded(*after_the_note: dict) -> dict:
    """A turn where the loop guard stepped in: the same edit three times, then the guard's
    note, which the server stores as the person's message, then what `after_the_note` holds."""
    edits = []
    for seq, call in ((2, "t1"), (4, "t2"), (6, "t3")):
        edits.append(message(seq, "assistant", "", [tool_call(call, "artifact_edit", old="a")]))
        edits.append(message(seq + 1, "tool", "not found", tool_call_id=call, name="artifact_edit"))
    note = LOOP_REDIRECT.format(names="artifact_edit", count=3)
    messages = [message(1, "user", "fix the date"), *edits, message(8, "user", note)]
    return {**ROOT, "messages": [*messages, *after_the_note]}


def test_a_note_the_server_writes_as_the_persons_message_does_not_start_a_turn():
    root = guarded(
        message(9, "assistant", "", [tool_call("t4", "artifact_read")]),
        message(10, "tool", "the canvas", tool_call_id="t4", name="artifact_read"),
        message(11, "assistant", "Fixed."),
        message(12, "user", "thanks, now the title"),
        message(13, "assistant", "", [tool_call("t5", "artifact_rewrite", title="x")]),
        message(14, "tool", "done", tool_call_id="t5", name="artifact_rewrite"),
        message(15, "assistant", "Done."),
    )
    orphan = {**CHILD, "parent_call_id": "gone"}

    seen = observe(root, [orphan], [], sent=("fix the date", "thanks, now the title"), spent_usd=0)

    assert [(call.turn, call.name) for call in seen.tool_calls] == [
        (1, "artifact_edit"),
        (1, "artifact_edit"),
        (1, "artifact_edit"),
        (1, "artifact_read"),
        (2, "artifact_rewrite"),
        (2, "web_search"),
    ]
    assert (seen.reply, seen.error) == ("Done.", "")


def test_the_reply_is_not_cut_short_by_a_note_the_server_wrote():
    root = guarded(message(9, "assistant", "", [tool_call("t4", "artifact_read")]))
    root["messages"][1]["content"] = "Let me fix it."

    assert observe(root, [], [], sent=("fix the date",), spent_usd=0.0).reply == "Let me fix it."


def test_the_agent_saying_the_next_message_first_does_not_start_that_turn():
    root = {
        **ROOT,
        "messages": [
            message(1, "user", "say ok, then read the log"),
            message(2, "assistant", "ok", [tool_call("t1", "workspace_read", path="log.md")]),
            message(3, "tool", "text", tool_call_id="t1", name="workspace_read"),
            message(4, "user", "ok"),
            message(5, "assistant", "Good."),
        ],
    }

    seen = observe(root, [], [], sent=("say ok, then read the log", "ok"), spent_usd=0.0)

    assert seen.tool_calls == (Call(1, "default", "workspace_read", {"path": "log.md"}),)


def test_a_conversation_without_every_text_the_eval_sent_fails_the_run():
    more = (*SENT, "one more")

    lost = observe(ROOT, [], [], sent=more, spent_usd=0.0)
    halted = observe(ROOT, [], [], sent=more, spent_usd=0.0, error="halted: loop")

    assert lost.error == "the conversation holds 2 of the 3 messages the eval sent"
    assert halted.error == "halted: loop"


def test_child_ids_are_the_other_conversations_of_the_family_in_the_order_they_started():
    runs = [
        {"conversation_id": "conv-1", "started_at": "2026-09-29T10:00:00+00:00"},
        {"conversation_id": "conv-3", "started_at": "2026-09-29T10:00:02+00:00"},
        {"conversation_id": "conv-2", "started_at": "2026-09-29T10:00:01+00:00"},
        {"conversation_id": "conv-2", "started_at": "2026-09-29T10:00:03+00:00"},
    ]

    assert child_ids(runs, "conv-1") == ["conv-2", "conv-3"]
    assert child_ids([], "conv-1") == []
