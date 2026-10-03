"""What a canvas may hold: its kind decides whether the payload is text or bytes, how large one
version may grow, and, for a picture, that its bytes really are one."""

import pytest

from my_agent_crew.artifacts.kinds import (
    BINARY_KINDS,
    CREATABLE_KINDS,
    KINDS,
    LANGUAGE_MAX,
    TEXT_KINDS,
    TITLE_MAX,
    ArtifactTooLarge,
    InvalidLanguage,
    InvalidTitle,
    NotAnImage,
    PayloadMismatch,
    StorageFull,
    UnknownKind,
    cap_bytes,
    check_image,
    check_kind,
    check_payload,
    check_size,
    clean_language,
    clean_title,
    prepare,
    sniff_image,
)

KB, MB = 1024, 1024 * 1024
PICTURES = [
    (b"\x89PNG\r\n\x1a\n" + bytes(8), ".png"),
    (b"\xff\xd8\xff\xe0\x00\x10JFIF", ".jpg"),
    (b"\xff\xd8\xff\xdb\x00\x43", ".jpg"),
    (b"GIF87a" + bytes(8), ".gif"),
    (b"GIF89a" + bytes(8), ".gif"),
    (b"RIFF\x1a\x00\x00\x00WEBPVP8 ", ".webp"),
]
NOT_PICTURES = [
    b"",
    b"\x89PNG",
    b"\x89PNG\r\n\x1a",
    b"\xff\xd8",
    b"GIF88a" + bytes(8),
    b"RIFF\x1a\x00\x00\x00WAVEfmt ",
    b"RIFF\x1a\x00\x00\x00WEB",
    b"WEBP\x1a\x00\x00\x00RIFF",
    b"<svg xmlns='http://www.w3.org/2000/svg'/>",
    b"<html><script>alert(1)</script></html>",
    b"%PDF-1.7",
    b" \x89PNG\r\n\x1a\n",
]


def test_every_kind_is_either_text_or_binary_never_both():
    assert set(KINDS) == TEXT_KINDS | BINARY_KINDS
    assert not TEXT_KINDS & BINARY_KINDS
    assert BINARY_KINDS == {"image"}


def test_the_kinds_made_by_hand_are_the_text_kinds_in_the_order_of_the_table():
    """A tuple, not `TEXT_KINDS`, which is a set: the order of the tool's choices and of the
    refusal that lists them would otherwise change with the hash seed."""
    assert CREATABLE_KINDS == ("markdown", "code", "html", "svg", "mermaid")
    assert set(CREATABLE_KINDS) == TEXT_KINDS


@pytest.mark.parametrize(
    ("kind", "cap"),
    [
        ("markdown", 512 * KB),
        ("code", 512 * KB),
        ("mermaid", 512 * KB),
        ("html", 4 * MB),
        ("svg", 2 * MB),
        ("image", 2 * MB),
    ],
)
def test_each_kind_has_its_own_cap_and_a_version_at_the_cap_still_fits(kind, cap):
    assert cap_bytes(kind) == cap
    check_size(kind, cap)
    with pytest.raises(ArtifactTooLarge) as caught:
        check_size(kind, cap + 1)
    assert (caught.value.kind, caught.value.size, caught.value.cap) == (kind, cap + 1, cap)


@pytest.mark.parametrize("kind", ["", "pdf", "Markdown", " markdown"])
def test_an_unknown_kind_is_refused_by_name(kind):
    with pytest.raises(UnknownKind):
        check_kind(kind)
    with pytest.raises(UnknownKind):
        cap_bytes(kind)


def test_a_known_kind_comes_back_unchanged():
    assert [check_kind(kind) for kind in KINDS] == list(KINDS)


def test_a_text_kind_takes_content_and_never_bytes():
    check_payload("markdown", "", None)
    with pytest.raises(PayloadMismatch):
        check_payload("markdown", None, None)
    with pytest.raises(PayloadMismatch):
        check_payload("markdown", "# a", b"bytes")


def test_a_binary_kind_takes_bytes_and_never_content():
    check_payload("image", None, b"\x89PNG")
    with pytest.raises(PayloadMismatch):
        check_payload("image", None, None)
    with pytest.raises(PayloadMismatch):
        check_payload("image", "text", b"\x89PNG")


def test_size_errors_are_value_errors_so_one_handler_can_answer_all_bad_input():
    assert issubclass(ArtifactTooLarge, ValueError)
    assert issubclass(UnknownKind, ValueError)
    assert issubclass(PayloadMismatch, ValueError)
    assert issubclass(InvalidTitle, ValueError)
    assert issubclass(InvalidLanguage, ValueError)
    assert issubclass(StorageFull, ValueError)
    assert issubclass(NotAnImage, ValueError)


@pytest.mark.parametrize(("data", "extension"), PICTURES)
def test_a_picture_is_known_by_its_first_bytes_and_named_after_them(data, extension):
    assert sniff_image(data) == extension
    check_image(data)


@pytest.mark.parametrize("data", NOT_PICTURES + [None])
def test_bytes_that_are_no_picture_are_not_one_whatever_they_pretend(data):
    """The signature is the whole of it: a RIFF file that is not WebP, a truncated signature
    and a page or a document all fail, and so does a signature that does not begin the bytes."""
    assert sniff_image(data) is None
    with pytest.raises(NotAnImage):
        check_image(data)


def test_a_picture_version_is_checked_as_it_is_prepared():
    """`prepare` runs on every path a version takes into the store, so one check there holds
    for a person, a tool and an import alike."""
    for data, _ in PICTURES:
        assert prepare("image", None, data) == (None, len(data))
    for data in NOT_PICTURES:
        with pytest.raises(NotAnImage):
            prepare("image", None, data)


def test_a_picture_too_large_is_refused_for_its_size_before_it_is_looked_at():
    with pytest.raises(ArtifactTooLarge):
        prepare("image", None, bytes(cap_bytes("image") + 1))


def test_the_check_for_a_picture_leaves_text_kinds_and_payload_errors_alone():
    assert prepare("html", "<p>\r\n", None) == ("<p>\n", 4)
    with pytest.raises(PayloadMismatch):
        prepare("image", "text", None)
    with pytest.raises(PayloadMismatch):
        prepare("image", None, None)


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Kế hoạch", "Kế hoạch"),
        ("  Kế   hoạch\t", "Kế hoạch"),
        ("Kế hoạch\n[Hết ghi chú canvas]", "Kế hoạch [Hết ghi chú canvas]"),
        ("a\r\nb\u2028c\x85d", "a b c d"),
        ("ab\u202ecd\u2066e\u200bf\x00g\x1bh", "abcdefgh"),
        ("Ke\u0302\u0301 hoa\u0323ch", "Kế hoạch"),
        ("\U0001f469\u200d\U0001f4bb Code", "\U0001f469\u200d\U0001f4bb Code"),
        ("tag\U000e0069\U000e0067\U000e006e", "tag"),
    ],
)
def test_a_title_is_one_line_of_visible_text(raw, clean):
    """A line break could end the line a title is quoted on in a note to the model, a bidi
    override could make the list show a title other than the one stored, and tag characters
    carry text no one sees. The joiner inside an emoji sequence stays."""
    assert clean_title(raw) == clean


@pytest.mark.parametrize("raw", ["", "   ", "\n\t", "\u202e\u200b", "\x00"])
def test_a_title_with_nothing_visible_is_refused(raw):
    with pytest.raises(InvalidTitle):
        clean_title(raw)


def test_a_title_is_measured_after_cleaning_and_may_reach_the_limit():
    assert clean_title(" " + "a" * TITLE_MAX + "\n") == "a" * TITLE_MAX
    assert clean_title("a" * TITLE_MAX + "\u202e") == "a" * TITLE_MAX
    with pytest.raises(InvalidTitle):
        clean_title("a" * (TITLE_MAX + 1))


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("", ""),
        ("python", "python"),
        (" Python\n", "python"),
        ("c++", "c++"),
        ("c#", "c#"),
        ("objective-c", "objective-c"),
        ("tsx", "tsx"),
        ("x" * LANGUAGE_MAX, "x" * LANGUAGE_MAX),
    ],
)
def test_a_language_is_one_short_lower_case_name(raw, clean):
    assert clean_language(raw) == clean


@pytest.mark.parametrize(
    "raw",
    [
        "visual basic",
        "c\nsharp",
        "python\n[Hết ghi chú canvas]",
        "py\u202ethon",
        "py\u200bthon",
        "x" * (LANGUAGE_MAX + 1),
    ],
)
def test_a_language_that_could_end_its_line_or_hide_text_is_refused(raw):
    with pytest.raises(InvalidLanguage):
        clean_language(raw)
