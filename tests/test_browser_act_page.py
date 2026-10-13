"""What an action checks of the page before it does anything: the element has to be the one
the model was shown still. No browser here: a page is a stand-in that draws what the test
says, so the cases a real browser would not produce on demand are covered too."""

from __future__ import annotations

import pytest

from my_agent_crew import texts_browser as t
from my_agent_crew.browser import act as a
from my_agent_crew.browser import kit as k
from my_agent_crew.browser.act_page import current
from my_agent_crew.browser.snapshot import Node, Shown, read
from my_agent_crew.browser.tabs import Tab
from my_agent_crew.config_browser import BrowserSettings
from my_agent_crew.tools.registry import ToolError

A, B = "http://shop.test/a", "http://shop.test/b"
SHOWN = '- button "Tìm" [ref=e2]\n- listitem [ref=e3]:\n  - text: Áo sơ mi'


class Found:
    def __init__(self, count: int):
        self._count = count

    async def count(self) -> int:
        return self._count


class Page:
    """A page that draws as scripted: each drawing leaves it at an address and gives an
    outline. With one step left, every later drawing repeats it."""

    def __init__(self, *steps, found: int = 1):
        self.url, self.steps, self.found, self.asked = A, list(steps), found, []

    async def aria_snapshot(self, mode: str) -> str:
        assert mode == "ai"  # any other mode forgets the refs the model was given
        self.url, outline = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        return outline

    async def wait_for_load_state(self, state: str, timeout: int) -> None:
        return None

    def locator(self, selector: str) -> Found:
        self.asked.append(selector)
        return Found(self.found)


@pytest.fixture
def kit(tmp_path, monkeypatch):
    monkeypatch.setattr(k, "SETTLE_SECONDS", 0)
    return k.Kit(None, "coach", BrowserSettings(enabled=True, mode="act"), tmp_path, 20_000)


def tab_on(kit, page: Page, shown: str = SHOWN, url: str = A) -> Tab:
    return Tab(1, "t1", "c1", page, 0.0, shown=Shown(url, read(shown, kit.ask).nodes))


def click(ref: str = "e2", name: str = "Tìm") -> a.Asked:
    return a.Asked("click", ref, name)


async def refusal(kit, tab: Tab, asked: a.Asked) -> str:
    with pytest.raises(ToolError) as error:
        await current(kit, tab, asked)
    return str(error.value)


async def test_an_element_still_as_shown_is_found_by_its_ref_and_nothing_else(kit):
    page = Page((A, '- heading "Mới" [ref=e9]\n' + SHOWN))
    tab = tab_on(kit, page)

    target, node = await current(kit, tab, click(name="  tìm "))

    assert isinstance(target, Found) and page.asked == ["aria-ref=e2"]
    assert node == Node("e2", "button", "Tìm")
    assert "e9" not in tab.shown.nodes  # looking before an action shows the model nothing


async def test_a_ref_the_model_was_never_given_reaches_no_page(kit):
    page = Page((A, SHOWN + '\n- button "Lạ" [ref=e7]'))
    tab = tab_on(kit, page)

    assert await refusal(kit, tab, click("e7", "Lạ")) == t.REF_UNKNOWN.format(ref="e7")
    made_up = 'e2"], body >> [x="' + "y" * 60
    assert await refusal(kit, tab, click(made_up)) == t.REF_UNKNOWN.format(ref=made_up[:40])
    tab.shown = None
    assert await refusal(kit, tab, click()) == t.NO_SNAPSHOT
    assert page.asked == [] and page.steps == [(A, SHOWN + '\n- button "Lạ" [ref=e7]')]


async def test_a_page_at_another_address_than_the_one_shown_is_not_acted_on(kit):
    elsewhere = tab_on(kit, Page((B, SHOWN)))
    elsewhere.page.url = B
    # Drawn three times and moved each time: the last drawing began where the model looked
    # and ended somewhere else.
    moving = tab_on(kit, Page((B, SHOWN), (A, SHOWN), (B, SHOWN), (B, SHOWN)))
    # Or began somewhere else and ended where the model looked: the outline may be of either.
    back = tab_on(kit, Page((A, SHOWN), (B, SHOWN), (A, SHOWN), (A, SHOWN)))
    back.page.url = B
    within = tab_on(kit, Page((A + "#muc-2", SHOWN)))

    for tab in (elsewhere, moving, back):
        assert await refusal(kit, tab, click()) == t.PAGE_MOVED
        assert tab.page.asked == []
    assert (moving.page.url, back.page.url) == (B, A)
    _target, node = await current(kit, within, click())  # a move within the page is none
    assert node.ref == "e2"


async def test_an_element_that_is_gone_or_became_another_kind_is_not_acted_on(kit):
    gone = tab_on(kit, Page((A, "- listitem [ref=e3]")))
    link = tab_on(kit, Page((A, '- link "Tìm" [ref=e2]')))
    nowhere = tab_on(kit, Page((A, SHOWN), found=0))
    twice = tab_on(kit, Page((A, SHOWN), found=2))

    for tab in (gone, link, nowhere, twice):
        assert await refusal(kit, tab, click()) == t.REF_GONE.format(ref="e2")
    assert gone.page.asked == link.page.asked == []


async def test_the_name_given_has_to_be_the_one_the_element_carries_now(kit):
    renamed = tab_on(kit, Page((A, '- button "Xoá" [ref=e2]')))
    same = tab_on(kit, Page((A, SHOWN)))
    long = "Tìm\n" + "x" * 100

    assert await refusal(kit, renamed, click()) == t.NAME_MISMATCH.format(ref="e2", name="Tìm")
    assert await refusal(kit, same, click(name="Tìm kiếm")) == (
        t.NAME_MISMATCH.format(ref="e2", name="Tìm kiếm")
    )
    assert await refusal(kit, same, click(name="")) == t.NAME_MISMATCH.format(ref="e2", name="")
    assert await refusal(kit, same, click(name=long)) == (
        t.NAME_MISMATCH.format(ref="e2", name="Tìm " + "x" * 76)
    )
    assert renamed.page.asked == same.page.asked == []
    _target, node = await current(kit, same, click("e3", ""))  # an element that has none
    assert node == Node("e3", "listitem", "")


@pytest.mark.parametrize(
    ("was", "now"),
    [
        ("Áo sơ mi", "Xoá"),  # a word came since the model looked
        ("Xoá", "Áo sơ mi"),  # or went: the person was asked about another thing
        ("Xoá", "Mua ngay"),
    ],
)
async def test_an_element_whose_words_for_a_person_changed_is_not_acted_on(kit, was, now):
    drawn = "- listitem [ref=e3]:\n  - text: {}"
    tab = tab_on(kit, Page((A, drawn.format(now))), drawn.format(was))

    assert await refusal(kit, tab, click("e3", "")) == t.STALE_ASK.format(ref="e3")
    assert tab.page.asked == []
    # A kind that sets nothing off stops for no word, so a word that came is no change to it.
    _target, node = await current(kit, tab, a.Asked("hover", "e3", ""))
    assert node.ref == "e3"


async def test_a_word_the_person_was_already_asked_about_is_no_change(kit):
    """The gate asked for the word in the name the model gave, or in what it chooses,
    whatever the page drew at the element then or draws now."""
    named = tab_on(kit, Page((A, '- button "Xoá" [ref=e2]')))
    colours = '- combobox "Màu" [ref=e4]'
    choice = tab_on(kit, Page((A, colours + ':\n  - option "Xoá hết"')), colours)

    _target, button = await current(kit, named, click(name="Xoá"))
    _target, box = await current(kit, choice, a.Asked("select", "e4", "Màu", value="Xoá màu"))

    assert (button.name, box.name) == ("Xoá", "Màu")
    assert await refusal(kit, choice, a.Asked("select", "e4", "Màu", value="Xanh")) == (
        t.STALE_ASK.format(ref="e4")
    )
