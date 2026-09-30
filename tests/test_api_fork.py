"""The fork route over HTTP: `POST /api/conversations/{id}/fork` hands back the new
conversation plus the cut message's own text as a draft, closes an open call before the
fork is returned, and leaves nothing behind when either step fails."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import Route
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.server import create_app
from my_agent_crew.texts import FORK_CALL_NOT_RUN
from my_agent_crew.tools.output_spill import Spill, sweep
from my_agent_crew.tools.registry import Tool, ToolResult

CALL_A, CALL_B = ToolCall("a1", "slow", {}), ToolCall("b1", "counter", {})


def user(text: str) -> Message:
    return Message(role="user", content=text)


def assistant(*, tool_calls: tuple[ToolCall, ...] = ()) -> Message:
    return Message(role="assistant", content="", tool_calls=tool_calls)


def tool(call_id: str, name: str) -> Message:
    return Message(role="tool", content="xong", tool_call_id=call_id, name=name)


@pytest.fixture
def client(deps_factory):
    deps = deps_factory(routes=(Route("fake", "echo"),))
    with TestClient(create_app(deps), base_url="http://127.0.0.1") as c:
        yield c, deps


def new_conversation(client: TestClient, **overrides: Any) -> str:
    return client.post("/api/conversations", json=overrides).json()["id"]


def fork(client: TestClient, conv_id: str, before_message_id: int):
    return client.post(
        f"/api/conversations/{conv_id}/fork", json={"before_message_id": before_message_id}
    )


def test_forking_returns_the_new_conversation_and_the_cut_messages_own_text(client):
    c, deps = client
    conv_id = new_conversation(c)
    deps.store.append(conv_id, user("một"))
    cut = deps.store.append(conv_id, user("hỏi lại")).id

    response = fork(c, conv_id, cut)

    assert response.status_code == 201
    body = response.json()
    assert body["draft"] == "hỏi lại"
    assert body["forked_from"] == conv_id
    assert body["id"] != conv_id
    history = c.get(f"/api/conversations/{body['id']}").json()["messages"]
    assert [m["content"] for m in history] == ["một"]


@pytest.mark.parametrize("default", [False, True])
def test_the_fork_runs_on_its_own_only_when_the_agent_default_says_so(deps_factory, default):
    deps = deps_factory(routes=(Route("fake", "echo"),), autonomous_default=default)
    with TestClient(create_app(deps), base_url="http://127.0.0.1") as c:
        conv_id = new_conversation(c, autonomous=not default)
        cut = deps.store.append(conv_id, user("hỏi")).id

        response = fork(c, conv_id, cut)

    assert response.status_code == 201
    assert response.json()["autonomous"] is default


def test_unknown_conversation_is_404(client):
    c, _ = client
    assert fork(c, "khong-co", 1).status_code == 404


def test_unknown_message_id_is_404(client):
    c, deps = client
    conv_id = new_conversation(c)
    cut = deps.store.append(conv_id, user("hỏi")).id
    assert fork(c, conv_id, cut + 1000).status_code == 404


def test_a_message_belonging_to_another_conversation_is_404(client):
    c, deps = client
    conv_id, other_id = new_conversation(c), new_conversation(c)
    other_cut = deps.store.append(other_id, user("hỏi")).id
    assert fork(c, conv_id, other_cut).status_code == 404


def test_cutting_at_a_non_user_message_is_400(client):
    c, deps = client
    conv_id = new_conversation(c)
    deps.store.append(conv_id, user("hỏi"))
    reply = deps.store.append(conv_id, Message(role="assistant", content="trả lời"))
    assert fork(c, conv_id, reply.id).status_code == 400


def test_forking_a_delegated_child_is_400(client):
    c, deps = client
    child = deps.store.create(parent_call_id="a1")
    cut = deps.store.append(child.id, user("việc")).id
    assert fork(c, child.id, cut).status_code == 400


def test_before_message_id_must_be_a_positive_integer(client):
    c, _ = client
    conv_id = new_conversation(c)
    for bad in (0, -1):
        response = c.post(f"/api/conversations/{conv_id}/fork", json={"before_message_id": bad})
        assert response.status_code == 422


def test_an_open_call_is_closed_and_never_run_again(deps_factory):
    """FM-10: `[user, assistant(A,B), tool(A), user]` cut at the second user message copies
    `[user, assistant(A,B), tool(A)]` with B still open; the route closes B before handing
    the fork back, and running a turn on the fork must not call the counting tool at all."""
    counter = {"runs": 0}

    async def _count(args: dict[str, object]) -> ToolResult:
        counter["runs"] += 1
        return ToolResult(ok=True, output="đếm rồi")

    counting_tool = Tool("counter", "Đếm số lần gọi.", {"type": "object", "properties": {}}, _count)
    deps = deps_factory(
        routes=(Route("scripted", "m"),),
        extra_tools=[counting_tool],
        script=[completion("không cần gọi thêm")],
    )
    with TestClient(create_app(deps), base_url="http://127.0.0.1") as c:
        conv_id = new_conversation(c)
        deps.store.append(conv_id, user("việc 1"))
        deps.store.append(conv_id, assistant(tool_calls=(CALL_A, CALL_B)))
        deps.store.append(conv_id, tool("a1", "slow"))
        cut = deps.store.append(conv_id, user("việc 2")).id

        response = fork(c, conv_id, cut)
        assert response.status_code == 201
        fork_id = response.json()["id"]

        # The route has already closed B by the time it answers: the copy itself ends on
        # the open tool(A), and the route's own refuse_unanswered appends the closing
        # tool(B) right after, so what the fork holds now is the copy plus that closure.
        history = deps.store.history(fork_id)
        assert [m.message.role for m in history] == ["user", "assistant", "tool", "tool"]
        assert history[-1].message.tool_call_id == "b1"
        assert history[-1].message.content == FORK_CALL_NOT_RUN

        sent = c.post(f"/api/conversations/{fork_id}/messages", json={"text": "tiếp tục"})
        assert sent.status_code == 200
        assert counter["runs"] == 0
        closed = [m for m in deps.store.history(fork_id) if m.message.tool_call_id == "b1"]
        assert len(closed) == 1  # not closed a second time by settle_tool_calls


def test_a_refusal_that_fails_to_write_leaves_no_fork_behind(client, monkeypatch):
    """AD-6 at the route: forcing `refuse_unanswered` to raise must not leave a half-built
    fork sitting in the list. `TestClient` re-raises a handler's own exception rather than
    turning it into a response body, same as it would for any other unhandled server error;
    what matters here is that no fork survives it."""
    c, deps = client
    conv_id = new_conversation(c)
    deps.store.append(conv_id, assistant(tool_calls=(CALL_A,)))
    cut = deps.store.append(conv_id, user("hỏi")).id
    before_ids = {conv.id for conv in deps.store.list()}

    def boom(*args, **kwargs):
        raise RuntimeError("đóng lỗi")

    monkeypatch.setattr("my_agent_crew.server.routes_fork.refuse_unanswered", boom)

    with pytest.raises(RuntimeError, match="đóng lỗi"):
        fork(c, conv_id, cut)

    assert {conv.id for conv in deps.store.list()} == before_ids


def _spill_files(deps, conv_id: str) -> list[str]:
    folder = deps.settings.home / "spill" / conv_id
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


def test_deleting_a_conversation_removes_its_spill_folder(client):
    c, deps = client
    conv_id = new_conversation(c)
    other = new_conversation(c)
    Spill(deps.settings.home).write(conv_id, "call1", "x" * 10)
    Spill(deps.settings.home).write(other, "call1", "y" * 10)

    assert c.delete(f"/api/conversations/{conv_id}").status_code == 204

    assert _spill_files(deps, conv_id) == []
    assert not (deps.settings.home / "spill" / conv_id).exists()
    assert len(_spill_files(deps, other)) == 1


def test_deleting_an_unknown_conversation_is_404_and_touches_no_spill_folder(client):
    c, deps = client
    conv_id = new_conversation(c)
    Spill(deps.settings.home).write(conv_id, "call1", "x" * 10)

    assert c.delete("/api/conversations/nope").status_code == 404

    assert len(_spill_files(deps, conv_id)) == 1


def test_forking_copies_the_spill_files_to_the_fork(client):
    c, deps = client
    conv_id = new_conversation(c)
    cut = deps.store.append(conv_id, user("hỏi")).id
    Spill(deps.settings.home).write(conv_id, "call1", "bản gốc")

    fork_id = fork(c, conv_id, cut).json()["id"]

    assert _spill_files(deps, fork_id) == _spill_files(deps, conv_id) != []
    assert Spill(deps.settings.home).read(fork_id, "call1") == "bản gốc"


def test_a_failed_spill_copy_does_not_break_the_fork(client, monkeypatch):
    c, deps = client
    conv_id = new_conversation(c)
    cut = deps.store.append(conv_id, user("hỏi")).id
    Spill(deps.settings.home).write(conv_id, "call1", "bản gốc")

    def broken(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("my_agent_crew.tools.output_spill.shutil.copyfile", broken)

    response = fork(c, conv_id, cut)

    assert response.status_code == 201
    assert c.get(f"/api/conversations/{response.json()['id']}").status_code == 200


def test_a_fork_still_reads_the_original_after_its_source_is_deleted_and_swept(client):
    c, deps = client
    conv_id = new_conversation(c)
    cut = deps.store.append(conv_id, user("hỏi")).id
    spill = Spill(deps.settings.home)
    spill.write(conv_id, "call1", "bản gốc")
    fork_id = fork(c, conv_id, cut).json()["id"]

    assert c.delete(f"/api/conversations/{conv_id}").status_code == 204
    assert sweep(deps.settings.home) == 0

    assert spill.read(fork_id, "call1") == "bản gốc"
    assert spill.read(conv_id, "call1") is None
