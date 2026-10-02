"""Whether the chat pasted a canvas back: the share of the canvas's three-word runs the chat
repeats, whatever shape the lines take, leaving out the title, the heading the canvas opens with
and a single line the chat quotes."""

from __future__ import annotations

import pytest
from eval_paste import PASTE_SHARE, Canvas, pasted_share

CLEANING = Canvas(
    "Kế hoạch dọn nhà",
    "# Kế hoạch dọn nhà\n\n"
    "- **Thứ Hai:** Phòng khách\n"
    "- Thứ Ba: Bếp\n"
    "- Thứ Tư: Phòng ngủ\n"
    "- Thứ Năm: Phòng tắm\n"
    "- Thứ Sáu: Ban công và cửa sổ\n",
)
WEEKEND = Canvas(
    "Việc cuối tuần",
    "# Việc cuối tuần\n\n- Dọn tủ lạnh\n- Đi chợ\n- Giặt chăn\n- Gọi điện cho bà\n- Tưới cây\n",
)


@pytest.mark.parametrize(
    "said",
    [
        "Đây là kế hoạch:\n\n**Kế hoạch dọn nhà**\n- __Thứ Hai:__ Phòng khách\n- Thứ Ba: Bếp\n"
        "- Thứ Tư: Phòng ngủ\n- Thứ Năm: Phòng tắm\n- Thứ Sáu: Ban công và cửa sổ",
        "| Ngày | Việc |\n|---|---|\n| Thứ Hai | Phòng khách |\n| Thứ Ba | Bếp |\n"
        "| Thứ Tư | Phòng ngủ |\n| Thứ Năm | Phòng tắm |\n| Thứ Sáu | Ban công và cửa sổ |",
        "thu hai - phong khach; thu ba - bep; thu tu - phong ngu; thu nam - phong tam;"
        " thu sau - ban cong va cua so.",
    ],
    ids=["as-written", "as-a-table", "on-one-line-without-accents"],
)
def test_a_canvas_of_short_lines_said_back_in_any_shape_is_all_pasted(said):
    assert pasted_share(CLEANING, said) == 1.0


def test_naming_the_title_and_quoting_one_line_is_not_a_paste():
    said = 'Mình đã tạo canvas "Kế hoạch dọn nhà". Ví dụ thứ Hai: Phòng khách, còn lại bạn sửa dần.'

    assert pasted_share(CLEANING, said) == 0.0


def test_a_one_line_canvas_said_back_with_the_heading_it_opens_with_is_a_quote():
    canvas = Canvas(
        "Đi chợ", "\n# Đi chợ cuối tuần\n\nMua rau muống, cà chua, trứng gà và đậu phụ\n"
    )
    said = "Đã ghi vào canvas Đi chợ cuối tuần: mua rau muống, cà chua, trứng gà và đậu phụ."

    assert pasted_share(canvas, said) == 0.0


def test_a_line_that_is_the_title_is_not_counted_whatever_its_markup():
    canvas = Canvas(
        "Đi chợ cuối tuần", "**Đi chợ cuối tuần**\nMua rau muống, cà chua, trứng gà và đậu phụ\n"
    )
    said = "Canvas Đi chợ cuối tuần giờ có: mua rau muống, cà chua, trứng gà và đậu phụ."

    assert pasted_share(canvas, said) == 0.0


def test_quoting_the_line_it_changed_is_not_a_paste_even_when_that_line_is_most_of_the_canvas():
    canvas = Canvas(
        "Việc cuối tuần",
        "# Việc cuối tuần\n\n- Dọn tủ lạnh, bỏ đồ hết hạn và lau các ngăn kéo\n- Đi chợ\n",
    )
    said = "Mình đã sửa dòng đầu thành: Dọn tủ lạnh, bỏ đồ hết hạn và lau các ngăn kéo."

    assert pasted_share(canvas, said) == 0.0


def test_a_line_the_canvas_repeats_is_still_one_line_and_accents_do_not_matter():
    canvas = Canvas(
        "Thực đơn",
        "- Thứ Hai: cơm gà xối mỡ rau luộc\n- Thứ Hai: cơm gà xối mỡ rau luộc\n"
        "- Thứ Ba: đậu phụ sốt cà chua\n",
    )

    assert pasted_share(canvas, "thu hai: com ga xoi mo rau luoc") == 0.0
    both = "Thu Hai: com ga xoi mo rau luoc. Thu Ba: dau phu sot ca chua"
    assert pasted_share(canvas, both) == 13 / 14


def test_quoting_the_two_lines_it_changed_in_a_longer_canvas_is_not_a_paste():
    canvas = Canvas(
        "Thực đơn tuần",
        "# Thực đơn tuần\n\n- Thứ Hai: cơm gà, rau muống luộc\n- Thứ Ba: bún riêu cua\n"
        "- Thứ Tư: cá kho tộ, canh chua\n- Thứ Năm: phở bò tái\n- Thứ Sáu: đậu phụ sốt cà chua\n"
        "- Thứ Bảy: lẩu nấm\n- Chủ Nhật: ăn ngoài\n",
    )
    said = (
        "Mình đã đổi hai ngày: Thứ Ba: bún riêu cua, và Thứ Sáu: đậu phụ sốt cà chua."
        " Các ngày khác giữ nguyên."
    )

    assert 0.0 < pasted_share(canvas, said) < PASTE_SHARE


def test_naming_the_headings_of_a_longer_document_is_not_a_paste():
    canvas = Canvas(
        "Kế hoạch dự án",
        "# Kế hoạch dự án\n\n"
        "## Mục tiêu\nHoàn thành bản thử nghiệm trước cuối tháng Ba, đủ cho năm người dùng thử.\n"
        "## Phạm vi\nChỉ làm phần đăng nhập, danh sách việc và nhắc việc qua email.\n"
        "## Rủi ro\nThiếu người kiểm thử vào tuần cuối, và máy chủ thử nghiệm chưa có.\n",
    )
    said = "Mình đã soạn kế hoạch trong canvas, gồm ba phần: Mục tiêu, Phạm vi và Rủi ro."

    assert pasted_share(canvas, said) == 0.0


def test_naming_the_items_it_added_is_not_a_paste_but_saying_the_whole_list_again_is():
    assert pasted_share(WEEKEND, 'Đã thêm hai việc: "gọi điện cho bà" và "tưới cây".') == 0.0
    again = "Danh sách giờ là: dọn tủ lạnh, đi chợ, giặt chăn, gọi điện cho bà, tưới cây."
    assert pasted_share(WEEKEND, again) == 1.0


def test_an_outline_said_back_with_other_numbering_is_all_pasted():
    canvas = Canvas(
        "Dàn ý: giấc ngủ",
        "# Dàn ý bài viết về giấc ngủ\n\n"
        "1. Vì sao ngủ đủ lại quan trọng\n2. Ngủ bao nhiêu là đủ\n3. Thói quen trước khi ngủ\n"
        "4. Ánh sáng và màn hình\n5. Cà phê, rượu và giấc ngủ\n6. Khi nào nên đi khám\n",
    )
    said = (
        "Dàn ý gồm sáu mục:\n- Vì sao ngủ đủ lại quan trọng\n- Ngủ bao nhiêu là đủ\n"
        "- Thói quen trước khi ngủ\n- Ánh sáng và màn hình\n- Cà phê, rượu và giấc ngủ\n"
        "- Khi nào nên đi khám"
    )

    assert pasted_share(canvas, said) == 1.0


def test_long_lines_said_back_without_their_labels_are_still_a_paste():
    canvas = Canvas(
        "Dọn nhà",
        "# Dọn nhà\n\n- Thứ Hai: lau sạch tủ bếp, rửa bát đĩa tồn và đổ rác\n"
        "- Thứ Ba: hút bụi phòng khách, lau kính cửa sổ và tưới cây\n",
    )
    said = (
        "Lau sạch tủ bếp, rửa bát đĩa tồn và đổ rác. "
        "Rồi hút bụi phòng khách, lau kính cửa sổ và tưới cây."
    )

    assert pasted_share(canvas, said) >= PASTE_SHARE


def test_a_canvas_too_short_to_paste_never_is():
    assert pasted_share(Canvas("Trống", ""), "anything at all") == 0.0
    assert pasted_share(Canvas("Việc", "- Đi chợ\n"), "Đi chợ nhé") == 0.0
