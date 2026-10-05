"""A `FILE:` line that names a picture: sent as the photo a `MEDIA:` line would send, where it
used to be refused as a format a chat does not take."""

from __future__ import annotations

import pytest

from my_agent_crew import texts
from my_agent_crew.channels.telegram_attachments import document_suffix_allowed, is_photo


def write(channel, relative: str, content: bytes = b"\x89PNG\r\n\x1a\n"):
    path = channel.deps.agent.workspace / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.mark.parametrize("name", ["a.png", "a.jpg", "a.jpeg", "a.webp", "out/Chart.PNG"])
def test_the_pictures_a_chat_shows_inline_are_photos(name):
    assert is_photo(name)


@pytest.mark.parametrize("name", ["a.svg", "a.html", "a.pdf", "a.env", "png", "a.png.sh"])
def test_anything_else_is_not_a_photo(name):
    """An SVG is markup and a name that only mentions `png` is not a picture."""
    assert not is_photo(name)


def test_a_picture_is_still_not_a_document_format():
    """The photo route is its own; the list of documents a chat takes did not grow."""
    assert not document_suffix_allowed("a.png")


@pytest.mark.parametrize("name", ["hinh.png", "out/anh.JPG", "a.jpeg", "a.webp"])
async def test_a_file_line_naming_a_picture_sends_it_as_a_photo(make_channel, fake, name):
    channel = make_channel()
    write(channel, name)
    await channel.outbound().send(f"Ảnh đây.\nFILE: {name}")
    assert fake.sent == ["Ảnh đây."]
    assert [upload.method for upload in fake.uploads] == ["sendPhoto"]
    assert len(fake.photos) == 1 and fake.documents == []


async def test_a_picture_and_a_document_on_file_lines_each_go_their_own_way(make_channel, fake):
    channel = make_channel()
    write(channel, "hinh.png")
    write(channel, "brief.pdf", b"%PDF-1.4\n")
    await channel.outbound().send("FILE: hinh.png\nFILE: brief.pdf")
    assert [(u.method, u.name) for u in fake.uploads] == [
        ("sendPhoto", "hinh.png"),
        ("sendDocument", "brief.pdf"),
    ]


async def test_a_missing_picture_on_a_file_line_is_said_as_a_picture(make_channel, fake):
    channel = make_channel()
    await channel.outbound().send("FILE: gone.png")
    assert fake.sent == [texts.TELEGRAM_MEDIA_MISSING.format(path="gone.png")]


async def test_a_picture_outside_the_workspace_is_still_refused(make_channel, fake, tmp_path):
    channel = make_channel()
    (tmp_path / "secret.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    await channel.outbound().send("FILE: ../secret.png")
    assert fake.uploads == []
    assert fake.sent == [texts.TELEGRAM_MEDIA_MISSING.format(path="../secret.png")]


async def test_a_markup_picture_on_a_file_line_is_still_refused(make_channel, fake):
    channel = make_channel()
    write(channel, "hinh.svg", b"<svg/>")
    await channel.outbound().send("FILE: hinh.svg")
    assert fake.uploads == []
    assert fake.sent == [texts.TELEGRAM_FILE_MISSING.format(path="hinh.svg")]
