"""`computer_act` as it runs: what the helper is sent, what the agent is told came of it, and
each way the helper says no told in a sentence of its own."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

from my_agent_crew import texts_desktop as t
from my_agent_crew import texts_desktop_act as ta
from my_agent_crew.agent.turn_context import reading_as
from my_agent_crew.desktop.client import ABSENT, BAD_ANSWER, TIMEOUT, UNTRUSTED, DesktopError
from my_agent_crew.desktop.kit import ACT, OBSERVE, said
from tests.desktop_helper import (
    HEIGHT,
    STALE,
    WIDTH,
    desk,
    frame,
    listening,
    outline_name,
    ref,
    socket_folder,
)
from tests.desktop_tools import desk_of

PROTOCOL = Path(__file__).parents[1] / "desktop-helper/Sources/DesktopHelperCore/Protocol.swift"
OURS = (ABSENT, TIMEOUT, BAD_ANSWER, UNTRUSTED)
BANK = ("Ngân hàng", "vn.bank.app")
WHY = "what the helper said of it"
POINT = {"x": 3, "y": 4}


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
        (call("click", x=0, y=0), {"x": 0, "y": 0}),
        (call("double_click", x=3, y=4.5), {"x": 3, "y": 4.5}),
        (call("right_click", x=15, y=9), {"x": 15, "y": 9}),
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


@pytest.mark.parametrize(
    ("kind", "node", "name"),
    [("click", "a2", "Ghi mới"), ("double_click", "a3", "mua sữa"), ("right_click", "a5", "Xoá")],
)
async def test_a_click_by_ref_goes_with_the_helpers_ref_and_the_name_of_its_outline(
    helper, tmp_path, kind, node, name
):
    tools = desk_of(helper, tmp_path)
    await tools.observe()

    answer = await tools.act(**call(kind, ref=ref(node), name=name))

    assert answer == ta.ACT_POSTED.format(kind=kind, app="Notes")
    (request,) = helper.sent("act")
    request.pop("id")
    # The tag and the name were this side's to judge: the helper is sent its own ref, and
    # the whole name of the outline that ref is one of.
    assert request == {
        "cmd": "act",
        "kind": kind,
        "app": "Notes",
        "frame_id": frame(1),
        "ref": node,
        "outline": outline_name(1),
    }
    assert [request["cmd"] for request in helper.requests] == ["apps", "ax", "act"]


async def test_a_field_set_is_said_to_be_set(helper, tmp_path):
    tools = desk_of(helper, tmp_path)
    await tools.observe()

    answer = await tools.act(**call("set_value", ref=ref("a3"), text="mua trứng"))

    assert answer == ta.ACT_SET.format(ref=ref("a3"), app="Notes")
    (request,) = helper.sent("act")
    assert (request["ref"], request["text"]) == ("a3", "mua trứng")
    assert request["outline"] == outline_name(1)


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
        call("set_value", ref=ref("a4"), text="hunter2"),
        call("set_value", ref=ref("a4"), text=""),
    ],
)
async def test_a_text_for_a_field_the_outline_marked_secure_never_reaches_the_helper(
    helper, tmp_path, args
):
    tools = desk_of(helper, tmp_path)
    await tools.observe()

    assert await tools.refused(ACT, **args) == ta.ACT_SECURE_REF.format(ref=ref("a4"))
    assert helper.sent("act") == []


async def test_a_secure_field_may_be_clicked_and_a_plain_one_set_or_typed_into(helper, tmp_path):
    tools = desk_of(helper, tmp_path)
    await tools.observe()

    await tools.act(**call("click", ref=ref("a4"), name="Mật khẩu"))
    await tools.act(**call("set_value", ref=ref("a3"), text="mua trứng"))
    await tools.act(**call("type", text="mua trứng"))

    assert [request["kind"] for request in helper.sent("act")] == ["click", "set_value", "type"]
    # A text that is typed names no element, so the name of no outline goes with it.
    assert not {"ref", "outline"} & set(helper.sent("act")[2])


async def test_a_ref_never_reaches_the_helper_unless_written_as_the_outline_shows_it(
    helper, tmp_path
):
    tools = desk_of(helper, tmp_path)
    await tools.observe()

    bare = await tools.refused(ACT, **call("click", ref="a2", name="Ghi mới"))
    typed = await tools.refused(ACT, **call("type", ref=ref("a3"), text="mua trứng"))

    assert bare == ta.ACT_REF_SHAPE.format(ref="a2")
    assert typed == ta.ACT_TYPE_REF
    assert helper.sent("act") == []


@pytest.mark.parametrize(
    "args",
    [call("click", ref=ref("a2"), name="Ghi mới"), call("set_value", ref=ref("a3"), text="x")],
)
async def test_a_ref_means_nothing_to_a_conversation_shown_no_outline(helper, tmp_path, args):
    refusal = await desk_of(helper, tmp_path).refused(ACT, **args)

    assert refusal == ta.ACT_REF_UNSEEN.format(ref=args["ref"])
    assert helper.requests == []


@pytest.mark.parametrize("name", ["Xoá", "Ghi", "", None])
async def test_a_click_under_a_name_the_outline_did_not_give_its_element_is_not_sent(
    helper, tmp_path, name
):
    tools = desk_of(helper, tmp_path)
    await tools.observe()
    args = call("click", ref=ref("a2")) | ({} if name is None else {"name": name})

    refusal = await tools.refused(ACT, **args)

    assert refusal == ta.ACT_NAME_MISMATCH.format(ref=ref("a2"), name=name or "")
    assert helper.sent("act") == []


async def test_a_name_is_the_same_whatever_its_case_its_spaces_and_the_way_its_marks_are_kept(
    helper, tmp_path
):
    tools = desk_of(helper, tmp_path)
    await tools.observe()
    name = unicodedata.normalize("NFD", "  ghi \n MỚI ")

    assert await tools.act(**call("click", ref=ref("a2"), name=name))
    assert helper.sent("act")[0]["ref"] == "a2"


async def test_a_row_that_did_not_fit_the_answer_names_nothing(helper, tmp_path):
    helper.running("Notes").nodes = [
        {"ref": f"a{n}", "depth": 1, "role": "AXButton", "title": f"nút {n} " + "x" * 70}
        for n in range(1, 201)
    ]
    tools = desk_of(helper, tmp_path, limit=3_000)
    outline = await tools.observe()
    assert "[ref=a10-0001]" in outline and "[ref=a200-0001]" not in outline
    last = outline.count("[ref=")
    assert 10 < last < 199 and f"[ref=a{last}-0001]" in outline

    cut = call("click", ref=ref("a200"), name="nút 200 " + "x" * 70)
    refusal = await tools.refused(ACT, **cut)

    assert refusal == ta.ACT_REF_UNSEEN.format(ref=ref("a200")) and helper.sent("act") == []
    # Nor does the first row that had no room, one line past the last that had.
    past = call("click", ref=ref(f"a{last + 1}"), name=f"nút {last + 1} " + "x" * 70)
    refusal = await tools.refused(ACT, **past)
    assert refusal == ta.ACT_REF_UNSEEN.format(ref=ref(f"a{last + 1}"))
    assert helper.sent("act") == []
    # A row the agent did read is clicked by the same words, the last of them too.
    assert await tools.act(**call("click", ref=ref("a10"), name="nút 10 " + "x" * 70))
    assert await tools.act(**call("click", ref=ref(f"a{last}"), name=f"nút {last} " + "x" * 70))


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
    refusal = await tools.refused(ACT, **call("set_value", ref=ref("a200"), text="x"))

    assert refusal == ta.ACT_SECURE_REF.format(ref=ref("a200"))


async def test_a_ref_is_judged_by_the_last_outline_and_not_by_one_before(helper, tmp_path):
    tools = desk_of(helper, tmp_path)
    await tools.observe()
    # The helper numbers the elements again each time: a4 is another field now.
    helper.running("Notes").nodes[3] = {"ref": "a4", "depth": 1, "role": "AXTextField"}
    await tools.observe()

    # As the outline before wrote it, a4 names nothing: not even the secure field it was.
    old = await tools.refused(ACT, **call("set_value", ref=ref("a4"), text="x"))
    assert old == ta.ACT_REF_UNSEEN.format(ref=ref("a4")) and helper.sent("act") == []
    new = await tools.act(**call("set_value", ref=ref("a4", 2), text="x"))
    assert new == ta.ACT_SET.format(ref=ref("a4", 2), app="Notes")
    assert helper.sent("act")[0]["outline"] == outline_name(2)


async def test_what_one_conversation_was_shown_is_no_other_conversations_to_act_on(
    helper, tmp_path
):
    # One agent, two conversations: the helper keeps one outline for all of them.
    tools = desk_of(helper, tmp_path)
    with reading_as("một"):
        await tools.observe()
    with reading_as("hai"):
        await tools.observe()
    first = call("click", ref=ref("a2"), name="Ghi mới")
    second = call("click", ref=ref("a2", 2), name="Ghi mới")

    with reading_as("một"):
        # Its own outline was replaced, and the newest is one it never read.
        assert await tools.refused(ACT, **first) == ta.ACT_REF_UNSEEN.format(ref=ref("a2"))
        assert await tools.refused(ACT, **second) == ta.ACT_REF_UNSEEN.format(ref=ref("a2", 2))
    # Nor is it the script's of a schedule, which runs in no conversation.
    assert await tools.refused(ACT, **second) == ta.ACT_REF_UNSEEN.format(ref=ref("a2", 2))
    assert helper.sent("act") == []
    with reading_as("hai"):
        assert await tools.act(**second) == ta.ACT_POSTED.format(kind="click", app="Notes")


async def test_an_outline_another_agent_read_since_is_the_helpers_to_refuse(helper, tmp_path):
    mine, theirs = desk_of(helper, tmp_path), desk_of(helper, tmp_path)
    await mine.observe()
    await theirs.observe()

    # This side still holds what it was shown. The helper keeps only its newest.
    refusal = await mine.refused(ACT, **call("click", ref=ref("a2"), name="Ghi mới"))

    assert refusal == told("ref_unknown")
    assert helper.sent("act")[0]["outline"] == outline_name(1)
    assert "computer_observe" in refusal


MISSING = object()


@pytest.mark.parametrize(
    "name",
    [MISSING, None, "", 7, 10**15, "xyz", "0" * 15, "0" * 17, "3F9C" + "0" * 12, ["0" * 16]],
)
async def test_an_outline_the_helper_gave_no_name_is_not_told_and_leaves_no_ref_to_use(
    helper, tmp_path, name
):
    tools = desk_of(helper, tmp_path)
    await tools.observe()
    tree = helper._ax({})
    tree = {key: value for key, value in tree.items() if key != "outline"}
    helper.scripted["ax"] = [tree if name is MISSING else {**tree, "outline": name}]

    refusal = await tools.refused(OBSERVE)

    assert refusal == said(DesktopError(BAD_ANSWER, ""))
    # The helper made a new outline of it all the same, so the one before names nothing.
    stale = await tools.refused(ACT, **call("click", ref=ref("a2"), name="Ghi mới"))
    assert stale == ta.ACT_REF_UNSEEN.format(ref=ref("a2")) and helper.sent("act") == []


async def test_an_outline_read_and_not_shown_takes_the_place_of_the_one_before(helper, tmp_path):
    tools = desk_of(helper, tmp_path)
    await tools.observe()
    # The next outline is of another process than the one asked for, so it is not told.
    helper.scripted["ax"] = [{**helper._ax({}), "pid": None}]
    assert await tools.refused(OBSERVE, app="Notes") == t.OBSERVE_OTHER

    refusal = await tools.refused(ACT, **call("click", ref=ref("a2"), name="Ghi mới"))

    assert refusal == ta.ACT_REF_UNSEEN.format(ref=ref("a2")) and helper.sent("act") == []


async def test_an_outline_that_could_not_be_read_leaves_the_marks_of_the_one_before(
    helper, tmp_path
):
    tools = desk_of(helper, tmp_path)
    await tools.observe()
    helper.fail["ax"] = ("internal", "")
    await tools.refused("computer_observe")

    # Nothing new was read, so what the agent was last shown still stands.
    refusal = await tools.refused(ACT, **call("set_value", ref=ref("a4"), text="x"))

    assert refusal == ta.ACT_SECURE_REF.format(ref=ref("a4")) and helper.sent("act") == []
    assert await tools.act(**call("click", ref=ref("a2"), name="Ghi mới"))


async def test_an_application_outside_the_list_left_in_front_is_told_without_its_name(
    helper, tmp_path
):
    helper.after_act = lambda desktop: setattr(desktop, "front", "Ngân hàng")

    answer = await desk_of(helper, tmp_path).act(**call("click", **POINT))

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
        **call("click", **POINT)
    )

    assert answer == ta.ACT_POSTED.format(kind="click", app="Notes")


@pytest.mark.parametrize("stop", ["locked", "display_asleep"])
async def test_a_screen_that_is_locked_or_dark_takes_no_action(helper, tmp_path, stop):
    setattr(helper, stop, True)

    assert await desk_of(helper, tmp_path).refused(ACT, **call("click", **POINT)) == told(stop)


async def test_an_application_that_is_not_in_front_takes_no_action(helper, tmp_path):
    helper.front = "Ngân hàng"

    refusal = await desk_of(helper, tmp_path).refused(ACT, **call("click", **POINT))

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

    refusal = await desk_of(helper, tmp_path).refused(ACT, **call("click", **POINT))

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
        absent = await tools.refused(ACT, **call("click", **POINT))
        doomed = await tools.refused(ACT, **call("key", keys="cmd+q"))
    finally:
        folder.rmdir()

    assert absent == t.HELPER_ERRORS["absent"]
    assert doomed == ta.ACT_KEYS_NEVER.format(keys="cmd+q")
