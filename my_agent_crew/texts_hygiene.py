"""Strings for memory hygiene: the consolidate prompt (moved here from `texts.py` once it
grew a review list), the fact-review prompt, and the run summaries the gate produces."""

# {{ }} in the JSON example is escaped because this whole string goes through
# `str.format`, same reason a literal brace anywhere else in it would need doubling.
CONSOLIDATE_PROMPT = (
    "Dưới đây là bộ nhớ dài hạn của một trợ lý và các ghi chép hằng ngày gần đây. "
    "Viết lại bộ nhớ dài hạn sao cho cô đọng hơn: giữ mọi điều còn đúng, gộp các mục "
    "trùng nhau, bổ sung điều đáng nhớ từ ghi chép, bỏ những gì chỉ đúng trong một ngày.\n\n"
    "Ghi chép gần đây có cả tóm tắt các cuộc trò chuyện (mục ghi «trò chuyện»). Đó là lời "
    "kể lại: chỉ đưa vào bộ nhớ điều người dùng đã nói rõ hoặc việc đã làm xong, không suy "
    "đoán thêm, và bỏ qua chuyện chỉ đúng trong cuộc trò chuyện đó.\n\n"
    "Mỗi dòng gạch đầu dòng có thể mang hậu tố ngày dạng (YYYY-MM-DD), là ngày dòng đó "
    "được xác nhận đúng lần cuối. Quy tắc về ngày:\n"
    "- Dòng lấy thẳng từ một ghi chép thì mang ngày của ghi chép đó.\n"
    "- KHÔNG được bịa ngày. Một dòng cũ chưa có ngày thì giữ nguyên, không thêm ngày, "
    "trừ khi ghi chép hôm nay xác nhận lại đúng điều đó.\n"
    "- Hai dòng mâu thuẫn nhau thì giữ dòng có ngày mới hơn, bỏ dòng cũ.\n\n"
    "Điều chỉ đúng trong một thời gian (đơn đang giao, chuyến đi, gói sắp hết hạn, đang "
    "ốm) ghi thêm ngày cuối còn đúng sau mũi tên: (YYYY-MM-DD → YYYY-MM-DD). Ngày cuối phải "
    "lấy từ ghi chép; không biết khi nào hết đúng thì đừng đưa điều đó vào bộ nhớ. Trạng "
    "thái đã có trong sổ hay công cụ của agent (đơn hàng, giao dịch, số đo) thì không chép "
    "vào bộ nhớ.\n\n"
    "Hôm nay là {today}. Danh sách dưới đây là các dòng cần xem lại vì chưa có ngày hoặc "
    "đã quá 90 ngày; MỖI dòng trong hai danh sách này phải được quyết định: giữ nguyên, "
    "sửa lại, hoặc bỏ hẳn, và nêu lý do ngắn cho quyết định đó. Dòng đã qua ngày cuối thì "
    "bỏ, trừ khi ghi chép cho thấy điều đó vẫn đúng.\n\n"
    "--- dòng chưa có ngày ---\n{undated}\n\n--- dòng đã cũ ---\n{stale}\n\n"
    "--- dòng đã qua ngày cuối ---\n{expired}\n\n{budget}"
    "Giữ nguyên tiếng Việt và dạng gạch đầu dòng Markdown, tối đa {limit} ký tự. Trả lời theo "
    "đúng khuôn: nội dung bộ nhớ mới trước, rồi một dòng riêng ghi đúng ---LÝ DO---, rồi "
    "các gạch đầu dòng nêu lý do cho từng thay đổi hoặc quyết định giữ/bỏ ở trên. Không mở "
    "đầu, không giải thích gì thêm ngoài khuôn này.\n\n"
    "--- bộ nhớ hiện tại ---\n{memory}\n\n--- ghi chép gần đây ---\n{notes}"
)

# How a conversation's recap is headed among the notes. The day leads: the rewrite's date
# check reads the first ten characters of each heading as a day it was shown.
EPISODE_LABEL = "{day} · trò chuyện «{title}»"

# `{why}` joins whichever of the two HELD_* parts apply, so a rewrite that only brings an
# unsourced date is not reported as dropping lines.
CONSOLIDATE_HELD = "Đề xuất chờ duyệt dù agent là autonomous: {why}."
HELD_REMOVED = "bỏ hoặc đổi {count} dòng"
HELD_INVENTED = "{count} ngày không rõ nguồn gốc"
# Appended to the proposal's reasons so the person sees which dates came from nowhere.
CONSOLIDATE_INVENTED_DATES = "- Ngày không rõ nguồn gốc: {dates}"
CONSOLIDATE_STALE = "Bộ nhớ đã bị ghi trong lúc chạy, không áp dụng đề xuất này."

# Filled into the rewrite prompt as `{budget}` only for an agent with a memory budget.
CONSOLIDATE_BUDGET = (
    "Bộ nhớ của trợ lý này có ngân sách {budget} ký tự. Không vừa thì bỏ trước những gì "
    "tra lại được trong sổ hay công cụ của trợ lý, rồi tới điều lâu không được nhắc lại; "
    "nêu lý do cho từng dòng bỏ.\n\n"
)
HELD_OVER_BUDGET = "dài {size} ký tự, quá ngân sách {budget}"

ADMISSION_PROMPT = (
    "Trợ lý «{agent}» ({description}) vừa viết lại bộ nhớ dài hạn của nó, có thêm các dòng "
    "mới dưới đây. Bộ nhớ dài hạn đi theo mọi lượt trò chuyện, nên chỉ nhận điều đáng mang "
    "theo lâu: sở thích, quy tắc, quyết định, bài học về người dùng hay công việc, hoặc "
    "điều chỉ đúng trong một thời gian và đã ghi ngày cuối (YYYY-MM-DD → YYYY-MM-DD). Không "
    "nhận trạng thái trợ lý tra lại được bất cứ lúc nào trong sổ, database hay công cụ của "
    "nó (đơn hàng đang ở đâu, số dư, lịch sắp tới, số đo), cũng không nhận việc đã xong mà "
    "không còn ảnh hưởng gì về sau.\n\n"
    "Trả lời mỗi dòng mới một dòng, theo đúng số thứ tự: `1. NHẬN` hoặc `1. BỎ: lý do "
    "ngắn`. Không thêm gì khác.\n\n"
    "--- dòng mới ---\n{lines}"
)
# Appended to the proposal's reasons, one per line the screen turned away.
ADMISSION_TURNED_AWAY = "- Không nhận vào bộ nhớ: {line} ({why})"
ADMISSION_NO_REASON = "không nêu lý do"
ADMISSION_FAILED = "- Bước sàng lọc dòng mới lỗi, các dòng mới được giữ nguyên."

REVIEW_MORE = "… và {count} dòng khác"
REVIEW_NONE = "không có"

FACT_REVIEW_PROMPT = (
    "Dưới đây là các điều đã ghi nhớ về người dùng và các ghi chép hằng ngày gần đây của "
    "một trợ lý. Xem lại từng fact: ghi chép mới có làm nó sai không, hay nó đã quá cũ và "
    "không còn ai xác nhận lại. Chỉ nêu ra fact thật sự cần quên hoặc sửa; đa số fact "
    "không cần động tới. Mỗi fact là một dòng dạng `- tên (ngày cập nhật) — mô tả: thân`; "
    "`name` trong câu trả lời là đúng phần tên đó.\n\n"
    "Trả lời bằng một mảng JSON, tối đa 10 mục, mỗi mục dạng "
    '{{"action": "forget" hoặc "update", "name": "…", "body": "…" (chỉ khi update), '
    '"reason": "…"}}. `update` phải kèm `body` mới, khác với thân hiện tại. Không thêm gì '
    "ngoài mảng JSON.\n\n"
    "--- các fact ---\n{facts}\n\n--- ghi chép gần đây ---\n{notes}"
)

FACT_REVIEW_MORE = "… còn {count} fact khác"
FACT_REVIEW_CREATED = "Đề xuất xem lại {count} fact, chờ duyệt."
FACT_REVIEW_BROKEN_JSON = "Model không trả JSON hợp lệ khi xem lại fact, bỏ qua bước này."
FACT_REVIEW_FAILED = "Bước xem lại fact lỗi, bản viết lại bộ nhớ vẫn giữ nguyên."
