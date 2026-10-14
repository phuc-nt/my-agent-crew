"""What the helper refuses of an action this side may not see coming: a point another window
lies over, and a web browser in front under a name of its own. Each is told in its own
sentence, and neither as an action done. The stand-in refuses a text with a control character
as the helper does, for a request sent around the tool."""

from __future__ import annotations

import pytest

from my_agent_crew import texts_desktop as t
from my_agent_crew import texts_desktop_act as ta
from my_agent_crew.desktop.client import DesktopClient, DesktopError
from my_agent_crew.desktop.kit import ACT
from tests.desktop_helper import CONTROL_TEXT, App, desk, frame, listening, ref
from tests.desktop_tools import desk_of, refusal_of

# A site saved as an application: a name of its own, and the bundle id of the browser's.
SITE = App("Gmail", "com.google.Chrome.app.kjgfgldnnfoeklkmfkjfagphfepbbdan", 503)
POINTED = {
    "click": {"x": 3, "y": 4},
    "double_click": {"x": 3, "y": 4},
    "right_click": {"x": 3, "y": 4},
    "drag": {"x": 1, "y": 2, "to_x": 3, "to_y": 4},
    "scroll": {"x": 1, "y": 2, "dy": 1},
    "click by ref": {"ref": ref("a2"), "name": "Ghi mới"},
}


@pytest.fixture
async def helper():
    async with listening(apps=desk(), front="Notes") as found:
        yield found


def call(kind: str, **args) -> dict:
    return {"kind": kind.split()[0], "app": "Notes", "frame_id": frame(1), **args}


@pytest.mark.parametrize(("kind", "args"), POINTED.items(), ids=POINTED.keys())
async def test_an_action_where_another_window_lies_on_top_is_told_so_and_not_as_done(
    helper, tmp_path, kind, args
):
    tools = desk_of(helper, tmp_path)
    await tools.observe()
    helper.covered = True

    refusal = await tools.refused(ACT, **call(kind, **args))

    # The sentence alone: what lies on top may be an application outside the list.
    assert refusal_of(refusal) == (t.HELPER_ERRORS["point_covered"], "")
    assert "Another window" not in refusal
    helper.covered = False
    done = await tools.act(**call(kind, **args))
    assert done == ta.ACT_POSTED.format(kind=kind.split()[0], app="Notes")


async def test_a_browser_in_front_under_a_name_of_its_own_is_the_helpers_to_refuse(
    helper, tmp_path
):
    # Nothing in the name says it is a browser: this side lets it through, the helper not.
    helper.apps.append(SITE)
    tools = desk_of(helper, tmp_path, ("Notes", "Gmail"))

    focused = await tools.refused(ACT, kind="focus_app", app="Gmail")
    helper.front = "Gmail"
    clicked = await tools.refused(ACT, **call("click", x=3, y=4) | {"app": "Gmail"})

    assert refusal_of(focused) == refusal_of(clicked) == (t.HELPER_ERRORS["browser_app"], "")
    assert [request["kind"] for request in helper.sent("act")] == ["focus_app", "click"]


@pytest.mark.parametrize(
    "app", ["Safari", "google chrome", "com.apple.Safari", "COM.GOOGLE.CHROME.app.x", "Arc"]
)
async def test_a_browser_a_list_names_is_refused_before_the_helper_hears(helper, tmp_path, app):
    # No agent's file can say so: the list here is made by hand.
    tools = desk_of(helper, tmp_path, ("Notes", app))

    for args in ({"kind": "focus_app", "app": app}, call("click", x=3, y=4) | {"app": app}):
        refusal = await tools.refused(ACT, **args)
        assert refusal == t.APP_OUTSIDE.format(app=app, apps=f"Notes, {app}")
    assert helper.requests == []


@pytest.mark.parametrize("text", ["sudx\bo ls", "\x1b[A", "a\x85", "a\x7f"])
async def test_the_stand_in_refuses_a_text_with_a_control_character_as_the_helper_does(
    helper, text
):
    client = DesktopClient(helper.path)

    for kind, args in (("type", {}), ("set_value", {"ref": "a3", "outline": "0" * 16})):
        with pytest.raises(DesktopError) as caught:
            await client.request("act", **call(kind, text=text, **args))
        assert (caught.value.code, caught.value.detail) == ("bad_request", CONTROL_TEXT)
    assert await client.request("act", **call("type", text="a\tb\r\n"))
