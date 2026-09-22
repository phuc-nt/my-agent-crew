"""A `FILE:` line in a reply: the agent handing over a document it produced.

`MEDIA:` already existed for images. A document needs its own line because Telegram
re-encodes photos, so a CSV sent as one is refused and a PDF arrives as a picture. The
guards tested here are the two a photo does not need — the format and the size — plus the
workspace containment every attachment shares.
"""

from __future__ import annotations

import logging

import pytest

from my_agent_crew import texts
from my_agent_crew.channels.telegram_attachments import (
    DOCUMENT_SUFFIXES,
    MAX_DOCUMENT_BYTES,
    allowed_suffix_list,
    document_suffix_allowed,
    split_reply,
)
from tests.telegram_fake import CHAT


def write(channel, relative: str, content: bytes = b"col\n1\n"):
    path = channel.deps.agent.workspace / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_a_file_line_is_split_from_the_prose_beside_the_media_line():
    prose, media, files = split_reply(
        "Báo cáo đây:\nMEDIA: out/chart.png\nFILE: out/brief.pdf\nxong"
    )
    assert prose == "Báo cáo đây:\nxong"
    assert media == ["out/chart.png"]
    assert files == ["out/brief.pdf"]


def test_a_sentence_mentioning_the_word_stays_prose():
    """The prefix must start the line, or an answer explaining the feature sends a file."""
    prose, media, files = split_reply("Dùng dòng FILE: để gửi tệp.\nFILE: a.pdf")
    assert files == ["a.pdf"]
    assert media == [] and "Dùng dòng FILE:" in prose


def test_several_file_lines_keep_the_order_the_reply_named_them():
    _, _, files = split_reply("FILE: a.csv\ngiữa\nFILE: b.pdf")
    assert files == ["a.csv", "b.pdf"]


@pytest.mark.parametrize("name", ["a.pdf", "a.csv", "a.md", "a.txt", "a.xlsx", "a.json", "a.zip"])
def test_the_formats_a_person_asks_to_receive_are_allowed(name):
    assert document_suffix_allowed(name)


@pytest.mark.parametrize("name", ["a.env", "key.pem", "id_rsa", "a.sqlite", "a.sh", "a"])
def test_anything_else_is_refused(name):
    """A reply is one line away from mailing out whatever the agent can write."""
    assert not document_suffix_allowed(name)


def test_the_extension_check_ignores_case():
    """A reply naming `Brief.PDF` means the file `brief.pdf`."""
    assert document_suffix_allowed("out/Brief.PDF")


def test_the_refusal_lists_the_formats_in_a_stable_order():
    """Set order would make the same refusal read differently run to run."""
    assert allowed_suffix_list() == ", ".join(sorted(s.lstrip(".") for s in DOCUMENT_SUFFIXES))


async def test_a_file_line_sends_the_document_and_keeps_the_prose(make_channel, fake):
    channel = make_channel()
    write(channel, "out/brief.csv", b"ngay,so\n2026-09-23,1\n")
    await channel.outbound().send("Số liệu đây.\nFILE: out/brief.csv")
    assert fake.sent == ["Số liệu đây."]
    assert len(fake.documents) == 1
    # Sent as a document, not a photo: Telegram would refuse a CSV as an image.
    assert "sendDocument" in fake.calls and "sendPhoto" not in fake.calls
    assert b"ngay,so" in fake.documents[0]


async def test_the_filename_rides_along_so_the_chat_shows_a_named_file(make_channel, fake):
    """Uploaded without a name, the document arrives as an untitled blob."""
    channel = make_channel()
    write(channel, "out/brief.pdf", b"%PDF-1.4\n")
    await channel.outbound().send("FILE: out/brief.pdf")
    assert b"brief.pdf" in fake.documents[0]


async def test_a_photo_and_a_document_in_one_reply_each_go_their_own_way(make_channel, fake):
    channel = make_channel()
    write(channel, "out/chart.png", b"\x89PNG\r\n")
    write(channel, "out/brief.pdf", b"%PDF-1.4\n")
    await channel.outbound().send("Xong.\nMEDIA: out/chart.png\nFILE: out/brief.pdf")
    assert len(fake.photos) == 1 and len(fake.documents) == 1


async def test_a_path_outside_the_workspace_is_refused_and_said_out_loud(
    make_channel, fake, tmp_path, caplog
):
    """The reply's prose has already gone out, so a silent failure leaves an answer that
    promises a file with no word about why none arrived."""
    channel = make_channel()
    outside = tmp_path / "secret.pdf"
    outside.write_bytes(b"%PDF-1.4\n")
    with caplog.at_level(logging.WARNING, logger="my_agent_crew.channels"):
        await channel.outbound().send(f"Đây.\nFILE: ../{outside.name}")
    assert fake.documents == []
    assert texts.TELEGRAM_FILE_MISSING.format(path=f"../{outside.name}") in fake.sent
    assert "Đây." in fake.sent


async def test_a_disallowed_format_is_refused_even_inside_the_workspace(make_channel, fake):
    """Containment is not enough: an agent can write a key file into its own workspace."""
    channel = make_channel()
    write(channel, "secrets.env", b"TOKEN=abc\n")
    await channel.outbound().send("FILE: secrets.env")
    assert fake.documents == []
    assert texts.TELEGRAM_FILE_MISSING.format(path="secrets.env") in fake.sent


async def test_a_file_too_large_for_a_chat_is_refused(make_channel, fake):
    channel = make_channel()
    write(channel, "big.zip", b"0" * (MAX_DOCUMENT_BYTES + 1))
    await channel.outbound().send("FILE: big.zip")
    assert fake.documents == []
    assert texts.TELEGRAM_FILE_MISSING.format(path="big.zip") in fake.sent


async def test_a_file_at_the_cap_still_goes_through(make_channel, fake):
    """The cap is a limit, not a threshold one byte below the limit."""
    channel = make_channel()
    write(channel, "big.zip", b"0" * MAX_DOCUMENT_BYTES)
    await channel.outbound().send("FILE: big.zip")
    assert len(fake.documents) == 1


async def test_a_missing_file_is_reported_rather_than_raised(make_channel, fake):
    channel = make_channel()
    await channel.outbound().send("FILE: out/never-written.pdf")
    assert fake.documents == []
    assert texts.TELEGRAM_FILE_MISSING.format(path="out/never-written.pdf") in fake.sent


async def test_one_bad_attachment_does_not_stop_the_next(make_channel, fake):
    """Each attachment is reported on its own, so the first failure cannot swallow the rest."""
    channel = make_channel()
    write(channel, "ok.pdf", b"%PDF-1.4\n")
    await channel.outbound().send("FILE: missing.pdf\nFILE: ok.pdf")
    assert len(fake.documents) == 1
    assert texts.TELEGRAM_FILE_MISSING.format(path="missing.pdf") in fake.sent


async def test_a_photo_failure_still_says_it_was_a_photo(make_channel, fake):
    """The two kinds share one code path now; they must not share one message."""
    channel = make_channel()
    await channel.outbound().send("MEDIA: gone.png")
    assert texts.TELEGRAM_MEDIA_MISSING.format(path="gone.png") in fake.sent
    assert texts.TELEGRAM_FILE_MISSING.format(path="gone.png") not in fake.sent


async def test_a_reply_that_is_only_a_file_line_sends_no_empty_message(make_channel, fake):
    channel = make_channel()
    write(channel, "brief.pdf", b"%PDF-1.4\n")
    await channel.outbound().send("FILE: brief.pdf")
    assert fake.sent == []
    assert len(fake.documents) == 1


async def test_the_document_goes_to_the_one_allowed_chat(make_channel, fake):
    channel = make_channel()
    write(channel, "brief.pdf", b"%PDF-1.4\n")
    await channel.outbound().send("FILE: brief.pdf")
    assert str(CHAT).encode() in fake.documents[0]
