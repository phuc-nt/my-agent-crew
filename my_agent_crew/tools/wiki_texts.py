"""What the wiki tools say to the agent and to the person.

The descriptions carry one instruction that matters more than the rest: read the page
before asserting what is on it. A vault makes the agent sound certain, and an agent that
answers from the index alone will state a page's title as though it had read its body.
"""

from __future__ import annotations

WIKI_GET_DESCRIPTION = (
    "Đọc một trang wiki theo tên (slug). Dùng trước khi khẳng định điều gì về một thứ có"
    " trang riêng: mục Wiki trong lời nhắc chỉ liệt kê tên, không phải nội dung."
)
WIKI_SEARCH_DESCRIPTION = (
    "Tìm trong các trang wiki theo từ khoá, ưu tiên tên trang. Trả về tên trang kèm đoạn"
    " khớp; muốn đọc cả trang thì gọi wiki_get."
)
WIKI_APPLY_DESCRIPTION = (
    "Tạo hoặc cập nhật một trang wiki. 'sources' là bắt buộc: ghi rõ trang này dựng từ đâu"
    " ('note:2026-09-20' hoặc 'conv:<id>'), vì một trang không nguồn là một trang tự bịa."
    " Phần liên kết do máy sinh sẽ được giữ nguyên, không cần viết."
)

WIKI_NOT_FOUND = "Không có trang wiki nào tên '{slug}'."
WIKI_EMPTY = "Chưa có trang wiki nào khớp."
WIKI_NO_SOURCES = "Trang wiki phải có ít nhất một nguồn trong 'sources'."
WIKI_NO_BODY = "Trang wiki phải có nội dung."
WIKI_SAVED = "Đã lưu trang '{slug}' ({kind}), {sources} nguồn."
WIKI_VAULT_EMPTY = "Chưa có trang wiki nào."

#: The prompt adds its own `##`, so this is the bare title.
WIKI_SECTION_TITLE = "Wiki"
WIKI_PROMPT_HINT = (
    "Đây chỉ là danh sách tên trang, không phải nội dung. Gọi `wiki_get` để đọc trang"
    " trước khi khẳng định điều gì trong đó."
)
#: Used only when the vault is too large to list: the shape of it, and nothing more.
WIKI_PROMPT_COUNT = "{count} trang, quá nhiều để liệt kê. Dùng `wiki_search` để tìm."

# The compile. The prompt asks for pages about *things*, not about days, because a page
# named after a date is only a daily note that has moved house. It insists on sources for
# the same reason the tool does, and it offers `review` plus `questions` so a model that
# is unsure has somewhere to put the doubt other than into a confident sentence.
#
# The linking rule is stated twice, in the rules and again beside the JSON shape, because
# a first compile against real notes produced 23 pages and not one `[[link]]`: mentioned
# once among six rules it reads as optional, and on a first run there are no existing
# pages to point at, so the model has to be told that the batch links to itself.
WIKI_COMPILE_PROMPT = (
    "Dưới đây là các ghi chép hằng ngày của một trợ lý, và danh sách trang wiki đã có.\n"
    "Hãy rút ra các trang wiki: mỗi trang nói về MỘT thứ có tên (người, nơi chốn, hợp"
    " đồng, dự án) hoặc một ý niệm lặp lại. Không tạo trang đặt tên theo ngày.\n\n"
    "Quy tắc:\n"
    "- 'sources' bắt buộc, ghi 'note:YYYY-MM-DD' của những ghi chép đã dùng. Không có"
    " nguồn thì không viết trang đó.\n"
    "- Chỉ viết điều ghi chép thực sự nói. Không suy diễn, không bịa chi tiết.\n"
    "- Trang đã có thì viết lại cho đầy đủ hơn, giữ nguyên tiêu đề cũ.\n"
    "- Khi thân trang nhắc tới một thứ cũng có trang trong đợt này hoặc trong danh sách"
    " đã có, viết tên nó dạng [[Tên trang]]. Đây là cách các trang nối với nhau; một"
    " vault không liên kết chỉ là một đống ghi chép rời.\n"
    "- Chỗ nào mâu thuẫn hoặc không chắc: đặt 'status': 'review' và ghi điều còn ngờ vào"
    " 'questions'.\n\n"
    "Trả về DUY NHẤT một mảng JSON, mỗi phần tử:\n"
    '{{"title": "...", "kind": "entities|concepts|syntheses", "body": "... [[Trang'
    ' khác]] ...", "sources": ["note:..."], "questions": ["..."], "status": "ok|review"}}'
    "\n\n"
    "--- trang đã có ---\n{pages}\n\n--- ghi chép ---\n{notes}"
)
WIKI_COMPILE_NO_PAGES = "(chưa có trang nào)"
WIKI_COMPILE_JOB_NAME = "Dựng wiki từ ghi chép"
WIKI_COMPILE_RUN_TITLE = "Dựng wiki · {agent}"
WIKI_COMPILE_NOTHING_NEW = "Không có ghi chép mới kể từ lần dựng trước, bỏ qua."
WIKI_COMPILE_EMPTY = "Model không trả về trang nào dùng được."
WIKI_COMPILE_PROPOSED = "Đã đề xuất {count} trang wiki, chờ duyệt."
WIKI_COMPILE_APPLIED = "Đã ghi {count} trang wiki, cập nhật liên kết ở {linked} trang."
#: The proposal's own description, shown in the approval list.
WIKI_COMPILE_DESCRIPTION = "{count} trang: {titles}"
