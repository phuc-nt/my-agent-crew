"""The wiki vault on disk: slugs, frontmatter round-trip, and what a broken file does."""

from datetime import date

import pytest

from my_agent_crew.memory.wiki_store import (
    Page,
    check_slug,
    find_page,
    list_pages,
    parse_page,
    read_page,
    render_page,
    slugify,
    wiki_dir,
    write_page,
)


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Hạn Eco", "han-eco"),
        ("hạn eco", "han-eco"),  # the same page, not a fork
        ("Đọc sách", "doc-sach"),  # `đ` is a letter, not a `d` with a mark
        ("  Sổ   sách  ", "so-sach"),
        ("Jimny 5 cửa", "jimny-5-cua"),
        ("!!!", "khong-ten"),
        # A title with no Latin letters still has a name. Dropping it would file every
        # such page under the same fallback slug, which is not a bad name but a merge:
        # two Japanese-titled books would become one page.
        ("ミトンとふびん", "ミトンとふびん"),
        ("東京 tower", "東京-tower"),
    ],
)
def test_a_title_becomes_a_stable_file_name(title: str, expected: str):
    assert slugify(title) == expected


def test_two_titles_that_share_no_latin_letters_are_two_pages():
    """The fallback slug is for a title that is only punctuation, not for every script
    that is not Latin. Sharing it would silently fork nothing and merge everything."""
    assert slugify("ミトンとふびん") != slugify("東京物語")


@pytest.mark.parametrize(
    "slug",
    ["../../etc/passwd", "a/b", ".", "..", "", "-leading", "han eco", "han.eco"],
)
def test_a_slug_that_could_climb_out_of_the_vault_is_refused(slug: str):
    """A slug becomes a path. Anything with a separator, a dot segment or a space is not
    a page name, whatever wrote it."""
    with pytest.raises(ValueError):
        check_slug(slug)


@pytest.mark.parametrize("slug", ["HOA", "Han-Eco", "hanEco"])
def test_an_uppercase_slug_is_refused_because_the_slugger_never_makes_one(slug: str):
    """`slugify` lowercases, so an uppercase slug did not come from a title. Accepting one
    would put `HOA.md` beside `hoa.md`: two pages about the same thing, or on a
    case-insensitive filesystem one file that both of them believe they own."""
    with pytest.raises(ValueError):
        check_slug(slug)


@pytest.mark.parametrize("slug", ["han-eco", "jimny-5-cua", "ミトンとふびん", "東京-tower"])
def test_a_slug_in_any_script_is_a_name_the_vault_accepts(slug: str):
    """The guard is against paths, not against alphabets: a page whose title has no Latin
    letters still has to be writable, or slugging it correctly would gain nothing."""
    assert check_slug(slug) == slug


def test_every_slug_the_slugger_makes_is_one_the_vault_accepts():
    """These two run back to back on every write. A title that slugs into something the
    guard rejects is a page that can never be saved."""
    for title in ["Hạn Eco", "ミトンとふびん", "東京 tower", "!!!", "Jimny 5 cửa"]:
        assert check_slug(slugify(title))


def test_a_page_survives_being_written_and_read_back(tmp_path):
    page = Page(
        slug="han-eco",
        kind="entities",
        title="Hạn Eco",
        body="Hạn nộp hồ sơ, xem [[so-sach]].",
        sources=["note:2026-09-20", "conv:c1"],
        questions=["Dời sang thứ sáu?"],
        status="review",
        updated="2026-09-21",
    )
    write_page(tmp_path, page)
    back = read_page(tmp_path, "entities", "han-eco")
    assert back == page


def test_writing_without_a_date_stamps_today(tmp_path):
    written = write_page(
        tmp_path,
        Page(slug="p", kind="concepts", title="P", body="x"),
        today=date(2026, 9, 23),
    )
    assert written.updated == "2026-09-23"
    assert read_page(tmp_path, "concepts", "p").updated == "2026-09-23"


def test_a_file_that_is_not_a_page_is_skipped_rather_than_raising(tmp_path):
    """One hand-dropped file in the folder must not take the whole vault down with it."""
    directory = wiki_dir(tmp_path) / "entities"
    directory.mkdir(parents=True)
    (directory / "rac.md").write_text("chỉ là ghi chú, không frontmatter", encoding="utf-8")
    (directory / "hong.md").write_text("---\n: : :\n---\n\nthân\n", encoding="utf-8")
    write_page(tmp_path, Page(slug="that", kind="entities", title="Thật", body="x"))

    assert [p.slug for p in list_pages(tmp_path)] == ["that"]
    assert parse_page(directory / "rac.md", "entities") is None


def test_a_status_the_vault_does_not_know_is_read_as_needing_review(tmp_path):
    """Believing an unknown status would let a page assert itself by misspelling."""
    directory = wiki_dir(tmp_path) / "concepts"
    directory.mkdir(parents=True)
    (directory / "x.md").write_text(
        "---\ntitle: X\nstatus: tuyệt-đối-đúng\n---\n\nthân\n", encoding="utf-8"
    )
    assert read_page(tmp_path, "concepts", "x").status == "review"


def test_one_source_written_as_a_string_is_still_a_source(tmp_path):
    """A model writes `sources: note:2026-09-20` as often as it writes a list."""
    directory = wiki_dir(tmp_path) / "entities"
    directory.mkdir(parents=True)
    (directory / "x.md").write_text(
        "---\ntitle: X\nsources: note:2026-09-20\n---\n\nthân\n", encoding="utf-8"
    )
    assert read_page(tmp_path, "entities", "x").sources == ["note:2026-09-20"]


def test_a_page_is_found_without_knowing_which_folder_holds_it(tmp_path):
    # A wikilink carries a name and never a folder, so this is the only lookup a link has.
    write_page(tmp_path, Page(slug="y", kind="syntheses", title="Y", body="x"))
    assert find_page(tmp_path, "y").kind == "syntheses"
    assert find_page(tmp_path, "khong-co") is None


@pytest.mark.parametrize("slug", ["../thoat", "co khoang trang", "", "-dau-gach", "HOA"])
def test_a_slug_that_could_leave_the_vault_is_refused(tmp_path, slug: str):
    with pytest.raises(ValueError):
        write_page(tmp_path, Page(slug=slug, kind="entities", title="X", body="x"))


def test_an_unknown_kind_is_refused(tmp_path):
    with pytest.raises(ValueError):
        write_page(tmp_path, Page(slug="x", kind="ghi-chu", title="X", body="x"))


def test_the_rendered_file_keeps_accents_readable():
    """A vault is read by people in an editor; escaped bytes would make it unreadable."""
    text = render_page(Page(slug="x", kind="entities", title="Hạn Eco", body="thân"))
    assert "title: Hạn Eco" in text
