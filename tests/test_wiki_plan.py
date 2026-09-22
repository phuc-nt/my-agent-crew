"""Reading a compile's model output into page writes."""

import json

import pytest

from my_agent_crew.memory.wiki_plan import MIN_BODY_CHARS, plan_pages, planned_from_dicts

LONG = "Hạn nộp hồ sơ là thứ tư, đã dời một lần từ thứ hai tuần trước."


def one(**kwargs) -> str:
    item = {"title": "Hạn Eco", "body": LONG, "sources": ["note:2026-09-20"], **kwargs}
    return json.dumps([item], ensure_ascii=False)


def test_a_plain_list_is_read():
    [page] = plan_pages(one())
    assert page.slug == "han-eco"
    assert page.sources == ["note:2026-09-20"]


def test_a_fenced_block_is_read():
    # Models fence JSON by habit even when told not to.
    assert plan_pages(f"Đây là kết quả:\n```json\n{one()}\n```\n") != []


def test_an_object_wrapping_the_list_is_read():
    text = json.dumps({"pages": json.loads(one())}, ensure_ascii=False)
    assert len(plan_pages(text)) == 1


def test_one_broken_page_does_not_cost_the_others():
    """The failure this prevents: a whole night's compile lost to one stray comma."""
    good = json.dumps(
        {"title": "Hạn Eco", "body": LONG, "sources": ["note:2026-09-20"]}, ensure_ascii=False
    )
    planned = plan_pages(f'[{{"title": "Hỏng", "body": }}, {good}]')
    assert [p.slug for p in planned] == ["han-eco"]


def test_a_page_with_no_sources_is_dropped():
    """It cannot be repaired here without inventing a source, and an invented source is
    the one thing the vault must not hold."""
    assert plan_pages(one(sources=[])) == []


def test_a_stub_body_is_dropped():
    assert plan_pages(one(body="ngắn")) == []
    assert plan_pages(one(body="x" * MIN_BODY_CHARS)) != []


def test_a_page_with_no_title_is_dropped():
    assert plan_pages(one(title="")) == []


def test_two_pages_that_slug_the_same_keep_only_the_first():
    # Otherwise the second silently overwrites the first inside one compile.
    text = json.dumps(
        [
            {"title": "Hạn Eco", "body": LONG, "sources": ["note:a"]},
            {"title": "hạn eco", "body": LONG, "sources": ["note:b"]},
        ],
        ensure_ascii=False,
    )
    [page] = plan_pages(text)
    assert page.sources == ["note:a"]


@pytest.mark.parametrize("kind,expected", [("concepts", "concepts"), ("ghi-chu", "entities")])
def test_an_unknown_folder_falls_back_rather_than_failing(kind, expected):
    [page] = plan_pages(one(kind=kind))
    assert page.kind == expected


def test_an_unknown_status_is_not_believed():
    [page] = plan_pages(one(status="tuyệt-đối-đúng"))
    assert page.status == "ok"


def test_review_status_survives():
    """A compile unsure of a page must be able to say so, or the flag is useless."""
    [page] = plan_pages(one(status="review"))
    assert page.status == "review"


def test_nothing_usable_gives_nothing():
    for text in ["", "xin lỗi, tôi không biết", "[]", "{}", "null"]:
        assert plan_pages(text) == []


def test_a_plan_survives_a_round_trip_through_a_proposal():
    """A proposal is stored as JSON and read back at approval time, possibly days later."""
    planned = plan_pages(one(questions=["Dời sang thứ sáu?"]))
    back = planned_from_dicts([p.to_dict() for p in planned])
    assert back == planned
