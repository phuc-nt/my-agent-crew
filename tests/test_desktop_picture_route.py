"""The picture a card asking about a desktop action shows: the one the screenshot tool took,
as it took it. The agent may write in the folder its pictures are kept in, so the route
serves a picture only while its bytes are the ones taken, and through no link."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import reading_as
from my_agent_crew.desktop import pictures
from my_agent_crew.desktop.kit import SCREENSHOT
from my_agent_crew.server.security_headers import FRAME_ANCESTORS
from my_agent_crew.server.untrusted_content import SANDBOX
from tests.desktop_helper import FakeHelper, desk, frame, listening, png
from tests.test_desktop_routes import Crew, serving

PICTURE = f"desktop/{frame(1)}.png"


@pytest.fixture(autouse=True)
def nothing_taken(monkeypatch):
    """What the tool took is kept in memory: each test starts from a crew that took none."""
    monkeypatch.setattr(pictures, "_written", {})


@pytest.fixture
async def helper() -> AsyncIterator[FakeHelper]:
    async with listening(apps=desk(), front="Notes") as found:
        yield found


@pytest.fixture
async def crew(tmp_path: Path, helper: FakeHelper) -> AsyncIterator[Crew]:
    async with serving(tmp_path, helper.path) as made:
        yield made


async def taken(crew: Crew) -> Path:
    """The agent's own tool takes the picture, and this is where it is."""
    with reading_as("c1"):
        await crew.rt.deps_for("coach").tools.get(SCREENSHOT).run({})
    return crew.workspace("coach") / PICTURE


async def card(crew: Crew, frame_id: str = frame(1), agent_id: str = "coach") -> httpx.Response:
    return await crew.web.get(f"/api/agents/{agent_id}/desktop/pictures/{frame_id}")


async def test_the_card_is_given_the_picture_the_tool_took_as_an_untrusted_image(crew):
    await taken(crew)

    reply = await card(crew)

    assert reply.status_code == 200 and reply.content == png(1)
    assert reply.headers["content-type"] == "image/png"
    assert reply.headers["x-content-type-options"] == "nosniff"
    assert reply.headers.get_list("content-security-policy") == [SANDBOX, FRAME_ANCESTORS]
    assert reply.headers["cross-origin-resource-policy"] == "same-origin"


async def test_a_picture_a_person_tried_is_one_the_tool_took_too(crew):
    assert (await crew.web.post("/api/agents/coach/desktop/screenshot")).status_code == 200

    reply = await card(crew)

    assert reply.status_code == 200 and reply.content == png(1)


async def test_a_picture_the_agent_rewrote_is_none_until_its_bytes_are_the_taken_ones(crew):
    picture = await taken(crew)

    picture.write_bytes(png(2))
    assert (await card(crew)).status_code == 404
    # The bytes are what counts, not that the file was written since.
    picture.write_bytes(png(1))
    assert (await card(crew)).content == png(1)


@pytest.mark.parametrize("linked", ["the picture", "its folder"])
async def test_a_link_put_in_its_place_is_none_even_to_the_very_bytes(crew, linked):
    picture = await taken(crew)
    elsewhere = crew.workspace("coach") / "elsewhere"
    if linked == "the picture":
        elsewhere.mkdir()
        picture.rename(elsewhere / picture.name)
        picture.symlink_to(elsewhere / picture.name)
    else:
        picture.parent.rename(elsewhere)
        picture.parent.symlink_to(elsewhere, target_is_directory=True)
    assert picture.read_bytes() == png(1)

    assert (await card(crew)).status_code == 404


async def test_a_picture_that_is_gone_or_is_no_file_is_none(crew):
    picture = await taken(crew)

    picture.unlink()
    assert (await card(crew)).status_code == 404
    picture.mkdir()
    assert (await card(crew)).status_code == 404


async def test_a_frame_the_tool_did_not_take_for_that_agent_is_none(crew):
    picture = await taken(crew)
    # The same bytes under the same name in another agent's folder: it took none of them.
    theirs = crew.workspace("looker") / PICTURE
    theirs.parent.mkdir(parents=True)
    theirs.write_bytes(picture.read_bytes())

    assert (await card(crew, agent_id="looker")).status_code == 404
    (crew.workspace("coach") / "desktop" / f"{frame(2)}.png").write_bytes(png(2))
    assert (await card(crew, frame(2))).status_code == 404


@pytest.mark.parametrize("name", ["notes", frame(1).upper(), f"{frame(1)}.png", f"{frame(1)}0x"])
async def test_a_name_that_is_no_frame_is_never_looked_for(crew, name):
    # Were the name looked for at all, this picture would be found and would verify.
    folder = crew.workspace("coach") / "desktop"
    folder.mkdir()
    (folder / f"{name}.png").write_bytes(png(1))
    workspace = crew.workspace("coach")
    pictures._written["coach"] = {name: (workspace, "desktop", hashlib.sha256(png(1)).hexdigest())}
    assert pictures.verified("coach", name) == png(1)

    assert (await card(crew, name)).status_code == 404


async def test_an_agent_the_crew_does_not_have_is_a_404(crew):
    await taken(crew)

    reply = await card(crew, agent_id="ghost")

    assert (reply.status_code, reply.json()) == (
        404,
        {"detail": texts.AGENT_UNKNOWN.format(agent_id="ghost")},
    )


def test_only_the_newest_pictures_of_an_agent_are_remembered(tmp_path):
    for number in range(1, pictures.KEPT + 2):
        pictures.save(tmp_path, "desktop", frame(number), png(number), "a")
    pictures.save(tmp_path, "theirs", frame(1), png(1), "b")
    # The oldest was removed from the folder: put back as it was, it is still forgotten.
    oldest = tmp_path / "desktop" / f"{frame(1)}.png"
    assert not oldest.exists()
    oldest.write_bytes(png(1))

    assert pictures.verified("a", frame(1)) is None
    # Another agent's picture takes no room of this one's.
    for number in (2, pictures.KEPT + 1):
        assert pictures.verified("a", frame(number)) == png(number), number
    assert pictures.verified("b", frame(1)) == png(1)
