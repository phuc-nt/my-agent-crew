"""Strings for memory hygiene: the consolidate prompt (moved here from `texts.py` once it
grew a review list), the fact-review prompt, and the run summaries the gate produces."""

# {{ }} in the JSON example is escaped because this whole string goes through
# `str.format`, same reason a literal brace anywhere else in it would need doubling.
CONSOLIDATE_PROMPT = (
    "Dưới đây là bộ nhớ dài hạn của một trợ lý và các ghi chép hằng ngày gần đây. "
    "Viết lại bộ nhớ dài hạn sao cho cô đọng hơn: giữ mọi điều còn đúng, gộp các mục "
    "trùng nhau, bổ sung điều đáng nhớ từ ghi chép, bỏ những gì chỉ đúng trong một ngày.\n\n"
    "Mỗi dòng gạch đầu dòng có thể mang hậu tố ngày dạng (YYYY-MM-DD), là ngày dòng đó "
    "được xác nhận đúng lần cuối. Quy tắc về ngày:\n"
    "- Dòng lấy thẳng từ một ghi chép thì mang ngày của ghi chép đó.\n"
    "- KHÔNG được bịa ngày. Một dòng cũ chưa có ngày thì giữ nguyên, không thêm ngày, "
    "trừ khi ghi chép hôm nay xác nhận lại đúng điều đó.\n"
    "- Hai dòng mâu thuẫn nhau thì giữ dòng có ngày mới hơn, bỏ dòng cũ.\n\n"
    "Hôm nay là {today}. Danh sách dưới đây là các dòng cần xem lại vì chưa có ngày hoặc "
    "đã quá 90 ngày; MỖI dòng trong hai danh sách này phải được quyết định: giữ nguyên, "
    "sửa lại, hoặc bỏ hẳn, và nêu lý do ngắn cho quyết định đó.\n\n"
    "--- dòng chưa có ngày ---\n{undated}\n\n--- dòng đã cũ ---\n{stale}\n\n"
    "Giữ nguyên tiếng Việt và dạng gạch đầu dòng Markdown, tối đa 24000 ký tự. Trả lời theo "
    "đúng khuôn: nội dung bộ nhớ mới trước, rồi một dòng riêng ghi đúng ---LÝ DO---, rồi "
    "các gạch đầu dòng nêu lý do cho từng thay đổi hoặc quyết định giữ/bỏ ở trên. Không mở "
    "đầu, không giải thích gì thêm ngoài khuôn này.\n\n"
    "--- bộ nhớ hiện tại ---\n{memory}\n\n--- ghi chép gần đây ---\n{notes}"
)

CONSOLIDATE_PROPOSED_REMOVING = (
    "Đề xuất bỏ hoặc đổi {count} dòng, chờ duyệt dù agent là autonomous."
)
CONSOLIDATE_STALE = "Bộ nhớ đã bị ghi trong lúc chạy, không áp dụng đề xuất này."

REVIEW_MORE = "… và {count} dòng khác"
REVIEW_NONE = "không có"

FACT_REVIEW_PROMPT = (
    "Dưới đây là các điều đã ghi nhớ về người dùng và các ghi chép hằng ngày gần đây của "
    "một trợ lý. Xem lại từng fact: ghi chép mới có làm nó sai không, hay nó đã quá cũ và "
    "không còn ai xác nhận lại. Chỉ nêu ra fact thật sự cần quên hoặc sửa; đa số fact "
    "không cần động tới.\n\n"
    "Trả lời bằng một mảng JSON, tối đa 10 mục, mỗi mục dạng "
    '{{"action": "forget" hoặc "update", "name": "…", "body": "…" (chỉ khi update), '
    '"reason": "…"}}. `update` phải kèm `body` mới, khác với thân hiện tại. Không thêm gì '
    "ngoài mảng JSON.\n\n"
    "--- các fact ---\n{facts}\n\n--- ghi chép gần đây ---\n{notes}"
)

FACT_REVIEW_CREATED = "Đề xuất xem lại {count} fact, chờ duyệt."
FACT_REVIEW_BROKEN_JSON = "Model không trả JSON hợp lệ khi xem lại fact, bỏ qua bước này."
FACT_REVIEW_FAILED = "Bước xem lại fact lỗi, bản viết lại bộ nhớ vẫn giữ nguyên."
