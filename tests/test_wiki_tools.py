"""The three wiki tools, and what `memory_search` does once a vault exists."""

import pytest

from my_agent_crew.memory import wiki_links, wiki_store
from my_agent_crew.memory.wiki_store import Page
from my_agent_crew.tools.memory import search_memory
from my_agent_crew.tools.registry import ToolError
from my_agent_crew.tools.wiki import build_wiki_tools


@pytest.fixture
def tools(tmp_path):
    return {tool.name: tool for tool in build_wiki_tools(tmp_path)}


def a_page(tmp_path, slug="han-eco", **kwargs):
    fields = {
        "slug": slug,
        "kind": "entities",
        "title": "Hạn Eco",
        "body": "Hạn nộp hồ sơ là thứ tư.",
        "sources": ["note:2026-09-20"],
        **kwargs,
    }
    return wiki_store.write_page(tmp_path, Page(**fields))


async def test_getting_a_page_shows_what_it_is_built_on(tmp_path, tools):
    """Sources on screen are the difference between a claim and a citation."""
    a_page(tmp_path, questions=["Dời sang thứ sáu?"])
    out = await tools["wiki_get"].run({"page": "Hạn Eco"})
    assert "Hạn nộp hồ sơ là thứ tư." in out
    assert "note:2026-09-20" in out
    assert "Dời sang thứ sáu?" in out


async def test_a_page_is_reached_by_its_written_name_not_only_its_slug(tmp_path, tools):
    a_page(tmp_path)
    for asked in ["Hạn Eco", "hạn eco", "han-eco"]:
        assert "Hạn nộp hồ sơ" in await tools["wiki_get"].run({"page": asked})


async def test_asking_for_a_page_that_is_not_there_says_so(tmp_path, tools):
    with pytest.raises(ToolError):
        await tools["wiki_get"].run({"page": "không có"})


async def test_search_finds_a_page_by_its_title(tmp_path, tools):
    # The word someone types is usually the name of the thing, not a phrase inside it.
    a_page(tmp_path)
    assert "han-eco" in await tools["wiki_search"].run({"query": "eco"})


async def test_search_with_nothing_to_find_says_so(tmp_path, tools):
    a_page(tmp_path)
    assert await tools["wiki_search"].run({"query": "xe máy"}) != ""


async def test_a_page_without_sources_is_refused(tmp_path, tools):
    """The one rule that makes the rest of the vault worth believing."""
    with pytest.raises(ToolError):
        await tools["wiki_apply"].run({"page": "X", "body": "thân", "sources": []})


async def test_writing_a_page_keeps_the_machine_written_links(tmp_path, tools):
    """A model rewriting a page must not be able to destroy the link graph."""
    block = wiki_links.render_related(["so-sach"], ["khac"])
    a_page(tmp_path, body=wiki_links.set_managed("Bản cũ.", block))

    await tools["wiki_apply"].run(
        {"page": "Hạn Eco", "body": "Bản mới.", "sources": ["note:2026-09-22"]}
    )
    page = wiki_store.find_page(tmp_path, "han-eco")
    assert wiki_links.authored_body(page.body) == "Bản mới."
    assert "so-sach" in page.body and "khac" in page.body
    assert page.sources == ["note:2026-09-22"]


async def test_rewriting_a_page_leaves_it_in_the_folder_it_already_lives_in(tmp_path, tools):
    """Moving it would break every link that resolved to the old place."""
    a_page(tmp_path, kind="syntheses")
    await tools["wiki_apply"].run(
        {"page": "Hạn Eco", "kind": "concepts", "body": "x", "sources": ["note:2026-09-22"]}
    )
    assert wiki_store.find_page(tmp_path, "han-eco").kind == "syntheses"


async def test_a_new_page_lands_in_the_folder_it_asked_for(tmp_path, tools):
    await tools["wiki_apply"].run(
        {"page": "Ý tưởng", "kind": "concepts", "body": "x", "sources": ["note:2026-09-22"]}
    )
    assert wiki_store.find_page(tmp_path, "y-tuong").kind == "concepts"


async def test_a_kind_the_vault_does_not_know_is_refused(tmp_path, tools):
    with pytest.raises(ToolError):
        await tools["wiki_apply"].run(
            {"page": "X", "kind": "ghi-chu", "body": "x", "sources": ["note:2026-09-22"]}
        )


async def test_one_source_written_as_a_string_is_accepted(tmp_path, tools):
    # Models write `sources: "note:..."` as readily as they write a list.
    await tools["wiki_apply"].run({"page": "X", "body": "x", "sources": "note:2026-09-22"})
    assert wiki_store.find_page(tmp_path, "x").sources == ["note:2026-09-22"]


def test_memory_search_reaches_wiki_pages_and_labels_them(tmp_path):
    """Without this the vault is invisible to the tool the agent actually reaches for."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    a_page(memory_dir)
    hits = search_memory(memory_dir, memory_dir.parent / "MEMORY.md", "hồ sơ")
    assert any(source.startswith("wiki:han-eco") for source, _ in hits)


def test_a_wiki_hit_does_not_carry_the_generated_link_block(tmp_path):
    """Otherwise every page matches every linked page's name, and search goes to noise."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    a_page(
        memory_dir,
        body=wiki_links.set_managed("Thân bài.", wiki_links.render_related(["xe-may"], [])),
    )
    hits = search_memory(memory_dir, memory_dir.parent / "MEMORY.md", "xe may")
    assert not any(source.startswith("wiki:") for source, _ in hits)
