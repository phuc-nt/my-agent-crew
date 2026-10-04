"""A canvas sent to the chat as a file: what a `FILE: artifact:<id>` or `MEDIA: artifact:<id>`
line of a reply asks for.

It leaves from memory, under a name a phone opens as text, with the secrets this process knows
covered in its text and its title. Whatever goes wrong is one line in the chat and never an
exception, because the prose of the reply has already gone out by then. Who may send which
canvas is in `test_telegram_canvas_scope.py`.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from my_agent_crew import texts
from my_agent_crew.channels import TelegramApi, telegram_canvas_file
from my_agent_crew.channels.telegram_api import SEND_TIMEOUT_SECONDS
from my_agent_crew.channels.telegram_canvas_file import canvas_link, telegram_filename
from my_agent_crew.config import Route
from my_agent_crew.reply_attachments import artifact_ref
from my_agent_crew.store.artifact_models import USER
from tests.canvas_helpers import PLAN, PNG
from tests.telegram_fake import CHAT, TOKEN, FakeTelegram, Upload, multipart

ID = "0123456789ab"
COVERED = texts.TRAJECTORY_REDACTED
CAPTION_LIMIT = 1024  # Telegram's own, for a photo and a document alike


def canvas(
    store,
    content: str | None = PLAN,
    *,
    title: str = "Kế hoạch",
    kind: str = "markdown",
    language: str = "",
    data: bytes | None = None,
) -> str:
    """A canvas a person made on the web, which the master reaches like every other."""
    return store.artifacts.create(title, kind, "", USER, "", content, data, language).id


def picture(store, data: bytes = PNG, title: str = "Biểu đồ") -> str:
    return canvas(store, None, title=title, kind="image", data=data)


def missing(artifact_id: str) -> str:
    return texts.TELEGRAM_CANVAS_MISSING.format(id=artifact_id)


def failed(artifact_id: str) -> str:
    return texts.TELEGRAM_CANVAS_FAILED.format(id=artifact_id)


@pytest.mark.parametrize(
    ("path", "ref"),
    [
        (f"artifact:{ID}", ID),
        (f"artifact: {ID} ", ID),
        ("artifact:0123456789AB", ""),
        ("artifact:", ""),
        ("artifact:0123456789a", ""),
        ("artifact:0123456789abc", ""),
        (f"artifact:{ID} v2", ""),
        ("artifact:../x", ""),
        ("artifact:0123456789ag", ""),
        ("out/brief.pdf", None),
        (f"Artifact:{ID}", None),
        (f"notes/artifact:{ID}", None),
        (f" artifact:{ID}", None),
        ("", None),
    ],
)
def test_a_path_names_a_canvas_only_as_the_prefix_and_a_whole_id(path, ref):
    """The id, "" for a line that set out to name a canvas and did not, None for a file path."""
    assert artifact_ref(path) == ref
    assert (artifact_ref(path) is None) == (ref is None)


async def test_a_markdown_canvas_arrives_as_a_document_with_its_secrets_covered(
    make_channel, fake, monkeypatch
):
    monkeypatch.setenv("CANVAS_TEST_TOKEN", "tok-93f1c07a55")
    channel = make_channel()
    text = "# Kế hoạch\nkhoá: tok-93f1c07a55\nvà sk-abcdefghijklmnop1234 nữa\n"
    art = canvas(channel.store, text)
    await channel.outbound().send(f"Đây nhé.\nFILE: artifact:{art}")
    sent = f"# Kế hoạch\nkhoá: {COVERED}\nvà {COVERED} nữa\n".encode()
    assert fake.uploads == [Upload("sendDocument", "Kế hoạch.md", '"Kế hoạch" v1', sent)]
    assert fake.sent == ["Đây nhé."]


@pytest.mark.parametrize(
    ("kind", "language", "name"),
    [
        ("markdown", "", "Bản nháp.md"),
        ("code", "python", "Bản nháp.py.txt"),
        ("code", "cobol", "Bản nháp.txt"),
        ("code", "", "Bản nháp.txt"),
        ("html", "", "Bản nháp.html.txt"),
        ("svg", "", "Bản nháp.svg.txt"),
        ("mermaid", "", "Bản nháp.mmd.txt"),
    ],
)
async def test_a_text_canvas_is_named_so_a_phone_opens_it_as_text(
    make_channel, fake, kind, language, name
):
    """Only markdown keeps its own extension last; code in a language with no extension of
    its own already ends in `.txt` and gets no second one."""
    channel = make_channel()
    art = canvas(channel.store, "x = 1\n", title="Bản nháp", kind=kind, language=language)
    await channel.outbound().send(f"FILE: artifact:{art}")
    assert [tuple(upload) for upload in fake.uploads] == [
        ("sendDocument", name, '"Bản nháp" v1', b"x = 1\n")
    ]


def test_a_picture_is_named_by_what_its_bytes_are():
    assert telegram_filename("Biểu đồ", "image", "", PNG) == "Biểu đồ.png"
    assert telegram_filename("Biểu đồ", "image", "", b"not a picture") == "Biểu đồ.bin"
    assert telegram_filename("ghi chú.txt", "code") == "ghi chú.txt.txt"
    assert telegram_filename("ghi chú.txt", "markdown") == "ghi chú.txt.md"


@pytest.mark.parametrize("prefix", ["MEDIA", "FILE"])
async def test_a_picture_arrives_as_a_photo_with_its_bytes_as_they_are(make_channel, fake, prefix):
    """The kind decides how a canvas travels, not the prefix of the line that named it. The
    bytes hold something shaped like a key, and nothing in a picture is covered."""
    channel = make_channel()
    data = PNG + b" sk-abcdefghijklmnop1234"
    art = picture(channel.store, data)
    await channel.outbound().send(f"{prefix}: artifact:{art}")
    assert fake.uploads == [Upload("sendPhoto", "Biểu đồ.png", '"Biểu đồ" v1', data)]
    assert fake.sent == []


async def test_a_text_canvas_on_a_media_line_is_still_a_document(make_channel, fake):
    channel = make_channel()
    art = canvas(channel.store)
    await channel.outbound().send(f"MEDIA: artifact:{art}")
    assert [(upload.method, upload.name) for upload in fake.uploads] == [
        ("sendDocument", "Kế hoạch.md")
    ]


async def test_the_newest_version_is_sent_and_the_caption_says_which(make_channel, fake):
    channel = make_channel()
    store = channel.store
    art = canvas(store, "# bản một\n")
    assert store.artifacts.write(art, "# bản hai\n", "agent:default", "").version == 2
    await channel.outbound().send(f"FILE: artifact:{art}")
    assert fake.uploads == [
        Upload("sendDocument", "Kế hoạch.md", '"Kế hoạch" v2', "# bản hai\n".encode())
    ]


async def test_the_caption_ends_with_a_link_when_the_web_has_an_address(
    make_channel, fake, deps_factory
):
    channel = make_channel(
        deps_factory(routes=(Route("fake", "echo"),), web_url="http://h:8765/crew")
    )
    art = canvas(channel.store)
    await channel.outbound().send(f"FILE: artifact:{art}")
    link = f"http://h:8765/crew/#/manage/canvas/{art}"
    assert [upload.caption for upload in fake.uploads] == [f'"Kế hoạch" v1\n{link}']
    assert canvas_link("http://h:8765/crew", art) == link and canvas_link("", art) == ""


@pytest.mark.parametrize("over", [0, 1])
async def test_a_link_that_would_make_the_caption_too_long_is_left_out(
    make_channel, fake, deps_factory, over
):
    """Telegram refuses a caption over its limit, file and all. The link is dropped whole
    rather than cut: half an address opens nothing."""
    start, tail = '"Kế hoạch" v1\nhttp://h/', f"/#/manage/canvas/{ID}"
    web_url = "http://h/" + "a" * (CAPTION_LIMIT - len(start) - len(tail) + over)
    channel = make_channel(deps_factory(routes=(Route("fake", "echo"),), web_url=web_url))
    art = canvas(channel.store)
    await channel.outbound().send(f"FILE: artifact:{art}")
    [upload] = fake.uploads
    if over:
        assert upload.caption == '"Kế hoạch" v1'
    else:
        assert upload.caption == f'"Kế hoạch" v1\n{web_url}/#/manage/canvas/{art}'
        assert len(upload.caption) == CAPTION_LIMIT


async def test_a_secret_in_the_title_reaches_neither_the_caption_nor_the_file_name(
    make_channel, fake, monkeypatch
):
    monkeypatch.setenv("CANVAS_TEST_PASSWORD", "hunter2-hunter2")
    channel = make_channel()
    art = canvas(channel.store, title="Khoá hunter2-hunter2 của tôi")
    await channel.outbound().send(f"FILE: artifact:{art}")
    [upload] = fake.uploads
    assert upload.caption == f'"Khoá {COVERED} của tôi" v1'
    assert upload.name == f"Khoá {COVERED} của tôi.md"


async def test_the_caption_is_plain_text_like_every_message(make_channel, fake):
    """Nothing is sent with a parse mode, so the markers a title holds would show as typed."""
    channel = make_channel()
    art = canvas(channel.store, title="**Tuần** này")
    await channel.outbound().send(f"FILE: artifact:{art}")
    assert [upload.caption for upload in fake.uploads] == ['"Tuần này" v1']


async def test_a_picture_refused_as_a_photo_arrives_as_a_document(make_channel, fake):
    """Telegram takes a photo only within its own limits of size and shape; the same bytes
    under the same name and caption still fit as a document, and nothing is called a failure."""
    channel = make_channel()
    art = picture(channel.store)
    fake.fail["sendPhoto"] = 400
    await channel.outbound().send(f"MEDIA: artifact:{art}")
    assert fake.uploads == [Upload("sendDocument", "Biểu đồ.png", '"Biểu đồ" v1', PNG)]
    assert fake.calls == ["sendPhoto", "sendDocument"] and fake.sent == []


async def test_a_picture_refused_both_ways_is_tried_once_more_and_no_further(make_channel, fake):
    channel = make_channel()
    art = picture(channel.store)
    fake.fail.update(sendPhoto=400, sendDocument=400)
    await channel.outbound().send(f"MEDIA: artifact:{art}")
    assert fake.calls == ["sendPhoto", "sendDocument", "sendMessage"]
    assert fake.sent == [failed(art)] and fake.uploads == []


async def test_a_photo_that_fails_for_another_reason_is_not_sent_again(make_channel, fake):
    """Only a refusal of the picture itself is worth a second way in: a Telegram that is down
    or is asking for a pause would take the document no better."""
    channel = make_channel()
    art = picture(channel.store)
    fake.fail["sendPhoto"] = 500
    await channel.outbound().send(f"MEDIA: artifact:{art}")
    assert fake.calls == ["sendPhoto", "sendMessage"] and fake.sent == [failed(art)]


async def test_a_document_that_is_refused_is_not_sent_again(make_channel, fake):
    channel = make_channel()
    art = canvas(channel.store)
    fake.fail["sendDocument"] = 400
    await channel.outbound().send(f"FILE: artifact:{art}")
    assert fake.calls == ["sendDocument", "sendMessage"] and fake.sent == [failed(art)]


async def test_a_canvas_that_cannot_be_sent_does_not_stop_the_next(make_channel, fake, caplog):
    """One line says which canvas did not arrive; why is in the log, not in the chat."""
    channel = make_channel()
    text, image = canvas(channel.store), picture(channel.store)
    fake.fail["sendDocument"] = 500
    with caplog.at_level(logging.WARNING, logger="my_agent_crew.channels"):
        await channel.outbound().send(f"Xong.\nFILE: artifact:{text}\nFILE: artifact:{image}")
    assert fake.sent == ["Xong.", failed(text)]
    assert [(upload.method, upload.data) for upload in fake.uploads] == [("sendPhoto", PNG)]
    [warning] = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert text in warning and "HTTP 500" in warning


@pytest.mark.parametrize("over", [0, 1])
async def test_a_canvas_over_what_a_chat_takes_is_not_uploaded(
    make_channel, fake, monkeypatch, caplog, over
):
    """Measured in the bytes that would travel, which for text are more than its characters."""
    content = "é" * 8  # 16 bytes
    monkeypatch.setattr(telegram_canvas_file, "MAX_DOCUMENT_BYTES", 16 - over)
    channel = make_channel()
    art = canvas(channel.store, content)
    with caplog.at_level(logging.WARNING, logger="my_agent_crew.channels"):
        await channel.outbound().send(f"FILE: artifact:{art}")
    if not over:
        assert [upload.data for upload in fake.uploads] == [content.encode()] and fake.sent == []
        return
    assert fake.calls == ["sendMessage"] and fake.sent == [failed(art)]
    [warning] = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert art in warning and "16" in warning and "15" in warning


async def test_a_canvas_named_twice_in_one_reply_is_sent_once(make_channel, fake):
    channel = make_channel()
    first, second = canvas(channel.store, "một\n"), canvas(channel.store, "hai\n")
    reply = (
        f"MEDIA: artifact:{second}\nFILE: artifact:{first}\n"
        f"FILE: artifact:{second}\nFILE: artifact:{first}"
    )
    await channel.outbound().send(reply)
    assert [upload.data for upload in fake.uploads] == [b"hai\n", "một\n".encode()]


async def test_lines_that_misname_a_canvas_get_one_notice_that_repeats_none_of_them(
    make_channel, fake
):
    """What follows `artifact:` is the model's text, which may be anything; the chat is told
    once that a line was wrong and never what the line said. The canvas named well is sent."""
    channel = make_channel()
    art = canvas(channel.store)
    reply = f"FILE: artifact:../../etc/passwd\nFILE: artifact:{art}\nMEDIA: artifact:{ID.upper()}"
    await channel.outbound().send(reply)
    assert fake.sent == [texts.TELEGRAM_CANVAS_BAD_REF]
    assert [upload.name for upload in fake.uploads] == ["Kế hoạch.md"]
    assert "{" not in texts.TELEGRAM_CANVAS_BAD_REF


async def test_a_canvas_that_is_not_there_is_said_so(make_channel, fake):
    channel = make_channel()
    art = canvas(channel.store)
    channel.store.artifacts.delete(art)
    await channel.outbound().send(f"FILE: artifact:{art}\nFILE: artifact:{ID}")
    assert fake.sent == [missing(art), missing(ID)] and fake.uploads == []


async def test_a_notice_about_a_canvas_that_cannot_be_sent_stops_nothing(make_channel, fake):
    """Like the notice about a workspace file: one more call to a Telegram that may be failing."""
    channel = make_channel()
    art = canvas(channel.store)
    fake.fail["sendMessage"] = 500
    await channel.outbound().send(f"FILE: artifact:{ID}\nFILE: artifact:x\nFILE: artifact:{art}")
    assert [upload.name for upload in fake.uploads] == ["Kế hoạch.md"]
    assert fake.sent == [] and fake.calls.count("sendMessage") == 2


async def test_the_log_names_the_canvas_by_id_version_and_size_alone(make_channel, fake, caplog):
    channel = make_channel()
    art = canvas(channel.store, "nội dung riêng\n", title="Tên riêng")
    with caplog.at_level(logging.INFO, logger="my_agent_crew.channels"):
        await channel.outbound().send(f"FILE: artifact:{art}")
    size = len("nội dung riêng\n".encode())
    lines = [r.getMessage() for r in caplog.records if r.name.endswith("telegram_canvas_file")]
    assert lines == [f"telegram default: sent canvas {art} v1 ({size} bytes)"]
    assert not any("riêng" in r.getMessage() for r in caplog.records)


async def test_workspace_files_go_first_and_as_before_then_the_canvases(make_channel, fake):
    channel = make_channel()
    workspace = channel.deps.agent.workspace
    (workspace / "brief.pdf").write_bytes(b"%PDF-1.4\n")
    (workspace / "chart.png").write_bytes(b"PNGDATA")
    art, image = canvas(channel.store), picture(channel.store)
    reply = (
        f"Đủ cả.\nFILE: artifact:{art}\nFILE: brief.pdf\nMEDIA: artifact:{image}\n"
        "MEDIA: chart.png\nFILE: gone.pdf"
    )
    await channel.outbound().send(reply)
    assert [tuple(upload) for upload in fake.uploads] == [
        ("sendPhoto", "chart.png", "", b"PNGDATA"),
        ("sendDocument", "brief.pdf", "", b"%PDF-1.4\n"),
        ("sendPhoto", "Biểu đồ.png", '"Biểu đồ" v1', PNG),
        ("sendDocument", "Kế hoạch.md", '"Kế hoạch" v1', PLAN.encode()),
    ]
    assert fake.sent == ["Đủ cả.", texts.TELEGRAM_FILE_MISSING.format(path="gone.pdf")]


def recording_api(fake: FakeTelegram, seen: list[httpx.Request]) -> TelegramApi:
    def handler(request: httpx.Request):
        seen.append(request)
        return fake.handler(request)

    return TelegramApi(TOKEN, httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize(
    ("as_photo", "method", "field"),
    [(False, "sendDocument", "document"), (True, "sendPhoto", "photo")],
)
async def test_bytes_are_uploaded_under_a_name_with_a_bounded_wait(fake, as_photo, method, field):
    """A message waits as long as Telegram takes; megabytes from memory are given a minute,
    so a line that stalls mid-upload ends as a failure the chat is told about."""
    seen: list[httpx.Request] = []
    api = recording_api(fake, seen)
    await api.send_bytes(CHAT, "a.txt", b"bytes", "**Tên** tệp", as_photo=as_photo)
    await api.send_bytes(CHAT, "b.txt", b"more", as_photo=as_photo)
    assert fake.calls == [method, method]
    first, second = (multipart(request) for request in seen)
    assert first == {
        "chat_id": ("", str(CHAT).encode()),
        "caption": ("", "Tên tệp".encode()),
        field: ("a.txt", b"bytes"),
    }
    assert second == {"chat_id": ("", str(CHAT).encode()), field: ("b.txt", b"more")}
    waits = set(seen[0].extensions["timeout"].values())
    assert waits == {SEND_TIMEOUT_SECONDS} and 0 < SEND_TIMEOUT_SECONDS <= 60
