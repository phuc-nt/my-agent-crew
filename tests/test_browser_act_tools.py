"""The one browser tool that does something to a page, against a real Chromium: what each
kind does, what it refuses to do, when a person is asked first, and that an action is only
ever made on the element and the tab the model was shown."""

from __future__ import annotations

import asyncio
import re

import pytest
import pytest_asyncio
from playwright.async_api import Error as BrowserError

from my_agent_crew import texts_browser as t
from my_agent_crew.browser import act_page, tools_act
from my_agent_crew.browser import kit as k
from my_agent_crew.browser.navigate import build_navigate
from my_agent_crew.browser.tools_act import build_act
from my_agent_crew.browser.tools_read import build_snapshot
from my_agent_crew.texts import WORKSPACE_ESCAPE
from my_agent_crew.tools.registry import ToolError
from tests.browser_tools import parts, ref_of, talking, world

pytestmark = pytest.mark.asyncio(loop_scope="module")

LOG = (
    "<p id=log></p>"
    "<script>function log(x) { document.getElementById('log').textContent += x + ';' }</script>"
)
KEYS = (
    "if (event.key.length > 1 && event.key != 'Shift') "
    "log((event.shiftKey ? 'Shift+' : '') + event.key)"
)
DOT = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
SHOP = (
    "<title>Cửa hàng</title>"
    "<button onclick=\"log('tìm')\">Tìm</button>"
    "<button onmouseover=\"log('rê')\" onclick=\"log('bấm rê')\">Rê chuột</button>"
    f'<input aria-label="Ghi chú" id=note value="cũ" onkeydown="{KEYS}">'
    '<input aria-label="Tên" id=ten>'
    '<textarea aria-label="Lời nhắn" id=msg></textarea>'
    '<div contenteditable role=textbox aria-label="Soạn thảo" id=soan></div>'
    # One option's value is what another is called: a choice is made by what the model saw.
    "<label>Màu <select id=mau onchange=\"log('màu ' + this.value)\">"
    "<option value=do>Đỏ</option><option value=Xanh>Hồng</option>"
    "<option value=xanh>Xanh</option></select></label>"
    "<ul><li onclick=\"log('món')\">Áo sơ mi "
    "<button onclick=\"event.stopPropagation(); log('thêm')\">Thêm</button></li></ul>"
    "<p id=chu>Chú thích</p>"
    "<button disabled onclick=\"log('khoá')\">Khoá</button>"
    "<button onclick=\"alert('Hết hàng')\">Báo</button>"
    "<button onclick=\"log('đặt')\">Đặt hàng</button>"
    '<a href="/khac" target="_blank">Mở cửa sổ</a>'
    '<div style="height: 3000px"></div>'
    "<button onclick=\"log('xa')\" onmouseover=\"log('rê xa')\">Ở xa</button>" + LOG
)
LOGIN = (
    "<title>Đăng nhập</title>"
    '<input aria-label="Email" id=email>'
    '<input type=password aria-label="Khoá" id=pw>'
    '<input aria-label="Mã OTP" id=otp>'
    '<input autocomplete="one-time-code" aria-label="Mã từ tin nhắn" id=code>'
    '<input autocomplete="section-a cc-number" aria-label="Dãy số mặt trước" id=cc>'
    "<label>Bí mật <input type=password id=pw2></label>"
    "<p id=chu>Chú thích</p>"
    '<iframe src="/khung" title="Khung"></iframe>'
)
FRAME = (
    '<input type=password aria-label="Mật mã" id=fp>'
    '<input aria-label="Lời nhắn trong khung" id=fi>'
    "<button onclick=\"this.textContent = 'Đã bấm'\">Trong khung</button>"
)
FORMS = (
    "<title>Các form</title>"
    '<form action="/tim"><input name=q aria-label="Từ khoá"><button>Tìm kiếm</button></form>'
    '<form action="/dat" method=post><input name=a aria-label="Địa chỉ">'
    "<button>Đặt hàng</button></form>"
    '<form action="/loi" method=post><input name=b aria-label="Lời chúc">'
    '<input type=submit value="Gửi"></form>'
    '<form action="/tra" method=post><input name=c aria-label="Số lượng">'
    '<input type=image alt="Thanh toán" src="/x.png"></form>'
    '<form action="/bo" method=post><input name=d aria-label="Lý do">'
    '<button type=submit aria-label="Xoá">x</button></form>'
    '<form action="/hai" method=post><input name=e aria-label="Mã giảm giá">'
    '<button>Áp dụng</button><button title="Xác nhận">OK</button></form>'
    '<form action="/luu" method=post><input name=f aria-label="Ghi thêm">'
    "<button type=button>Xoá</button><button>Lưu</button></form>"
    # Controls that say what they do some other way than in their own words.
    '<form action="/k1" method=post><input name=g aria-label="Ô một"><input type=submit></form>'
    '<form action="/k2" method=post><input name=h aria-label="Ô hai">'
    f'<button type=submit><img alt="Gửi" src="{DOT}" width=20 height=20></button></form>'
    '<form action="/k3" method=post><input name=i aria-label="Ô ba">'
    f'<input type=image src="{DOT}" width=20 height=20></form>'
    '<form action="/k4" method=post><input name=j aria-label="Ô bốn">'
    '<button type="">Thanh toán</button></form>'
    '<form action="/k5" method=post><input name=k aria-label="Ô năm">'
    '<button type="sumbit">Xác nhận</button></form>'
    '<form action="/k6" method=post><input name=l aria-label="Ô sáu"><button type=submit>'
    '<span role=img aria-label="Xoá" style="display: inline-block; width: 20px; height: 20px">'
    "</span></button></form>"
    '<span id=nhan hidden>Đặt hàng</span><form action="/k7" method=post>'
    '<input name=m aria-label="Ô bảy"><button type=submit aria-labelledby=nhan>→</button></form>'
    '<form action="/k8" method=post><input name=n aria-label="Ô tám">'
    "<button hidden>Xoá</button></form>"
    # A form and what belongs to it, apart on the page.
    '<form id=\'ở "xa"\' action="/k9" method=post><input name=o aria-label="Ô chín"></form>'
    "<button form='ở \"xa\"'>Mua ngay</button>"
    '<input name=p aria-label="Ô mười" form=kia><form id=kia action="/k10" method=post>'
    "<button>Chuyển tiền</button></form>"
    '<form action="/ghi" method=post><input name=r aria-label="Ghi lại">'
    "<button form=kia>Xoá</button><button type=reset>Xoá hết</button><button>Ghi</button></form>"
    # A field that names no form belongs to none, also when it stands in one.
    '<form action="/k11" method=post><input name=s aria-label="Ô rời" form="">'
    "<button>Xoá</button></form>"
)
UPLOAD = (
    "<title>Tải lên</title>"
    "<button onclick=\"document.getElementById('an').click()\">Chọn tệp</button>"
    '<input type=file id=an hidden onchange="log(this.files[0].name)">'
    "<label>Tệp thấy được "
    "<input type=file id=hien onchange=\"log('thấy ' + this.files[0].name)\"></label>"
    "<button onclick=\"log('bấm')\">Không mở gì</button>" + LOG
)
LEAVING = (
    "<title>Sắp đi</title>"
    '<a href="/manh">Từng mảnh</a>'
    "<button onclick=\"setTimeout(() => location = '/khac', 400)\">Đi sau</button>"
)
# Controls that hold elements of their own: a picture, a heading, a paragraph.
INSIDE = (
    "<title>Trong nút</title>"
    f"<button onclick=\"log('xoá')\"><img alt='thùng rác' src='{DOT}' width=20 height=20> "
    "Xoá tài khoản</button>"
    '<a href="/khac" style="display: block"><h3>Gói Pro</h3><p>199.000đ mỗi tháng</p>Mua ngay</a>'
    "<div role=button tabindex=0 onclick=\"log('vĩnh viễn')\">"
    "<p>Tài khoản của bạn</p><p>Xoá vĩnh viễn</p></div>"
    "<button onclick=\"log('tiền')\"><svg width=20 height=20 role=img aria-label='biểu tượng'>"
    "<rect width=20 height=20></rect></svg> Gửi tiền</button>"
    '<div style="cursor: pointer" onclick="log(\'hẳn\')">Xoá hẳn<p>Không hoàn tác được</p></div>'
    f"<button id=xem onclick=\"log('xem')\"><img alt='mắt' src='{DOT}' width=20 height=20> "
    "<span>Xem</span></button>" + LOG
)
# A page in two pieces with a pause between; the first is enough for a browser to show it.
PIECES = ["<title>Mảnh</title><p>Phần đầu</p>" + " " * 2048, 0.6, "<button>Phần cuối</button>"]
PAGES = {
    "/": SHOP,
    "/di": LEAVING,
    "/manh": lambda _site: (200, {}, PIECES),
    "/khoa": LOGIN,
    "/khung": FRAME,
    "/form": FORMS,
    "/tep": UPLOAD,
    "/trong": INSIDE,
    # The first button stands where the shop's does, so both pages draw it under one ref.
    "/khac": '<title>Khác</title><button onclick="window.close()">Tìm</button>' + LOG,
    "/lon": "<title>Lớn dần</title><div id=dau></div><button onclick=\"log('đúng')\">Chọn</button>"
    + LOG,
    "/tim": "<title>Kết quả</title><p>Đã tìm</p>",
    "/trang": "<title>Trắng</title><p>Không có gì</p>",
    "/luu": "<title>Đã lưu</title>",
    "/ghi": "<title>Đã ghi</title>",
    "/x.png": "",
}
POSTS = ("/dat", "/loi", "/tra", "/bo", "/hai", *(f"/k{n}" for n in range(1, 12)))


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def w(tmp_path_factory):
    # Room for every test's tabs: a window a page opens is dropped once the browser is full.
    async with world(tmp_path_factory.mktemp("act"), PAGES, max_tabs=40) as made:
        private = made.intranet.url("/x.png")
        # The request is made and answered before the click is over, so what the page reached
        # for is known by the time the page is told.
        reach = (
            f"var x = new XMLHttpRequest(); x.open('GET', '{private}', false); "
            "try { x.send() } catch (e) { log('chặn') }"
        )
        made.site.pages["/goi"] = (
            f"<title>Gọi</title><img src='{private}'>"
            "<button onclick=\"log('tìm')\">Tìm</button>"
            f'<button onclick="{reach}">Tải ảnh</button>' + LOG
        )
        yield made


async def opened(w, path: str = "/", **how) -> str:
    return await build_navigate(w.kit()).run({"url": w.site.url(path), **how})


async def act(w, kind: str, ref: str, name: str, kit=None, **more) -> str:
    return await build_act(kit or w.kit()).run({"kind": kind, "ref": ref, "name": name, **more})


async def refused(w, kind: str, ref: str, name: str, **more) -> str:
    with pytest.raises(ToolError) as error:
        await act(w, kind, ref, name, **more)
    return str(error.value)


def why(w, kind: str, ref: str, name: str, kit=None, **more) -> str | None:
    """What the gate is told about a call: the reason it stops for a person, or None."""
    return build_act(kit or w.kit()).ask_when({"kind": kind, "ref": ref, "name": name, **more})


def heads(answer: str) -> list[str]:
    """What an answer says before the line that announces its fence."""
    return parts(answer)[0].splitlines()[:-1]


def ref_at(answer: str, pattern: str) -> str:
    """The ref of an element that has no name, found by what its line looks like."""
    match = re.search(pattern, answer)
    assert match, (pattern, answer)
    return match.group(1)


def done(kind: str, ref: str) -> str:
    return t.ACT_DONE.format(kind=kind, ref=ref)


async def logged(tab) -> str:
    return await tab.page.inner_text("#log")


async def value(tab, selector: str) -> str:
    return await tab.page.input_value(selector)


async def test_the_tool_stops_for_a_person_by_its_own_rule_and_is_not_one_to_run_again(w):
    tool = build_act(w.kit())

    assert (tool.name, tool.requires_approval) == ("browser_act", True)
    assert (tool.replay_safe, tool.parallel) == (False, False)
    assert tool.ask_when is not None and tool.allow_when is None and tool.ask_reason is None
    assert tool.parameters["required"] == ["kind", "ref", "name"]
    assert set(tool.parameters["properties"]) == {
        *("kind", "ref", "name", "text", "key", "value", "path", "tab", "timeout_s")
    }


@talking("act-click")
async def test_a_click_is_made_once_and_the_page_after_it_is_what_the_model_is_given(w):
    first = await opened(w)
    tab, ref = w.tab("act-click"), ref_of(first, "Tìm")

    assert why(w, "click", ref, "Tìm") is None
    answer = await act(w, "click", ref, " tìm ")

    assert heads(answer) == [done("click", ref), "Tab t1"]
    assert "Địa chỉ: " + w.site.url("/") in parts(answer)[1]
    assert ": tìm;" in parts(answer)[1] and await logged(tab) == "tìm;"
    # The page told after an action is the one the next action is checked against.
    line = ref_at(answer, r"paragraph \[ref=(\w+)\]: tìm;")
    assert line in tab.shown.nodes and line not in first


@talking("act-kinds")
async def test_each_kind_does_its_one_thing_to_the_element_named(w):
    first = await opened(w)
    tab = w.tab("act-kinds")
    note, name, message = (ref_of(first, x) for x in ("Ghi chú", "Tên", "Lời nhắn"))
    item = ref_at(first, r"listitem \[ref=(\w+)\]")

    await act(w, "type", name, "Tên", text=" Áo ")
    await act(w, "type", name, "Tên", text="dài ")  # typed where the cursor is, as keys are
    await act(w, "press", name, "Tên", key="x")
    await act(w, "fill", message, "Lời nhắn", text="một\nhai")
    await act(w, "fill", note, "Ghi chú", text="mới")  # in place of what the field held
    await act(w, "fill", ref_of(first, "Soạn thảo"), "Soạn thảo", text="thư")
    assert [await value(tab, x) for x in ("#ten", "#msg", "#note")] == [
        " Áo dài x",
        "một\nhai",
        "mới",
    ]
    assert await tab.page.inner_text("#soan") == "thư"
    await act(w, "fill", message, "Lời nhắn", text="")
    assert await value(tab, "#msg") == ""

    for key in ("arrowdown", "Shift+Tab", "Enter"):  # no form here: Enter is a key like any
        await act(w, "press", note, "Ghi chú", key=key)
    assert await logged(tab) == "ArrowDown;Shift+Tab;Enter;"

    chosen = await act(w, "select", ref_of(first, "Màu"), "Màu", value="Xanh")
    assert await value(tab, "#mau") == "xanh" and 'option "Xanh" [selected]' in chosen
    await act(w, "hover", ref_of(first, "Rê chuột"), "Rê chuột")
    await act(w, "click", item, "")
    await act(w, "click", ref_of(first, "Thêm"), "Thêm")
    assert await logged(tab) == "ArrowDown;Shift+Tab;Enter;màu xanh;rê;món;thêm;"

    assert await tab.page.evaluate("window.scrollY") == 0
    far = await act(w, "scroll", ref_of(first, "Ở xa"), "Ở xa")
    assert await tab.page.evaluate("window.scrollY") > 0
    assert heads(far) == [done("scroll", ref_of(first, "Ở xa")), "Tab t1"]
    assert await logged(tab) == "ArrowDown;Shift+Tab;Enter;màu xanh;rê;món;thêm;"


@talking("act-stale")
async def test_an_element_is_acted_on_only_while_it_is_the_one_the_model_was_shown(w):
    first = await opened(w)
    tab, ref = w.tab("act-stale"), ref_of(first, "Tìm")

    assert await refused(w, "click", ref, "Tìm kiếm") == (
        t.NAME_MISMATCH.format(ref=ref, name="Tìm kiếm")
    )
    assert await refused(w, "click", "e999", "Tìm") == t.REF_UNKNOWN.format(ref="e999")
    assert why(w, "click", "e999", "Xoá") is None  # nothing will be done, nobody is asked

    # The page gives the button another name once the model has looked: the browser draws
    # it under a new ref, and the old one is no element any more.
    await tab.page.evaluate("document.querySelector('button').textContent = 'Xoá'")
    new = ref_of(await tab.page.aria_snapshot(mode="ai"), "Xoá")

    assert new != ref
    assert await refused(w, "click", ref, "Tìm") == t.REF_GONE.format(ref=ref)
    assert await refused(w, "click", ref, "Xoá") == t.REF_GONE.format(ref=ref)
    assert await refused(w, "click", new, "Xoá") == t.REF_UNKNOWN.format(ref=new)
    assert await logged(tab) == ""

    again = await build_snapshot(w.kit()).run({})
    assert ref_of(again, "Xoá") == new
    assert why(w, "click", new, "Xoá") == t.ASK_WORD.format(
        kind="click", name="Xoá", host="127.0.0.1", word="xoá"
    )
    await tab.page.evaluate("document.querySelector('button').remove()")
    assert await refused(w, "click", new, "Xoá") == t.REF_GONE.format(ref=new)
    assert await logged(tab) == ""


@talking("act-grown")
async def test_a_ref_stays_with_its_element_when_the_page_grows_around_it(w):
    first = await opened(w, "/lon")
    tab, ref = w.tab("act-grown"), ref_of(first, "Chọn")

    await tab.page.evaluate(
        "document.getElementById('dau').innerHTML = "
        '\'<button onclick="log(1)">Chọn 1</button><button onclick="log(2)">Chọn 2</button>\''
    )
    answer = await act(w, "click", ref, "Chọn")

    assert await logged(tab) == "đúng;"
    assert ref_of(answer, "Chọn") == ref and ref_of(answer, "Chọn 1") != ref


@talking("act-under")
async def test_a_word_that_came_under_an_element_since_the_model_looked_stops_the_action(w):
    first = await opened(w)
    tab, item = w.tab("act-under"), ref_at(first, r"listitem \[ref=(\w+)\]")

    assert why(w, "click", item, "") is None
    await tab.page.evaluate("document.querySelector('li button').textContent = 'Xoá'")

    assert why(w, "click", item, "") is None  # the gate reads what was shown, as before
    assert await refused(w, "click", item, "") == t.STALE_ASK.format(ref=item)
    assert await logged(tab) == ""
    await act(w, "hover", item, "")  # which shows the page again: now a person is asked
    assert why(w, "click", item, "") == t.ASK_WORD.format(
        kind="click", name="", host="127.0.0.1", word="xoá"
    )


@talking("act-inside")
async def test_a_person_is_asked_for_a_click_on_what_stands_inside_a_control_that_asks(w):
    """A click on the picture in a button presses the button, and the browser draws a button
    that holds a picture without a name: what it says stands beside the picture."""
    first = await opened(w, "/trong")
    tab = w.tab("act-inside")
    inside = (
        (ref_of(first, "thùng rác"), "thùng rác", "xoá"),  # the picture in a button
        (ref_of(first, "Gói Pro"), "Gói Pro", "mua"),  # the heading in a link
        (ref_at(first, r"paragraph \[ref=(\w+)\]: 199"), "", "mua"),
        (ref_at(first, r"paragraph \[ref=(\w+)\]: Tài khoản"), "", "xoá"),  # a box made a button
        (ref_of(first, "biểu tượng"), "biểu tượng", "gửi"),  # a drawing in a button
        (ref_at(first, r"paragraph \[ref=(\w+)\]: Không hoàn tác"), "", "xoá"),  # under a pointer
    )

    for ref, name, word in inside:
        assert why(w, "click", ref, name) == t.ASK_WORD.format(
            kind="click", name=name, host="127.0.0.1", word=word
        )
        assert why(w, "hover", ref, name) is None
    assert await logged(tab) == ""

    # A control that asks for nothing is pressed through what it holds, and nobody is asked.
    eye = ref_of(first, "mắt")
    assert why(w, "click", eye, "mắt") is None
    await act(w, "click", eye, "mắt")
    assert await logged(tab) == "xem;"
    # Once it says something else than the model saw, the click is not made.
    await tab.page.evaluate("document.querySelector('#xem span').textContent = 'Xoá'")
    assert why(w, "click", eye, "mắt") is None
    assert await refused(w, "click", eye, "mắt") == t.STALE_ASK.format(ref=eye)
    assert await logged(tab) == "xem;"


@talking("act-moved")
async def test_a_page_that_went_elsewhere_since_the_model_looked_is_not_acted_on(w):
    first = await opened(w)
    tab, ref = w.tab("act-moved"), ref_of(first, "Tìm")

    await tab.page.evaluate("location.hash = 'muc-2'")
    await act(w, "click", ref, "Tìm")  # a move within the page is none
    assert await logged(tab) == "tìm;"

    # The page takes another address and keeps its elements, as an app of one page does:
    # the button is there under the same ref and name, on a page the model never saw.
    await tab.page.evaluate("history.pushState({}, '', '/khac')")

    assert ref_of(await tab.page.aria_snapshot(mode="ai"), "Tìm") == ref
    assert await refused(w, "click", ref, "Tìm") == t.PAGE_MOVED
    assert await logged(tab) == "tìm;"
    await tab.page.goto(w.site.url("/khac"))  # another document, whose button closes the window
    assert await refused(w, "click", ref, "Tìm") == t.PAGE_MOVED
    assert not tab.page.is_closed()


@talking("act-secret")
async def test_a_password_a_code_and_a_card_number_are_never_typed_into(w):
    first = await opened(w, "/khoa")
    tab = w.tab("act-secret")
    ways = (("type", {"text": "abc"}), ("fill", {"text": "abc"}), ("press", {"key": "a"}))

    for name in ("Khoá", "Mã OTP", "Mã từ tin nhắn", "Dãy số mặt trước", "Mật mã"):
        ref = ref_of(first, name)
        for kind, more in ways:
            assert why(w, kind, ref, name, **more) is None  # no setting lets it through
            assert await refused(w, kind, ref, name, **more) == t.ACT_SECRET_FIELD
    frame = tab.page.frame_locator("iframe")
    assert [await value(tab, x) for x in ("#pw", "#otp", "#code", "#cc")] == [""] * 4
    assert await frame.locator("#fp").input_value() == ""

    # Every other field is typed into, in a frame too.
    await act(w, "type", ref_of(first, "Email"), "Email", text="a@b.vn")
    await act(w, "fill", ref_of(first, "Lời nhắn trong khung"), "Lời nhắn trong khung", text="chào")
    pressed = await act(w, "click", ref_of(first, "Trong khung"), "Trong khung")
    assert await value(tab, "#email") == "a@b.vn"
    assert await frame.locator("#fi").input_value() == "chào"
    assert 'button "Đã bấm"' in pressed


@talking("act-focus")
async def test_keys_go_to_the_element_named_or_nowhere(w):
    """The browser would hand keys meant for an element that takes none to whatever holds
    the cursor, and text meant for a label to the field it labels."""
    first = await opened(w, "/khoa")
    tab = w.tab("act-focus")
    text = ref_at(first, r"paragraph \[ref=(\w+)\]: Chú thích")
    label = ref_at(first, r"generic \[ref=(\w+)\]:\n\s+- text: Bí mật")

    await act(w, "click", ref_of(first, "Khoá"), "Khoá")  # the cursor is in the password now
    assert await tab.page.evaluate("document.activeElement.id") == "pw"

    assert await refused(w, "type", text, "", text="abc") == t.ACT_NOT_FOCUSED.format(ref=text)
    assert await refused(w, "press", text, "", key="a") == t.ACT_NOT_FOCUSED.format(ref=text)
    assert await refused(w, "fill", text, "", text="abc") == t.ACT_NOT_FIELD.format(ref=text)
    assert await refused(w, "fill", label, "", text="abc") == t.ACT_NOT_FIELD.format(ref=label)
    assert await refused(w, "type", label, "", text="abc") == t.ACT_NOT_FOCUSED.format(ref=label)
    assert [await value(tab, x) for x in ("#pw", "#pw2")] == ["", ""]


@talking("act-select")
async def test_a_choice_is_made_in_a_list_of_the_page_and_in_nothing_else(w):
    first = await opened(w)
    tab = w.tab("act-select")
    label = ref_at(first, r"generic \[ref=(\w+)\]:\n\s+- text: Màu")
    colour = ref_of(first, "Màu")

    assert await refused(w, "select", label, "", value="Xanh") == (
        t.ACT_NOT_SELECT.format(ref=label)
    )
    assert await refused(w, "select", ref_of(first, "Tên"), "Tên", value="Xanh") == (
        t.ACT_NOT_SELECT.format(ref=ref_of(first, "Tên"))
    )
    assert await value(tab, "#mau") == "do"
    # What is chosen may be what stops for a person, whatever the list is called.
    assert why(w, "select", colour, "Màu", value="Xanh") is None
    assert why(w, "select", colour, "Màu", value="Xoá màu") == t.ASK_WORD.format(
        kind="select", name="Màu", host="127.0.0.1", word="xoá"
    )
    assert why(w, "fill", colour, "Màu", text="Xoá màu", value="Xoá màu") is None


@talking("act-enter")
async def test_enter_does_not_send_a_form_a_person_would_be_asked_about(w):
    first = await opened(w, "/form")
    tab = w.tab("act-enter")
    forms = (
        ("Địa chỉ", "đặt hàng"),  # the words on a button
        ("Lời chúc", "gửi"),  # the value of a submit input
        ("Số lượng", "thanh toán"),  # the alt of an image that submits
        ("Lý do", "xoá"),  # a label for those who cannot see the icon
        ("Mã giảm giá", "xác nhận"),  # the second of two buttons, in its title
        ("Ô một", "submit"),  # a submit input that says nothing: the browser calls it Submit
        ("Ô hai", "gửi"),  # the alt of a picture the button holds
        ("Ô ba", "submit"),  # an image that submits and has no alt
        ("Ô bốn", "thanh toán"),  # a type left empty is a submit button's
        ("Ô năm", "xác nhận"),  # and so is a type nobody knows
        ("Ô sáu", "xoá"),  # a label on what the button holds
        ("Ô bảy", "đặt hàng"),  # a name written elsewhere on the page
        ("Ô tám", "xoá"),  # a button nobody sees is still what Enter presses
        ("Ô chín", "mua"),  # a button outside the form, tied to it by the form's id
        ("Ô mười", "chuyển tiền"),  # a field outside its form
    )

    for name, word in forms:
        ref = ref_of(first, name)
        assert why(w, "press", ref, name, key="Enter") is None  # the field holds no word
        for key in ("Enter", "shift+enter"):
            assert await refused(w, "press", ref, name, key=key) == (
                t.ACT_ENTER_SUBMITS.format(word=word)
            )
    await act(w, "press", ref_of(first, "Địa chỉ"), "Địa chỉ", key="a")  # any other key goes
    assert await value(tab, "[name=a]") == "a"
    assert not [x for x in w.site.seen if x.startswith("POST")]

    # A button that sends nothing does not count, whatever it says: Enter presses the other.
    sent = await act(w, "press", ref_of(first, "Ghi thêm"), "Ghi thêm", key="Enter")

    assert "POST /luu" in w.site.seen and "Tiêu đề: Đã lưu" in parts(sent)[1]
    # Nor does one that only empties the form, or stands in it and belongs to another.
    again = await opened(w, "/form")
    sent = await act(w, "press", ref_of(again, "Ghi lại"), "Ghi lại", key="Enter")

    assert "POST /ghi" in w.site.seen and "Tiêu đề: Đã ghi" in parts(sent)[1]
    # And Enter in a field of no form sends none, whatever the form around it would do.
    last = await opened(w, "/form")
    stayed = await act(w, "press", ref_of(last, "Ô rời"), "Ô rời", key="Enter")

    assert "Địa chỉ: " + w.site.url("/form") in parts(stayed)[1]
    assert not [x for x in w.site.seen if x.split()[1] in POSTS]


@talking("act-search")
async def test_enter_sends_a_form_nobody_is_asked_about_and_the_page_it_leads_to_is_told(w):
    first = await opened(w, "/form")
    ref = ref_of(first, "Từ khoá")

    await act(w, "fill", ref, "Từ khoá", text="ao")
    answer = await act(w, "press", ref, "Từ khoá", key="Enter")

    assert heads(answer) == [done("press", ref), "Tab t1"]
    assert "Địa chỉ: " + w.site.url("/tim?q=ao") in parts(answer)[1]
    assert "Tiêu đề: Kết quả" in parts(answer)[1] and "GET /tim?q=ao" in w.site.seen
    # The page that came is the one shown now: a ref of the page before is none of its own.
    assert await refused(w, "click", ref, "Từ khoá") in (
        t.REF_UNKNOWN.format(ref=ref),
        t.REF_GONE.format(ref=ref),
    )


@talking("act-upload")
async def test_a_file_of_the_workspace_goes_to_the_chooser_an_element_opens(w, monkeypatch):
    monkeypatch.setattr(act_page, "CHOOSER_SECONDS", 0.4)
    (w.workspace / "don.pdf").write_text("đơn")
    (w.workspace.parent / "ngoai.txt").write_text("bí mật")
    first = await opened(w, "/tep")
    tab = w.tab("act-upload")
    button, shown, plain = (ref_of(first, x) for x in ("Chọn tệp", "Tệp thấy được", "Không mở gì"))

    # Always a person first, also in a conversation that runs on its own.
    assert why(w, "upload", button, "Chọn tệp", path="don.pdf\n") == (
        t.ASK_UPLOAD.format(path="don.pdf", host="127.0.0.1", name="Chọn tệp")
    )
    answer = await act(w, "upload", button, "Chọn tệp", path="don.pdf")
    assert heads(answer) == [done("upload", button), "Tab t1"]
    await act(w, "upload", shown, "Tệp thấy được", path="don.pdf")
    assert await logged(tab) == "don.pdf;thấy don.pdf;"

    # An element that opens no chooser was clicked, as the person was told, and got no file.
    assert await refused(w, "upload", plain, "Không mở gì", path="don.pdf") == (
        t.ACT_NO_CHOOSER.format(ref=plain)
    )
    assert await logged(tab) == "don.pdf;thấy don.pdf;bấm;"
    # A file that is not the agent's reaches no page: nothing is clicked for it.
    assert await refused(w, "upload", button, "Chọn tệp", path="../ngoai.txt") == WORKSPACE_ESCAPE
    assert await refused(w, "upload", button, "Chọn tệp", path="khac.pdf") == (
        t.ACT_UPLOAD_MISSING.format(path="khac.pdf")
    )
    assert await logged(tab) == "don.pdf;thấy don.pdf;bấm;"
    size = await tab.page.evaluate("document.getElementById('an').files[0].size")
    assert size == len("đơn".encode())


async def test_the_gate_starts_no_browser_and_asks_about_an_upload_anywhere(w):
    kit = w.kit("nobody")

    assert why(w, "click", "e2", "Xoá", kit=kit) is None
    assert why(w, "upload", "e2", "Chọn  tệp", kit=kit, path="a.pdf") == (
        t.ASK_UPLOAD.format(path="a.pdf", host="—", name="Chọn tệp")
    )
    assert why(w, "upload", "e2", "x", kit=kit, path="thư\nmục/" + "a" * 200) == (
        t.ASK_UPLOAD.format(path="thư mục/" + "a" * 112, host="—", name="x")
    )
    assert w.pool.running("nobody") is None


@talking("act-blank")
async def test_a_page_with_no_host_is_named_by_its_address_cut_short(w):
    await opened(w, "/trang")
    blank = await w.pool.running("coach").tabs.open("act-blank", "trong")

    assert why(w, "upload", "e1", "x", tab="trong", path="a.pdf") == (
        t.ASK_UPLOAD.format(path="a.pdf", host="about:blank", name="x")
    )
    await blank.page.goto("about:blank#" + "a" * 100)
    assert why(w, "upload", "e1", "x", tab="trong", path="a.pdf") == (
        t.ASK_UPLOAD.format(path="a.pdf", host="about:blank#" + "a" * 68, name="x")
    )
    # With no tab named it is the tab of the last call still, not the one opened since.
    assert why(w, "upload", "e1", "x", path="a.pdf") == (
        t.ASK_UPLOAD.format(path="a.pdf", host="127.0.0.1", name="x")
    )


@talking("act-words")
async def test_a_person_is_asked_for_a_word_in_a_name_by_the_kinds_that_set_something_off(w):
    first = await opened(w)
    tab = w.tab("act-words")
    order, plain = ref_of(first, "Đặt hàng"), ref_of(first, "Tìm")
    session = w.pool.running("coach")
    was = (tab.used, tab.shown, session.tabs.last("act-words"))

    asks = {
        kind: why(w, kind, order, " Đặt   hàng ", text="x", key="Enter", value="x")
        for kind in ("click", "press", "select", "type", "fill", "hover", "scroll")
    }

    for kind in ("click", "press", "select"):
        assert asks[kind] == t.ASK_WORD.format(
            kind=kind, name="Đặt hàng", host="127.0.0.1", word="đặt hàng"
        )
    assert [asks[kind] for kind in ("type", "fill", "hover", "scroll")] == [None] * 4
    assert why(w, "click", plain, "Tìm") is None
    assert why(w, "drag", order, "Đặt hàng") is None  # no such kind: the call refuses itself
    # A name the model made up counts as the name a person is asked about.
    assert why(w, "click", plain, "x" * 90 + " xoá") == t.ASK_WORD.format(
        kind="click", name="x" * 80, host="127.0.0.1", word="xoá"
    )
    # Asking is only reading: the gate asks several times for one call.
    now = (tab.used, tab.shown, session.tabs.last("act-words"))
    assert now[0] == was[0] and now[1] is was[1] and now[2] is was[2]
    assert await logged(tab) == ""


@talking("act-hosts")
async def test_an_agent_with_hosts_is_asked_for_any_action_on_a_page_outside_them(w):
    bound = w.kit(hosts=("localhost",))
    out = await opened(w)
    ref = ref_of(out, "Tìm")
    more = {"text": "x", "key": "Tab", "value": "Đỏ"}

    for kind in ("click", "type", "fill", "press", "select", "hover", "scroll"):
        assert why(w, kind, ref, "Tìm", kit=bound, **more) == (
            t.ASK_OUTSIDE_HOSTS.format(kind=kind, host="127.0.0.1")
        )
    assert why(w, "click", ref, "Tìm") is None  # an agent with no list goes anywhere
    assert why(w, "click", "e999", "Tìm", kit=bound) is None  # nothing will be done
    assert why(w, "drag", ref, "Tìm", kit=bound) is None

    home = await build_navigate(w.kit()).run(
        {"url": w.site.url("/", host="localhost"), "tab": "nha"}
    )
    tab = w.tab("act-hosts", "nha")
    order = ref_of(home, "Đặt hàng")

    assert why(w, "click", ref, "Tìm", kit=bound) is None  # the tab of the last call
    assert why(w, "click", ref, "Tìm", kit=bound, tab="t1") == (
        t.ASK_OUTSIDE_HOSTS.format(kind="click", host="127.0.0.1")
    )
    assert why(w, "click", order, "Đặt hàng", kit=bound) == t.ASK_WORD.format(
        kind="click", name="Đặt hàng", host="localhost", word="đặt hàng"
    )

    # The page leaves for a host outside the list while nobody looks. What the gate says
    # stays what it said, and the action finds a page that is not the one shown.
    await tab.page.goto(w.site.url("/"))

    assert why(w, "click", ref, "Tìm", kit=bound) is None
    with pytest.raises(ToolError) as moved:
        await act(w, "click", ref, "Tìm", kit=bound)
    assert str(moved.value) == t.PAGE_MOVED and await logged(tab) == ""


@talking("act-two")
async def test_an_action_is_for_the_tab_named_or_for_the_tab_of_the_last_call(w):
    first = await opened(w, tab="mot")
    await opened(w, "/khac", tab="hai")
    one, two = w.tab("act-two", "mot"), w.tab("act-two", "hai")
    order = ref_of(first, "Đặt hàng")
    asked = t.ASK_WORD.format(kind="click", name="Đặt hàng", host="127.0.0.1", word="đặt hàng")

    assert why(w, "click", order, "Đặt hàng") is None  # the other page has no such element
    assert why(w, "click", order, "Đặt hàng", tab="mot") == asked
    assert why(w, "click", order, "Đặt hàng", tab="ba") is None
    assert await refused(w, "click", order, "Đặt hàng") == t.REF_UNKNOWN.format(ref=order)
    assert await refused(w, "click", order, "Đặt hàng", tab="ba") == (
        t.UNKNOWN_TAB.format(label="ba", labels="hai, mot")
    )

    answer = await act(w, "click", order, "Đặt hàng", tab="mot")

    assert heads(answer) == [done("click", order), "Tab mot"]
    assert (await logged(one), await logged(two)) == ("đặt;", "")
    assert why(w, "click", order, "Đặt hàng") == asked  # which is the last call's tab now


@talking("act-gone")
async def test_an_action_never_moves_to_another_tab_when_its_own_is_gone(w):
    first = await opened(w)
    one = w.tab("act-gone")
    ref, link = ref_of(first, "Tìm"), ref_of(first, "Mở cửa sổ")

    answer = await act(w, "click", link, "Mở cửa sổ")

    assert heads(answer) == [done("click", link), "Tab t1", t.PAGE_NEW_TABS.format(labels="t2")]
    assert await refused(w, "click", ref, "Tìm", tab="t2") == t.NO_SNAPSHOT
    popup = await build_snapshot(w.kit()).run({"tab": "t2"})
    assert ref_of(popup, "Tìm") == ref  # the same ref and name as the first tab's button

    closed = await act(w, "click", ref, "Tìm")  # no label: the tab of the last call

    assert closed == t.ACT_TAB_CLOSED.format(kind="click", ref=ref, label="t2")
    assert w.tab("act-gone", "t2") is None and w.tab("act-gone") is one
    assert why(w, "click", ref, "Tìm") is None
    assert await refused(w, "click", ref, "Tìm") == t.TAB_GONE.format(labels="t1")
    assert await logged(one) == ""  # where the same call would have found a button to press
    await act(w, "click", ref, "Tìm", tab="t1")
    assert await logged(one) == "tìm;"


async def test_an_action_in_a_conversation_with_no_tab_says_to_open_one(w):
    with pytest.raises(ToolError) as none:
        await act(w, "click", "e2", "Tìm")

    assert str(none.value) == t.NO_TAB


@talking("act-reach")
async def test_what_a_page_reached_for_in_an_action_is_told_and_nothing_from_before_it(w):
    first = await opened(w, "/goi")
    tab = w.tab("act-reach")
    told = t.PAGE_REFUSED.format(hosts="127.0.0.1")

    plain = await act(w, "click", ref_of(first, "Tìm"), "Tìm")
    reach = await act(w, "click", ref_of(first, "Tải ảnh"), "Tải ảnh")

    assert told in parts(first)[1].splitlines()  # the picture the page asked for as it loaded
    assert told not in parts(plain)[1]
    assert told in parts(reach)[1].splitlines()
    assert await logged(tab) == "tìm;chặn;" and w.intranet.seen == []


@talking("act-dialog")
async def test_what_a_page_said_in_a_dialog_is_told_with_the_page_after_the_action(w):
    first = await opened(w)
    tab = w.tab("act-dialog")

    answer = await act(w, "click", ref_of(first, "Báo"), "Báo")

    assert t.PAGE_DIALOG.format(text="alert: Hết hàng") in parts(answer)[1].splitlines()
    assert tab.dialogs == []


@talking("act-slow")
async def test_an_element_that_never_gets_ready_is_given_up_after_the_time_asked(w):
    first = await opened(w)
    tab = w.tab("act-slow")
    locked, colour = ref_of(first, "Khoá"), ref_of(first, "Màu")

    assert await refused(w, "click", locked, "Khoá", timeout_s=1) == (
        t.ACT_TIMEOUT.format(ref=locked, seconds=1)
    )
    assert await refused(w, "select", colour, "Màu", value="Tím", timeout_s=0) == (
        t.ACT_TIMEOUT.format(ref=colour, seconds=1)
    )
    assert await logged(tab) == "" and await value(tab, "#mau") == "do"


@talking("act-waits")
async def test_the_time_an_element_is_given_is_the_one_asked_within_bounds(w, monkeypatch):
    first = await opened(w)
    ref = ref_of(first, "Tìm")
    waits = []

    async def note(*given) -> None:
        waits.append(given[-1])

    monkeypatch.setattr(tools_act, "guard", note)
    monkeypatch.setattr(tools_act, "perform", note)
    for given in ({}, {"timeout_s": 0}, {"timeout_s": 3}, {"timeout_s": 99}, {"timeout_s": "x"}):
        await act(w, "hover", ref, "Tìm", **given)

    assert waits == [x for ms in (8_000, 1_000, 3_000, 30_000, 8_000) for x in (ms, ms)]


@talking("act-unseen")
async def test_an_action_made_is_told_as_made_when_the_page_cannot_be_read_after_it(w, monkeypatch):
    """Told as failed, it would be made again: a second click, a second order."""
    first = await opened(w)
    tab, ref = w.tab("act-unseen"), ref_of(first, "Tìm")

    async def broken(*_args, **_kwargs):
        raise BrowserError("Target crashed\nCall log:\n  - quoting the page")

    async def stuck(*_args, **_kwargs):
        await asyncio.sleep(30)

    monkeypatch.setattr(tools_act, "page_report", broken)
    crashed = await act(w, "click", ref, "Tìm")
    monkeypatch.setattr(tools_act, "page_report", stuck)
    monkeypatch.setattr(k, "CALL_SECONDS", 0.5)
    hung = await act(w, "click", ref, "Tìm", timeout_s=1)

    # Of why the page could not be read, the tool's own line and not the fence under it.
    why_not = t.BROWSER_FAILED.format(error="Error")
    assert crashed == done("click", ref) + "\n" + t.ACT_UNSEEN.format(error=why_not)
    assert hung == done("click", ref) + "\n" + (
        t.ACT_UNSEEN.format(error=t.PAGE_STUCK.format(seconds=2))
    )
    assert await logged(tab) == "tìm;tìm;"


@talking("act-shut")
async def test_a_tab_that_closes_while_the_page_is_read_is_told_as_closed(w, monkeypatch):
    first = await opened(w)
    tab, ref = w.tab("act-shut"), ref_of(first, "Tìm")

    async def closing(_kit, _session, held, **_how):
        await held.page.close()
        raise BrowserError("Target page, context or browser has been closed")

    monkeypatch.setattr(tools_act, "page_report", closing)

    assert await act(w, "click", ref, "Tìm") == (
        t.ACT_TAB_CLOSED.format(kind="click", ref=ref, label="t1")
    )
    assert tab.page.is_closed()


@talking("act-refs")
async def test_every_ref_the_browser_draws_is_one_the_model_can_name(w):
    for path in ("/", "/khoa", "/form", "/tep"):
        await opened(w, path)
        tab = w.tab("act-refs")
        drawn = set(re.findall(r"\[ref=(\w+)\]", await tab.page.aria_snapshot(mode="ai")))

        assert drawn == set(tab.shown.nodes) and len(drawn) >= 5


@talking("act-pieces")
async def test_a_page_still_arriving_after_a_click_is_told_whole(w):
    first = await opened(w, "/di")
    tab = w.tab("act-pieces")

    answer = await act(w, "click", ref_of(first, "Từng mảnh"), "Từng mảnh")

    assert "Địa chỉ: " + w.site.url("/manh") in parts(answer)[1]
    assert "Phần đầu" in answer and ref_of(answer, "Phần cuối") in tab.shown.nodes


@talking("act-later")
async def test_a_page_that_leaves_a_moment_after_a_click_is_told_as_where_it_went(w, monkeypatch):
    monkeypatch.setattr(k, "SETTLE_SECONDS", 1.0)  # well past the moment the page takes
    first = await opened(w, "/di")

    answer = await act(w, "click", ref_of(first, "Đi sau"), "Đi sau")

    assert "Địa chỉ: " + w.site.url("/khac") in parts(answer)[1]
    assert "Sắp đi" not in answer and w.tab("act-later").shown.url == w.site.url("/khac")
