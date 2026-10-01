"""What a canvas may hold: its kind decides whether the payload is text or bytes, and how
large one version may grow."""

import pytest

from my_agent_crew.artifacts.kinds import (
    BINARY_KINDS,
    KINDS,
    TEXT_KINDS,
    ArtifactTooLarge,
    PayloadMismatch,
    UnknownKind,
    cap_bytes,
    check_kind,
    check_payload,
    check_size,
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
