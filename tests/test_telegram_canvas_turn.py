"""A canvas written away from the web, through the real loop and the real tools.

A Telegram turn and a scheduled job write canvases as a web turn does. The chat gets the
turn's words, then the canvas the reply names as a file, then the list of what the turn wrote.
These tests read what the chat received and what the store holds, and nothing of how the turn
got there. A job that wrote a canvas and has nothing to say is in `test_scheduler_reporting.py`.
"""

from __future__ import annotations

from my_agent_crew.agent.turn_context import JOB, TELEGRAM
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.artifacts.tag import TAG_RE
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.scheduler import Scheduler
from my_agent_crew.store.runs import DONE, RunRecord
from tests.canvas_helpers import PLAN
from tests.telegram_fake import Upload, message, poll_each
from tests.test_canvas_payload_trim import canvas_tools
from tests.test_scheduler import with_schedules
from tests.test_telegram_canvas_notice_sent import listed, messages_and_files

TITLE = "Kế hoạch tuần"
CREATE = ToolCall("a1", "artifact_create", {"title": TITLE, "kind": "markdown", "content": PLAN})
WEEKLY = Schedule("weekly-plan", TITLE, cron="30 7 * * 1", prompt="Lập kế hoạch tuần.")


class NamesWhatItWrote:
    """A model scripted by what it is shown. It makes a canvas, reads the canvas's id off the
    tool's result as a model does, and answers with `reply`, where `{id}` stands for that id.
    A tool that refused is answered with the refusal, so the chat shows what went wrong."""

    name = "scripted"

    def __init__(self, reply: str) -> None:
        self.reply = reply

    async def stream(self, messages, tools, model, reasoning=""):
        last = messages[-1]
        if last.role != "tool":
            answer = completion(tool_calls=(CREATE,))
        elif made := TAG_RE.match(last.content):
            answer = completion(self.reply.format(id=made[1]))
        else:
            answer = completion(last.content)
        async for item in ScriptedProvider([answer]).stream(messages, tools, model, reasoning):
            yield item


def the_one_canvas(store, source: str) -> str:
    """The id of the only canvas in the store, checked to be the plan the turn was scripted
    to write, by the default agent, in a conversation whose run came from `source`."""
    [made] = store.artifacts.list()
    head = store.artifacts.head(made.id)
    assert (made.title, made.agent_id, head.version, head.content) == (TITLE, "default", 1, PLAN)
    run = store.runs.latest_for_conversation(head.conversation_id)
    assert run is not None and run.source.split(":")[0] == source
    assert store.artifact_links.get(head.conversation_id, made.id) is not None
    return made.id


def sent_in_order(fake) -> list[str]:
    """The messages and files the chat was sent, in order, without the polling around them."""
    return [call for call in messages_and_files(fake) if call != "getUpdates"]


async def run_weekly(make_channel, deps) -> RunRecord:
    """Runs the weekly job with the channel as the place its brief is pushed to."""
    channel = make_channel(deps)

    async def deliver(agent_id: str, conv_id: str) -> bool:
        return await channel.deliver(conv_id)

    scheduler = Scheduler({"default": deps}, channel.hub, deliver=deliver)
    return await scheduler.run_job("default/weekly-plan")


async def test_a_telegram_turn_writes_a_canvas_and_sends_it_as_the_file_its_reply_names(
    make_channel, deps_factory, fake, store
):
    model = NamesWhatItWrote("Đã lập kế hoạch.\nFILE: artifact:{id}")
    deps = deps_factory(extra_tools=canvas_tools(store), providers={"scripted": model})
    channel = make_channel(deps)
    await poll_each(channel, fake, message(1, "lập kế hoạch tuần"))
    the_one_canvas(store, TELEGRAM)
    assert sent_in_order(fake) == ["sendMessage", "sendDocument", "sendMessage"]
    assert fake.sent == ["Đã lập kế hoạch.", listed((TITLE, 1))]
    assert fake.uploads == [Upload("sendDocument", f"{TITLE}.md", f'"{TITLE}" v1', PLAN.encode())]


async def test_a_job_writes_a_canvas_and_its_brief_names_it(
    make_channel, deps_factory, fake, store
):
    script = [completion(tool_calls=(CREATE,)), completion("Kế hoạch tuần đã có.")]
    deps = with_schedules(deps_factory(script=script, extra_tools=canvas_tools(store)), WEEKLY)
    run = await run_weekly(make_channel, deps)
    assert run.status == DONE
    the_one_canvas(store, JOB)
    assert fake.uploads == []
    assert fake.sent == ["Kế hoạch tuần đã có.", listed((TITLE, 1))]
