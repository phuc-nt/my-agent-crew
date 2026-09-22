"""What the lint reports, and the two dashboards it writes."""

from datetime import date

from my_agent_crew.memory import wiki_lint, wiki_store
from my_agent_crew.memory.wiki_reports import (
    OPEN_QUESTIONS_NAME,
    STALE_NAME,
    reports_dir,
    write_reports,
)
from my_agent_crew.memory.wiki_store import Page

TODAY = date(2026, 9, 23)


def page(slug="han-eco", **kwargs) -> Page:
    fields = {
        "slug": slug,
        "kind": "entities",
        "title": "Hạn Eco",
        "body": "thân",
        "sources": ["note:2026-09-20"],
        "updated": "2026-09-20",
        **kwargs,
    }
    return Page(**fields)


def test_a_page_with_no_sources_is_reported():
    """It still reads as knowledge while having stopped being traceable."""
    [problem] = wiki_lint.unsourced([page(sources=[])])
    assert problem.slug == "han-eco" and problem.kind == "unsourced"


def test_a_sourced_page_is_not_reported():
    assert wiki_lint.unsourced([page()]) == []


def test_a_link_to_a_page_nobody_wrote_is_reported():
    [problem] = wiki_lint.dangling([page(body="Xem [[Sổ sách]].")])
    assert problem.detail == "so-sach"


def test_a_link_to_a_page_that_exists_is_not_reported():
    pages = [page(body="Xem [[Sổ sách]]."), page(slug="so-sach", title="Sổ sách")]
    assert wiki_lint.dangling(pages) == []


def test_a_link_inside_the_generated_block_is_not_a_dangling_link():
    """The block is regenerated from real pages, so a link in it can never dangle; counting
    it would report a problem the machine invented."""
    body = "thân\n\n<!-- wiki:related -->\n[[khong-co]]\n<!-- /wiki:related -->"
    assert wiki_lint.dangling([page(body=body)]) == []


def test_an_old_page_is_reported_as_stale():
    [problem] = wiki_lint.stale([page(updated="2026-01-01")], TODAY)
    assert problem.kind == "stale"


def test_a_recent_page_is_not_stale():
    assert wiki_lint.stale([page(updated="2026-09-20")], TODAY) == []


def test_a_page_with_no_date_counts_as_stale():
    """Treating absence of evidence as freshness is how a vault starts lying."""
    [problem] = wiki_lint.stale([page(updated="")], TODAY)
    assert "không có ngày" in problem.detail


def test_a_page_flagged_for_review_is_reported():
    [problem] = wiki_lint.needs_review([page(status="review")])
    assert problem.kind == "review"


def test_open_questions_carry_the_page_they_came_from():
    items = wiki_lint.open_questions([page(questions=["Dời sang thứ sáu?"])])
    assert items == [("han-eco", "Dời sang thứ sáu?")]


def test_both_dashboards_are_written_even_when_the_vault_is_clean(tmp_path):
    """A missing file reads as 'the check never ran', which is a different answer."""
    wiki_store.write_page(tmp_path, page(), today=TODAY)
    write_reports(tmp_path, TODAY)
    for name in (OPEN_QUESTIONS_NAME, STALE_NAME):
        assert (reports_dir(tmp_path) / name).is_file()


def test_the_dashboards_report_what_the_vault_actually_holds(tmp_path):
    wiki_store.write_page(
        tmp_path, page(questions=["Dời sang thứ sáu?"], body="Xem [[Sổ sách]]."), today=TODAY
    )
    write_reports(tmp_path, TODAY)
    questions = (reports_dir(tmp_path) / OPEN_QUESTIONS_NAME).read_text(encoding="utf-8")
    problems = (reports_dir(tmp_path) / STALE_NAME).read_text(encoding="utf-8")
    assert "Dời sang thứ sáu?" in questions
    assert "so-sach" in problems


def test_a_dashboard_is_replaced_not_appended(tmp_path):
    """Otherwise it keeps reporting problems that were fixed months ago."""
    wiki_store.write_page(tmp_path, page(questions=["Cũ?"]), today=TODAY)
    write_reports(tmp_path, TODAY)
    wiki_store.write_page(tmp_path, page(questions=[]), today=TODAY)
    write_reports(tmp_path, TODAY)
    assert "Cũ?" not in (reports_dir(tmp_path) / OPEN_QUESTIONS_NAME).read_text(encoding="utf-8")


def test_the_reports_folder_is_not_mistaken_for_pages(tmp_path):
    """It lives inside the vault, so a careless scan would read its files as pages."""
    wiki_store.write_page(tmp_path, page(), today=TODAY)
    write_reports(tmp_path, TODAY)
    assert [p.slug for p in wiki_store.list_pages(tmp_path)] == ["han-eco"]
