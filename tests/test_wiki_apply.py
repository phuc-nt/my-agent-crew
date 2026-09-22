"""Writing a plan into the vault and rebuilding the link graph across it."""

from my_agent_crew.memory import wiki_links, wiki_store
from my_agent_crew.memory.wiki_apply import capture_previous, rebuild_links, write_planned
from my_agent_crew.memory.wiki_plan import Planned
from my_agent_crew.memory.wiki_store import Page

LONG = "Hạn nộp hồ sơ là thứ tư, đã dời một lần."


def planned(slug="han-eco", title="Hạn Eco", body=LONG, kind="entities", **kwargs) -> Planned:
    return Planned(
        slug=slug, kind=kind, title=title, body=body, sources=["note:2026-09-20"], **kwargs
    )


def test_a_plan_becomes_pages_on_disk(tmp_path):
    write_planned(tmp_path, [planned()])
    page = wiki_store.find_page(tmp_path, "han-eco")
    assert page.title == "Hạn Eco" and page.sources == ["note:2026-09-20"]


def test_a_rewrite_leaves_the_page_where_it_lives(tmp_path):
    wiki_store.write_page(
        tmp_path, Page(slug="han-eco", kind="syntheses", title="Hạn Eco", body="cũ", sources=["x"])
    )
    write_planned(tmp_path, [planned(kind="concepts")])
    assert wiki_store.find_page(tmp_path, "han-eco").kind == "syntheses"


def test_what_a_page_said_before_is_captured_for_the_undo(tmp_path):
    wiki_store.write_page(
        tmp_path,
        Page(slug="han-eco", kind="entities", title="Hạn Eco", body="bản cũ", sources=["x"]),
    )
    [before] = capture_previous(tmp_path, [planned()])
    assert before["body"] == "bản cũ"


def test_a_page_that_does_not_exist_yet_has_no_previous(tmp_path):
    """Recording an empty page instead would make an undo write blanks over nothing."""
    assert capture_previous(tmp_path, [planned()]) == []


def test_a_link_becomes_a_backlink_on_the_other_page(tmp_path):
    write_planned(
        tmp_path,
        [planned(), planned(slug="so-sach", title="Sổ sách", body=f"Xem [[Hạn Eco]]. {LONG}")],
    )
    rebuild_links(tmp_path)
    assert "so-sach" in wiki_store.find_page(tmp_path, "han-eco").body
    assert "han-eco" in wiki_store.find_page(tmp_path, "so-sach").body


def test_a_link_to_a_page_nobody_wrote_is_not_an_edge(tmp_path):
    """It is a note to self in the author's text, not a connection in the graph."""
    write_planned(tmp_path, [planned(body=f"Xem [[Chưa Có]]. {LONG}")])
    rebuild_links(tmp_path)
    body = wiki_store.find_page(tmp_path, "han-eco").body
    assert "chua-co" not in wiki_links.split_managed(body)[1]


def test_the_authors_words_survive_a_rebuild(tmp_path):
    """Exactly, not approximately: a rebuild that folds its own block into the author's
    text grows the page a little every night until the words are buried."""
    written = f"[[Hạn Eco]] {LONG}"
    write_planned(tmp_path, [planned(), planned(slug="so-sach", title="Sổ sách", body=written)])
    rebuild_links(tmp_path)
    rebuild_links(tmp_path)
    page = wiki_store.find_page(tmp_path, "so-sach")
    assert wiki_links.authored_body(page.body) == written
    assert page.body.count(wiki_links.OPEN) == 1


def test_a_rebuild_that_changes_nothing_rewrites_nothing(tmp_path):
    """A compile that found nothing new must leave the vault genuinely untouched."""
    write_planned(
        tmp_path, [planned(), planned(slug="so-sach", title="Sổ sách", body=f"[[Hạn Eco]] {LONG}")]
    )
    assert rebuild_links(tmp_path) == 2
    assert rebuild_links(tmp_path) == 0


def test_redrawing_links_does_not_redate_the_page(tmp_path):
    """Otherwise every page looks revised today and nobody can see what actually changed."""
    wiki_store.write_page(
        tmp_path,
        Page(
            slug="han-eco",
            kind="entities",
            title="Hạn Eco",
            body="[[So Sach]]",
            sources=["x"],
            updated="2026-01-01",
        ),
    )
    wiki_store.write_page(
        tmp_path, Page(slug="so-sach", kind="entities", title="Sổ sách", body="x", sources=["y"])
    )
    rebuild_links(tmp_path)
    assert wiki_store.find_page(tmp_path, "han-eco").updated == "2026-01-01"


def test_a_page_does_not_link_to_itself(tmp_path):
    write_planned(tmp_path, [planned(body=f"Xem [[Hạn Eco]]. {LONG}")])
    rebuild_links(tmp_path)
    managed = wiki_links.split_managed(wiki_store.find_page(tmp_path, "han-eco").body)[1]
    assert "Được nhắc tới" not in managed
