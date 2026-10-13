"""The desktop as the owner's screens are told of it: what the helper says of the machine on
the connections page, one agent's desktop, the picture a person takes to try it, the button
that asks macOS for the helper's permissions, and the rows of the tool list."""

from __future__ import annotations

import contextlib
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from my_agent_crew import texts
from my_agent_crew import texts_desktop as t
from my_agent_crew.activity.step_previews import outcome_preview
from my_agent_crew.agent.turn_context import reading_as
from my_agent_crew.desktop.kit import ACT, DESKTOP_TOOLS, SCREENSHOT
from my_agent_crew.server import desktop_runtime
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime import Runtime
from tests.browser_crew import built, crew_home
from tests.desktop_helper import (
    HEIGHT,
    PROTOCOL,
    VERSION,
    WIDTH,
    FakeHelper,
    desk,
    frame,
    listening,
    png,
)

AGENTS = {
    "coach": 'computer: "on"\ncomputer_apps: [Notes]\n',
    "looker": 'computer: "on"\n',
    "plain": "description: no key\n",
}
MACHINE = {
    "present": True,
    "version": VERSION,
    "protocol": PROTOCOL,
    "locked": False,
    "display_asleep": False,
    "screen_recording": True,
    "accessibility": True,
}
ABSENT = {
    "present": False,
    "version": None,
    "protocol": None,
    "locked": None,
    "display_asleep": None,
    "screen_recording": None,
    "accessibility": None,
}
PICTURE = f"desktop/{frame(1)}.png"
# As the web reads a screenshot step: the picture's path and its frame from the line that
# says where it was saved, and the frame alone from the line that says nothing changed. A
# run's step keeps one line of the answer, cut short, so neither is told by a line end.
FRAME = r"[0-9a-f]{16}-\d{1,10}x\d{1,10}-\d{1,10}"
SAVED_LINE = re.compile(rf"^Đã chụp màn hình và lưu vào (.*?({FRAME})\.png)\. frame_id: ")
UNCHANGED_LINE = re.compile(rf"^Màn hình không đổi từ lần chụp trước\. frame_id: ({FRAME}) ")
# A folder deep enough that a step's one line ends before the path of an unchanged picture.
DEEP = "records/kept/for/the/owner/by/this/agent"


@dataclass
class Crew:
    web: httpx.AsyncClient
    rt: Runtime
    home: Path

    def workspace(self, agent_id: str) -> Path:
        return self.rt.deps_for(agent_id).agent.workspace

    def pictures(self, agent_id: str) -> list[str]:
        return sorted(found.name for found in self.workspace(agent_id).rglob("*.png"))

    async def machine(self) -> dict:
        reply = await self.web.get("/api/connections")
        assert reply.status_code == 200, reply.text
        return reply.json()["desktop"]

    async def tries(self, agent_id: str) -> tuple[int, dict]:
        reply = await self.web.post(f"/api/agents/{agent_id}/desktop/screenshot")
        return reply.status_code, reply.json()


@contextlib.asynccontextmanager
async def serving(
    root: Path, socket: Path | None = None, agents: dict[str, str] | None = None
) -> AsyncIterator[Crew]:
    """The crew served, looking for the helper at `socket`; with none, where a home keeps
    it, and there is nothing there."""
    config = f"desktop_socket: {socket}\n" if socket else ""
    rt = built(crew_home(root, config=config, **(AGENTS if agents is None else agents)))
    app = create_app(rt, schedule=False)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as web:
            yield Crew(web, rt, root / "home")


@pytest.fixture
async def helper() -> AsyncIterator[FakeHelper]:
    async with listening(apps=desk(), front="Notes") as found:
        yield found


@pytest.fixture
async def crew(tmp_path: Path, helper: FakeHelper) -> AsyncIterator[Crew]:
    async with serving(tmp_path, helper.path) as made:
        yield made


@pytest.fixture
async def alone(tmp_path: Path) -> AsyncIterator[Crew]:
    """A crew on a machine nobody installed the helper on."""
    async with serving(tmp_path) as made:
        yield made


def asked(helper: FakeHelper) -> list[str]:
    return [request["cmd"] for request in helper.requests]


async def test_the_connections_page_is_told_what_the_helper_says_of_the_machine(crew, helper):
    assert await crew.machine() == MACHINE
    # One `state`, which touches nothing: neither the screen nor a dialog of the system's.
    # What is in front and what the displays are stay with the helper.
    (request,) = helper.requests
    assert sorted(request) == ["cmd", "id"] and request["cmd"] == "state"


@pytest.mark.parametrize("key", ["locked", "display_asleep", "screen_recording", "accessibility"])
async def test_each_thing_the_helper_says_reaches_the_page_as_it_said_it(crew, helper, key):
    setattr(helper, key, not getattr(helper, key))

    assert await crew.machine() == MACHINE | {key: not MACHINE[key]}


async def test_a_machine_with_no_helper_is_told_as_one_and_not_as_an_error(alone):
    assert await alone.machine() == ABSENT
    # Looking for the helper makes nothing: the folder is the helper's own to make.
    assert not (alone.home / "desktop").exists()


async def test_a_helper_that_never_answers_holds_the_page_up_for_one_second(crew, helper):
    helper.silent = True
    began = time.monotonic()

    told = await crew.machine()

    took = time.monotonic() - began
    assert told == ABSENT
    # The page's own deadline, and not the ten seconds a tool gives the helper.
    assert desktop_runtime.STATUS_SECONDS == 1.0 and 0.9 <= took < 5, took


TROUBLES = {
    "a line that is not JSON": {"raw": b"not an answer\n"},
    "half an answer": {"raw": b'{"ok": true'},
    "an answer to somebody else": {"other_id": True},
    "a connection closed without a word": {"hangs_up": True},
    "a refusal": {"fail": {"state": ("internal", "boom")}},
}


@pytest.mark.parametrize("trouble", TROUBLES.values(), ids=TROUBLES.keys())
async def test_a_helper_whose_answer_cannot_be_read_is_told_as_none(crew, helper, trouble):
    for key, value in trouble.items():
        setattr(helper, key, value)

    assert await crew.machine() == ABSENT


async def test_what_the_helper_left_out_or_mistyped_is_unknown_and_never_guessed(crew, helper):
    mistyped = {"version": 7, "protocol": True, "locked": "no", "display_asleep": 0}
    helper.scripted["state"] = [mistyped, {"version": "9" * 500, "protocol": 2, "locked": True}]

    assert await crew.machine() == ABSENT | {"present": True}
    # A helper of another protocol is told as it is, for the page to say so, and a version
    # of any length is cut to what a line of the page holds.
    newer = {"present": True, "version": "9" * 40, "protocol": 2, "locked": True}
    assert await crew.machine() == ABSENT | newer


async def test_an_agents_desktop_is_its_mode_its_applications_and_the_machine(crew, helper):
    async def told(agent_id: str) -> dict:
        reply = await crew.web.get(f"/api/agents/{agent_id}/desktop")
        assert reply.status_code == 200, reply.text
        return reply.json()

    assert await told("coach") == {"mode": "on", "apps": ["Notes"], "machine": MACHINE}
    assert await told("looker") == {"mode": "on", "apps": [], "machine": MACHINE}
    for without in ("plain", "default"):
        assert await told(without) == {"mode": "off", "apps": [], "machine": MACHINE}, without
    assert asked(helper) == ["state"] * 4


async def test_an_agents_desktop_on_a_machine_with_no_helper_still_tells_its_own_keys(alone):
    reply = await alone.web.get("/api/agents/coach/desktop")

    assert reply.status_code == 200
    assert reply.json() == {"mode": "on", "apps": ["Notes"], "machine": ABSENT}


@pytest.mark.parametrize(("method", "path"), [("GET", "/desktop"), ("POST", "/desktop/screenshot")])
async def test_an_agent_the_crew_does_not_have_is_a_404(crew, helper, method, path):
    reply = await crew.web.request(method, f"/api/agents/ghost{path}")

    assert reply.status_code == 404
    assert reply.json() == {"detail": texts.AGENT_UNKNOWN.format(agent_id="ghost")}
    assert helper.requests == []


async def test_a_person_tries_a_screenshot_and_is_given_what_the_agent_would_be(crew, helper):
    status, told = await crew.tries("coach")

    assert status == 200, told
    assert told == {"frame_id": frame(1), "path": PICTURE, "width": WIDTH, "height": HEIGHT}
    assert (crew.workspace("coach") / PICTURE).read_bytes() == png(1)
    # The page shows it as it shows any file of the agent's workspace.
    shown = await crew.web.get("/api/agents/coach/files", params={"path": PICTURE})
    assert shown.status_code == 200 and shown.headers["content-type"] == "image/png"
    assert shown.content == png(1)
    # Held to the agent's applications as its own tool is: a look before and a look after.
    assert asked(helper) == ["state", "screenshot", "state"]
    assert "since" not in helper.sent("screenshot")[0]


async def test_an_agent_given_no_application_shows_a_person_whatever_is_in_front(crew, helper):
    helper.front = "Ngân hàng"

    status, told = await crew.tries("looker")

    assert (status, told["path"]) == (200, PICTURE)
    assert crew.pictures("looker") == [f"{frame(1)}.png"] and asked(helper) == ["screenshot"]


CANNOT = {
    "locked": ("locked", True, t.HELPER_ERRORS["locked"]),
    "display asleep": ("display_asleep", True, t.HELPER_ERRORS["display_asleep"]),
    "no permission": ("screen_recording", False, t.HELPER_ERRORS["permission_missing:screen"]),
}


@pytest.mark.parametrize("agent_id", ["coach", "looker"])
@pytest.mark.parametrize(("key", "value", "sentence"), CANNOT.values(), ids=CANNOT.keys())
async def test_a_screen_that_cannot_be_pictured_is_a_409_that_names_what_is_missing(
    crew, helper, agent_id, key, value, sentence
):
    setattr(helper, key, value)

    assert await crew.tries(agent_id) == (409, {"detail": sentence})
    assert crew.pictures(agent_id) == []


async def test_a_locked_console_gives_a_person_the_sentence_and_never_a_blank_picture(crew, helper):
    helper.locked = True
    # A helper that would hand over a black picture all the same.
    helper.scripted["screenshot"] = [helper._screenshot({})]

    assert await crew.tries("coach") == (409, {"detail": t.HELPER_ERRORS["locked"]})
    assert helper.sent("screenshot") == [] and crew.pictures("coach") == []


async def test_a_person_is_shown_no_application_the_agent_itself_would_not_be(crew, helper):
    helper.front = "Ngân hàng"

    status, told = await crew.tries("coach")

    assert (status, told) == (409, {"detail": t.SHOT_OUTSIDE})
    assert "Ngân hàng" not in told["detail"]
    assert helper.sent("screenshot") == [] and crew.pictures("coach") == []


async def test_an_agent_without_the_desktop_gives_a_person_no_picture_either(crew, helper):
    for without in ("plain", "default"):
        assert await crew.tries(without) == (409, {"detail": t.TRY_OFF}), without
    assert helper.requests == []


async def test_trying_on_a_machine_with_no_helper_says_there_is_none(alone):
    assert await alone.tries("coach") == (409, {"detail": t.HELPER_ERRORS["absent"]})
    assert await alone.tries("looker") == (409, {"detail": t.HELPER_ERRORS["absent"]})


async def test_a_persons_picture_is_not_one_the_agent_was_given(crew, helper):
    look = crew.rt.deps_for("coach").tools.get(SCREENSHOT).run
    with reading_as("c1"):
        await look({})
    helper.shot = 2

    status, told = await crew.tries("coach")
    with reading_as("c1"):
        answer = await look({})

    assert (status, told["frame_id"]) == (200, frame(2))
    # The agent is sent the new screen whole. Had the person's picture counted as its own,
    # it would be told the screen had not changed since a frame it never saw.
    assert [sent.get("since") for sent in helper.sent("screenshot")] == [None, None, frame(1)]
    assert answer.splitlines()[0] == t.SHOT_SAVED.format(
        path=f"desktop/{frame(2)}.png", frame_id=frame(2), width=WIDTH, height=HEIGHT
    )


async def test_a_screenshot_step_tells_the_web_the_picture_and_the_frame(tmp_path, helper):
    agents = {"held": f'write_paths: [{DEEP}]\ncomputer: "on"\n', "free": 'computer: "on"\n'}
    cut_short = []
    async with serving(tmp_path, helper.path, agents) as made:
        for agent_id, folder in (("held", f"{DEEP}/desktop"), ("free", "desktop")):
            look = made.rt.deps_for(agent_id).tools.get(SCREENSHOT).run
            with reading_as("c1"):
                first = await look({})
                again = await look({})
            path = f"{folder}/{frame(1)}.png"

            # Read the one way from the whole answer and from what a run's step keeps.
            for read in (first, outcome_preview(first, True)):
                assert SAVED_LINE.findall(read) == [(path, frame(1))], agent_id
            assert path in again
            for read in (again, outcome_preview(again, True)):
                assert UNCHANGED_LINE.findall(read) == [frame(1)], agent_id
            cut_short.append(path not in outcome_preview(again, True))
            # The route that serves a workspace file gives the picture as an image.
            served = await made.web.get(f"/api/agents/{agent_id}/files", params={"path": path})
            assert served.status_code == 200 and served.content == png(1), agent_id
            assert served.headers["content-type"] == "image/png", agent_id
    # Why an unchanged screen is read by its frame and not by its path: a step's one line
    # ends before the path of an agent that keeps its pictures deep.
    assert cut_short == [True, False]


async def test_the_button_asks_the_helper_to_ask_macos_and_tells_what_it_holds(crew, helper):
    helper.accessibility = False

    reply = await crew.web.post("/api/desktop/permissions")

    assert reply.status_code == 200, reply.text
    assert reply.json() == {"screen_recording": True, "accessibility": False}
    (request,) = helper.requests
    assert sorted(request) == ["cmd", "id"] and request["cmd"] == "request_permissions"


async def test_nothing_but_the_button_asks_for_a_permission(crew, helper):
    """The one request that may put a dialog of the system's on the owner's screen."""
    await crew.machine()
    await crew.web.get("/api/agents/coach/desktop")
    await crew.tries("coach")
    await crew.web.get("/api/tools")

    assert asked(helper) == ["state", "state", "state", "screenshot", "state"]


async def test_what_the_helper_does_not_say_of_a_permission_is_unknown(crew, helper):
    helper.scripted["request_permissions"] = [{"screen_recording": "yes"}]

    reply = await crew.web.post("/api/desktop/permissions")

    assert reply.status_code == 200
    assert reply.json() == {"screen_recording": None, "accessibility": None}


async def test_the_button_on_a_machine_with_no_helper_is_a_409_that_says_so(alone):
    reply = await alone.web.post("/api/desktop/permissions")

    assert (reply.status_code, reply.json()) == (409, {"detail": t.HELPER_ERRORS["absent"]})


async def test_the_button_on_a_locked_console_is_a_409_that_names_the_lock(crew, helper):
    helper.locked = True

    reply = await crew.web.post("/api/desktop/permissions")

    assert (reply.status_code, reply.json()) == (409, {"detail": t.HELPER_ERRORS["locked"]})


async def marked(made: Crew) -> None:
    listed = {tool["name"]: tool for tool in (await made.web.get("/api/tools")).json()}

    # The mark is what a screen tells them apart by: no allow-list brings one, so a cell
    # that is empty is the agent's `computer` key.
    assert [name for name, tool in listed.items() if "with_desktop" in tool] == sorted(
        DESKTOP_TOOLS
    )
    for name in DESKTOP_TOOLS:
        assert listed[name]["with_desktop"] is True, name
        assert listed[name]["optional"] is False, name
        assert not {"with_browser", "with_reads", "with_mcp"} & set(listed[name]), name
        assert listed[name]["agents"] == ["coach", "looker"], name
    assert [name for name in DESKTOP_TOOLS if listed[name]["requires_approval"]] == [ACT]
    # And none of them is an agent's list's to give, whatever the agent's key says.
    for agent in (await made.web.get("/api/agents")).json():
        assert not set(agent["listable_tools"]) & set(DESKTOP_TOOLS), agent["id"]


async def test_the_crews_tool_list_marks_the_desktop_tools_as_the_computer_keys_to_give(
    crew, helper
):
    await marked(crew)
    assert helper.requests == []


async def test_the_tool_list_is_the_same_on_a_machine_with_no_helper(alone):
    await marked(alone)
