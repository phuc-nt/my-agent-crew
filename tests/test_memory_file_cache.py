"""Wiki pages are parsed once per change on disk, not once per system prompt."""

import os
from pathlib import Path

from my_agent_crew.memory import file_cache, wiki_store
from my_agent_crew.memory.wiki_store import Page


def _page(title: str) -> Page:
    return Page(slug="han-eco", kind="entities", title=title, body="x", sources=["note:a"])


def test_an_unchanged_page_is_not_parsed_again(tmp_path: Path, monkeypatch):
    memory_dir = tmp_path / "memory"
    wiki_store.write_page(memory_dir, _page("Hạn Eco"))
    parsed: list[Path] = []
    real_parse = wiki_store.parse_page
    monkeypatch.setattr(
        wiki_store, "parse_page", lambda p, kind: parsed.append(p) or real_parse(p, kind)
    )
    assert [p.title for p in wiki_store.list_pages(memory_dir)] == ["Hạn Eco"]
    assert [p.title for p in wiki_store.list_pages(memory_dir)] == ["Hạn Eco"]
    assert len(parsed) == 1


def test_an_edited_page_is_parsed_again_on_the_next_call(tmp_path: Path):
    memory_dir = tmp_path / "memory"
    written = wiki_store.write_page(memory_dir, _page("Hạn Eco"))
    assert [p.title for p in wiki_store.list_pages(memory_dir)] == ["Hạn Eco"]
    wiki_store.write_page(memory_dir, _page("Hạn Eco Việt Nam"))
    path = wiki_store.wiki_dir(memory_dir) / written.kind / f"{written.slug}.md"
    later = path.stat().st_mtime + 2  # the two writes may share a clock tick
    os.utime(path, (later, later))
    assert [p.title for p in wiki_store.list_pages(memory_dir)] == ["Hạn Eco Việt Nam"]


def test_a_same_sized_edit_with_a_new_mtime_is_seen(tmp_path: Path):
    path = tmp_path / "f.txt"
    path.write_text("aaaa")
    assert file_cache.cached(path, Path.read_text) == "aaaa"
    path.write_text("bbbb")
    later = path.stat().st_mtime + 2
    os.utime(path, (later, later))
    assert file_cache.cached(path, Path.read_text) == "bbbb"
    file_cache.forget(path)
    calls: list[Path] = []
    assert file_cache.cached(path, lambda p: calls.append(p) or p.read_text()) == "bbbb"
    assert calls == [path]
