"""What a canvas may hold: its kind decides whether the payload is text or bytes, and how
large one version may grow."""

import pytest

from my_agent_crew.artifacts.kinds import (
    BINARY_KINDS,
    KINDS,
    LANGUAGE_MAX,
    TEXT_KINDS,
    TITLE_MAX,
    ArtifactTooLarge,
    InvalidLanguage,
    InvalidTitle,
    PayloadMismatch,
    StorageFull,
    UnknownKind,
    cap_bytes,
    check_kind,
    check_payload,
    check_size,
    clean_language,
    clean_title,
)

KB, MB = 1024, 1024 * 1024


def test_every_kind_is_either_text_or_binary_never_both():
    assert set(KINDS) == TEXT_KINDS | BINARY_KINDS
    assert not TEXT_KINDS & BINARY_KINDS
    assert BINARY_KINDS == {"image"}


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
