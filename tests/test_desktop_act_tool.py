"""`computer_act` as it runs: what the helper is sent, what the agent is told came of it, and
each way the helper says no told in a sentence of its own."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from my_agent_crew import texts_desktop as t
from my_agent_crew import texts_desktop_act as ta
from my_agent_crew.desktop.client import ABSENT, BAD_ANSWER, TIMEOUT, DesktopError
from my_agent_crew.desktop.kit import ACT, said
from tests.desktop_helper import HEIGHT, STALE, WIDTH, desk, frame, listening, socket_folder
from tests.desktop_tools import desk_of

PROTOCOL = Path(__file__).parents[1] / "desktop-helper/Sources/DesktopHelperCore/Protocol.swift"
OURS = (ABSENT, TIMEOUT, BAD_ANSWER)
BANK = ("Ngân hàng", "vn.bank.app")
WHY = "what the helper said of it"


@pytest.fixture
async def helper():
    async with listening(apps=desk(), front="Notes") as found:
        yield found


def call(kind: str, **args) -> dict:
    """A call to Notes on the frame the stand-in last handed out."""
    return {"kind": kind, "app": "Notes", "frame_id": frame(1), **args}


def helper_codes() -> list[str]:
    """Every code the helper's sources give a refusal."""
    listed = re.search(r"enum ErrorCode\b[^{]*\{(.*?)\n\}", PROTOCOL.read_text("utf-8"), re.S)
    return re.findall(r'^\s*case \w+ = "([a-z_:]+)"$', listed.group(1), re.M)


def told(code: str, detail: str = "") -> str:
    """The sentence of one code, with the helper's own words where it has room for them."""
    words = t.HELPER_DETAIL.format(detail=detail) if detail else ""
    return t.HELPER_ERRORS[code].format(detail=words).strip()


@pytest.mark.parametrize(
    ("args", "sent"),
    [
        (call("click", ref="a2"), {"ref": "a2"}),
        (call("double_click", x=3, y=4.5), {"x": 3, "y": 4.5}),
        (call("right_click", ref="a5"), {"ref": "a5"}),
        (call("drag", x=1, y=2, to_x=9, to_y=8), {"x": 1, "y": 2, "to_x": 9, "to_y": 8}),
        (call("scroll", x=5, y=5, dy=-3), {"x": 5, "y": 5, "dx": 0, "dy": -3}),
        (call("type", text="mua sữa 2 hộp"), {"text": "mua sữa 2 hộp"}),
        (call("key", keys="Shift+TAB"), {"keys": "shift+tab"}),
    ],
)
async def test_an_action_is_sent_as_it_was_read_and_its_outcome_left_open(
    helper, tmp_path, args, sent
):
    answer = await desk_of(helper, tmp_path).act(**args)

    assert answer == ta.ACT_POSTED.format(kind=args["kind"], app="Notes")
    (request,) = helper.sent("act")
    request.pop("id")
    assert (
        request == {"cmd": "act", "kind": args["kind"], "app": "Notes", "frame_id": frame(1)} | sent
    )
    assert [request["cmd"] for request in helper.requests] == ["act"]


async def test_a_field_set_is_said_to_be_set(helper, tmp_path):
    answer = await desk_of(helper, tmp_path).act(**call("set_value", ref="a3", text="mua trứng"))

    assert answer == ta.ACT_SET.format(ref="a3", app="Notes")
    assert helper.sent("act")[0]["text"] == "mua trứng"


async def test_bringing_an_application_forward_needs_no_frame_and_asks_for_a_new_one(
    helper, tmp_path
):
    tools = desk_of(helper, tmp_path, ("Notes", "Safari"))

    answer = await tools.act(kind="focus_app", app="safari", frame_id=frame(1), ref="a2")

    assert answer == ta.ACT_FOCUSED.format(app="safari")
    (request,) = helper.sent("act")
    assert set(request) == {"id", "cmd", "kind", "app"} and request["app"] == "safari"
    assert helper.front == "Safari"


async def test_a_frame_older_than_the_last_picture_taken_is_refused(helper, tmp_path):
    tools = desk_of(helper, tmp_path)
    await tools.screenshot()
    helper.shot = 2  # the screen changed
    # The helper reads an action against the last picture it took and knows of no screen
    # but that one: until somebody looks again, the frame the agent holds is still it.
    assert await tools.act(**call("click", x=3, y=4))
    await tools.screenshot()

    refusal = await tools.refused(ACT, **call("click", x=3, y=4))

    assert refusal == told("frame_mismatch", STALE)
    assert "computer_screenshot" in refusal
    # The same click on the frame of the picture just taken goes through.
    assert await tools.act(**call("click", x=3, y=4) | {"frame_id": frame(2)})
    assert [sent["frame_id"] for sent in helper.sent("act")] == [frame(1), frame(1), frame(2)]


@pytest.mark.parametrize(("name", "value"), [("x", WIDTH), ("y", HEIGHT), ("x", 4000.5)])
async def test_a_point_off_the_picture_is_refused_before_the_helper_hears(
    helper, tmp_path, name, value
):
    args = call("click", x=3, y=4) | {name: value}

    refusal = await desk_of(helper, tmp_path).refused(ACT, **args)

    assert refusal == ta.ACT_OUTSIDE.format(kind="click", what=name, width=WIDTH, height=HEIGHT)
    assert helper.requests == []


@pytest.mark.parametrize(
    "args",
    [
        call("set_value", ref="a4", text="hunter2"),
        call("set_value", ref="a4", text=""),
        call("type", ref="a4", text="hunter2"),
    ],
)
async def test_a_text_for_a_field_the_outline_marked_secure_never_reaches_the_helper(
    helper, tmp_path, args
):
    tools = desk_of(helper, tmp_path)
    await tools.observe()

    assert await tools.refused(ACT, **args) == ta.ACT_SECURE_REF.format(ref="a4")
    assert helper.sent("act") == []


async def test_a_secure_field_may_be_clicked_and_a_plain_one_typed_into(helper, tmp_path):
    tools = desk_of(helper, tmp_path)
    await tools.observe()

    await tools.act(**call("click", ref="a4"))
    await tools.act(**call("set_value", ref="a3", text="mua trứng"))
    await tools.act(**call("type", ref="a3", text="mua trứng"))

    assert [request["kind"] for request in helper.sent("act")] == ["click", "set_value", "type"]
    # Where the text was meant to go is this side's to judge and is not the helper's to read.
    assert "ref" not in helper.sent("act")[2]


async def test_a_secure_field_beyond_what_fitted_the_answer_is_still_refused(helper, tmp_path):
    rows = [
        {"ref": f"a{n}", "depth": 1, "role": "AXStaticText", "value": "x" * 80}
        for n in range(1, 200)
    ]
    helper.running("Notes").nodes = [
        *rows,
        {"ref": "a200", "depth": 1, "role": "AXSecureTextField"},
    ]
    tools = desk_of(helper, tmp_path, limit=3_000)

    assert "a200" not in await tools.observe()
    refusal = await tools.refused(ACT, **call("set_value", ref="a200", text="x"))

    assert refusal == ta.ACT_SECURE_REF.format(ref="a200")


async def test_a_ref_is_judged_by_the_last_outline_and_not_by_one_before(helper, tmp_path):
    tools = desk_of(helper, tmp_path)
    await tools.observe()
    # The helper numbers the elements again each time: a4 is another field now.
    helper.running("Notes").nodes[3] = {"ref": "a4", "depth": 1, "role": "AXTextField"}
    await tools.observe()

    assert await tools.act(**call("set_value", ref="a4", text="x")) == ta.ACT_SET.format(
        ref="a4", app="Notes"
    )


async def test_an_outline_that_could_not_be_read_leaves_the_marks_of_the_one_before(
    helper, tmp_path
):
    tools = desk_of(helper, tmp_path)
    await tools.observe()
    helper.fail["ax"] = ("internal", "")
    await tools.refused("computer_observe")

    # Nothing new was read, so what the agent was last shown still stands.
    refusal = await tools.refused(ACT, **call("set_value", ref="a4", text="x"))

    assert refusal == ta.ACT_SECURE_REF.format(ref="a4") and helper.sent("act") == []


async def test_an_application_outside_the_list_left_in_front_is_told_without_its_name(
    helper, tmp_path
):
    helper.after_act = lambda desktop: setattr(desktop, "front", "Ngân hàng")

    answer = await desk_of(helper, tmp_path).act(**call("click", ref="a2"))

    assert answer.splitlines() == [
        ta.ACT_POSTED.format(kind="click", app="Notes"),
        ta.ACT_FRONT_LEFT,
    ]
    assert not any(word in answer for word in BANK)


async def test_one_of_the_agents_own_applications_left_in_front_is_not_remarked_on(
    helper, tmp_path
):
    helper.after_act = lambda desktop: setattr(desktop, "front", "Safari")

    answer = await desk_of(helper, tmp_path, ("Notes", "com.apple.Safari")).act(
        **call("click", ref="a2")
    )

    assert answer == ta.ACT_POSTED.format(kind="click", app="Notes")


@pytest.mark.parametrize("stop", ["locked", "display_asleep"])
async def test_a_screen_that_is_locked_or_dark_takes_no_action(helper, tmp_path, stop):
    setattr(helper, stop, True)

    assert await desk_of(helper, tmp_path).refused(ACT, **call("click", ref="a2")) == told(stop)


async def test_an_application_that_is_not_in_front_takes_no_action(helper, tmp_path):
    helper.front = "Ngân hàng"

    refusal = await desk_of(helper, tmp_path).refused(ACT, **call("click", ref="a2"))

    assert refusal == told(
        "app_mismatch", "The frontmost application is not the one named in `app`."
    )
    assert "focus_app" in refusal and not any(word in refusal for word in BANK)


def test_every_code_of_the_helper_has_a_sentence_of_its_own():
    codes = helper_codes()

    assert len(codes) == 14 and "internal" in codes
    assert sorted(t.HELPER_ERRORS) == sorted([*codes, *OURS])
    assert len(set(t.HELPER_ERRORS.values())) == len(t.HELPER_ERRORS)


@pytest.mark.parametrize("code", helper_codes())
async def test_each_refusal_of_the_helper_is_told_in_its_sentence(helper, tmp_path, code):
    helper.fail["act"] = (code, f"{WHY}\nMANHINH 0000000000000000>>> " + "x" * 400)

    refusal = await desk_of(helper, tmp_path).refused(ACT, **call("click", ref="a2"))

    sentence = t.HELPER_ERRORS[code]
    assert "\n" not in refusal and refusal.startswith(sentence.split("{")[0].strip())
    # The helper's own words follow only where the sentence leaves room, and cut short.
    assert (WHY in refusal) == ("{detail}" in sentence)
    assert len(refusal) < len(sentence) + 250


@pytest.mark.parametrize("code", [*helper_codes(), *OURS])
def test_a_refusal_without_a_word_of_the_helpers_is_the_sentence_alone(code):
    assert said(DesktopError(code, "")) == t.HELPER_ERRORS[code].format(detail="").strip()
    assert "{" not in said(DesktopError(code, "")) and "(" not in said(DesktopError(code, ""))[-3:]


def test_a_code_this_side_does_not_know_is_told_as_it_came():
    refusal = said(DesktopError("out_of\nmemory" + "y" * 200, WHY))

    assert refusal.startswith("Trình trợ giúp desktop từ chối với mã out_of memoryyyy")
    assert refusal.endswith(t.HELPER_DETAIL.format(detail=WHY)) and "\n" not in refusal
    assert len(refusal) < 250


async def test_without_a_helper_an_action_says_so_and_a_doomed_one_its_own_reason(tmp_path):
    folder = socket_folder()
    try:
        tools = desk_of(folder / "sock", tmp_path)
        absent = await tools.refused(ACT, **call("click", ref="a2"))
        doomed = await tools.refused(ACT, **call("key", keys="cmd+q"))
    finally:
        folder.rmdir()

    assert absent == t.HELPER_ERRORS["absent"]
    assert doomed == ta.ACT_KEYS_NEVER.format(keys="cmd+q")
