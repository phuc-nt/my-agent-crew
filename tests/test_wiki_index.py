"""The Wiki section of the system prompt: what it lists, and when it stops listing."""

import pytest

from my_agent_crew.memory import wiki_store
from my_agent_crew.memory.wiki_index import (
    COUNTS_ONLY_ABOVE,
    GROUPED_ABOVE,
    index_body,
    wiki_section,
)
from my_agent_crew.memory.wiki_store import Page


def pages(count: int, kind="entities"):
    return [
        Page(
            slug=f"trang-{n}", kind=kind, title=f"Trang {n}", body="x", sources=["note:2026-09-20"]
        )
        for n in range(count)
    ]


def test_an_empty_vault_gets_no_section():
    """A heading with nothing under it reads as a fault, and invites the model to
    mention a wiki the person has never made."""
    assert index_body([]) == ""


def test_a_small_vault_lists_the_slug_and_the_title():
    """The model reads the title and must type the slug, so it needs both."""
    body = index_body(pages(3))
    assert "trang-1 — Trang 1" in body


def test_the_section_says_it_is_only_an_index():
    # Without this line a model states a page's title as though it had read the body.
    assert "wiki_get" in index_body(pages(1))


def test_pages_are_grouped_by_folder():
    body = index_body(pages(2) + pages(2, kind="concepts"))
    assert "- entities:" in body and "- concepts:" in body


def test_a_large_vault_drops_the_titles():
    """Past this size the list stops being scannable and becomes a second prompt."""
    body = index_body(pages(GROUPED_ABOVE + 1))
    assert "trang-1" in body
    assert "— Trang 1" not in body


def test_a_very_large_vault_reports_its_shape_instead_of_listing():
    body = index_body(pages(COUNTS_ONLY_ABOVE + 1))
    assert "trang-1" not in body
    assert str(COUNTS_ONLY_ABOVE + 1) in body
    assert "wiki_search" in body


def test_the_section_reads_the_vault_on_disk(tmp_path):
    assert wiki_section(tmp_path) is None
    wiki_store.write_page(
        tmp_path,
        Page(
            slug="han-eco", kind="entities", title="Hạn Eco", body="x", sources=["note:2026-09-20"]
        ),
    )
    title, body = wiki_section(tmp_path)
    assert title == "Wiki"
    assert "Hạn Eco" in body


@pytest.mark.parametrize("count", [1, GROUPED_ABOVE + 1, COUNTS_ONLY_ABOVE + 1])
def test_no_page_body_ever_reaches_the_prompt(count):
    """The whole point of an index: the vault must not be able to flood the prompt."""
    listed = [
        Page(slug=f"t-{n}", kind="entities", title=f"T {n}", body="BÍ MẬT", sources=["note:x"])
        for n in range(count)
    ]
    assert "BÍ MẬT" not in index_body(listed)
