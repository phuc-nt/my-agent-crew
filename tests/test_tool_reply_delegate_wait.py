"""A `delegate` whose wait for the child ran out fails with a result shaped like any other, so
the web has no opening to know it by: it reads the outcome line, then the sentence the body
opens with (`web/src/lib/tool-reply.ts`). This holds every word it reads to the tool's own, and
shows the one other result marked failed, which the tool does not fail the call for, opening
with other words."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator

import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.events import ToolResultEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.config import Route
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Completion, ToolCall
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store import Store
from my_agent_crew.texts import DELEGATE_CANVAS_MORE, DELEGATE_TIMEOUT, DELEGATE_UNFINISHED
from my_agent_crew.tools.delegate import DELEGATE_TOOL_NAME
from my_agent_crew.tools.delegate_outcome import FAILED, timed_out
from tests.conftest import collect
from tests.test_tool_reply_openings import fixed_words, web_constant
from tests.test_tools_delegate import agent, delegation_result, wait_until_paused, web_pattern

CANVAS = "[artifact 3f9a1c2b7d40 v1] Dàn ý"
MORE = DELEGATE_CANVAS_MORE.format(n=2)
WRITE = ToolCall("w", "workspace_write", {"path": "note.md", "content": "rpe 4"})
ASKS_TO_WRITE = '/tool workspace_write {"path": "x.txt", "content": "1"}'


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.fixture
def crew(deps_factory, store: Store) -> Callable[..., Runtime]:
    """A boss over a `worker` that says what its script says, three steps at most, and answers
    through the echo provider when it has none."""

    def build(*script: Completion) -> Runtime:
        base = deps_factory(routes=(Route("fake", "echo"),))
        worker = deps_factory(script=script, max_steps=3) if script else base
        agents = {
            "boss": agent(base, "boss", delegates=("worker",)),
            "worker": agent(worker, "worker"),
        }
        rt = Runtime(base.settings, store, agents, ActivityHub(store))
        rt.wire_delegation()
        return rt

    return build


def _read(output: str) -> tuple[str, list[str]]:
    """What the web reads of a result: the outcome on line 2, and the paragraphs under the
    blank line the canvases end at."""
    lines = output.split("\n")
    assert web_pattern("HEADER").fullmatch(lines[0]), output
    outcome = web_pattern("OUTCOME").fullmatch(lines[1])
    blank = lines.index("", 2)
    assert all(web_pattern("CANVAS").fullmatch(line) for line in lines[2:blank]), output
    return outcome[1], "\n".join(lines[blank + 1 :]).split("\n\n")


def _wait_runs_out(rt: Runtime, monkeypatch) -> None:
    """The child gets as far as asking to write, and the wait for it ends there."""
    real_wait = rt.hub.wait_finished

    async def runs_out(conv_id: str, timeout: float):
        await wait_until_paused(rt)
        return await real_wait(conv_id, 0.01)

    monkeypatch.setattr(rt.hub, "wait_finished", runs_out)


def test_the_web_reads_a_wait_that_ran_out_by_the_tools_own_words():
    wait, left_out = web_constant("WAIT_RAN_OUT"), web_constant("LEFT_OUT")
    assert web_constant("DELEGATE") == DELEGATE_TOOL_NAME
    assert web_constant("NOT_FINISHED") == FAILED
    assert wait == fixed_words(DELEGATE_TIMEOUT) and left_out == fixed_words(DELEGATE_CANVAS_MORE)
    # Each stands in a paragraph of its own, and the web looks for one past the other: neither
    # may be taken for the other, nor may the note a child stopped short is reported with.
    assert "\n" not in DELEGATE_TIMEOUT and "\n" not in DELEGATE_CANVAS_MORE
    assert not wait.startswith(left_out)
    assert not DELEGATE_UNFINISHED.startswith((wait, left_out))


@pytest.mark.parametrize(("canvases", "more"), [([], ""), ([CANVAS], ""), ([CANVAS], MORE)])
def test_a_wait_that_ran_out_fails_the_call_over_the_sentence_the_web_reads(
    canvases: list[str], more: str
):
    """Alone under the blank line, or past the count of the canvases the result left out."""
    result = timed_out("c9", None, canvases, more)

    outcome, paragraphs = _read(result.output)
    assert result.ok is False and outcome == web_constant("NOT_FINISHED")
    assert paragraphs == [*([more] if more else []), DELEGATE_TIMEOUT.format(conv_id="c9")]
    assert all(left.startswith(web_constant("LEFT_OUT")) for left in paragraphs[:-1])
    assert paragraphs[-1].startswith(web_constant("WAIT_RAN_OUT"))


async def test_a_turn_stores_a_wait_that_ran_out_as_the_failure_the_web_reads(crew, monkeypatch):
    """Through the loop: the reply goes out as a failure, and the thread holds it word for
    word under the tool's name, which is all the web has of it when it reads the thread back."""
    rt = crew()
    _wait_runs_out(rt, monkeypatch)
    parent = rt.store.create(agent_id="boss", autonomous=False)
    asked = json.dumps({"task": ASKS_TO_WRITE, "agent": "worker"})

    turn = run_turn(rt.deps_for("boss"), parent.id, f"/tool {DELEGATE_TOOL_NAME} {asked}")
    [result] = [event for event in await collect(turn) if isinstance(event, ToolResultEvent)]

    child = rt.store.for_parent_call(result.tool_call_id)
    outcome, paragraphs = _read(result.output)
    assert result.ok is False and result.name == web_constant("DELEGATE")
    assert outcome == web_constant("NOT_FINISHED")
    assert paragraphs == [DELEGATE_TIMEOUT.format(conv_id=child.id)]
    assert paragraphs[0].startswith(web_constant("WAIT_RAN_OUT"))
    stored = [held.message for held in rt.store.history(parent.id) if held.message.role == "tool"]
    assert [(said.name, said.content) for said in stored] == [(DELEGATE_TOOL_NAME, result.output)]


async def test_a_child_stopped_short_does_not_fail_the_call_and_opens_with_its_own_note(crew):
    """The same outcome line, over a body the web must not read as a wait that ran out."""
    rt = crew(*(completion(tool_calls=(WRITE,)) for _ in range(3)))
    parent = rt.store.create(agent_id="boss", autonomous=True)

    result = await delegation_result(rt, parent.id, "call-1", task="ghi RPE 4", agent="worker")

    outcome, paragraphs = _read(result.output)
    assert result.ok is True and outcome == web_constant("NOT_FINISHED")
    assert paragraphs[0].startswith(fixed_words(DELEGATE_UNFINISHED))
    assert not paragraphs[0].startswith((web_constant("WAIT_RAN_OUT"), web_constant("LEFT_OUT")))
