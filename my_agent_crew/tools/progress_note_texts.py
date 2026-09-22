"""Strings for the progress-note tool.

They live apart from `my_agent_crew/texts.py` only because that file is at its size
budget; there is no other reason to look for them here.
"""

from __future__ import annotations

#: The description is the whole interface: the model decides when to call this from these
#: sentences alone. So it says what a note is for (someone is watching), when to send one
#: (before a slow or multi-step piece of work), and — the part that matters most — what it
#: is not. Without the last line a model treats a free-form writing tool as a scratchpad
#: and narrates every thought, which buries the timeline it was meant to clarify.
PROGRESS_NOTE_DESCRIPTION = (
    "Báo cho người đang theo dõi biết bạn sắp làm gì, bằng một câu ngắn."
    " Dùng trước một việc dài hoặc nhiều bước — tìm tài liệu, chạy lệnh lâu,"
    " xử lý từng mục trong danh sách — để họ thấy tiến trình thay vì một khoảng lặng."
    " Không dùng để trả lời người dùng, không dùng để ghi nhớ điều gì, và không cần"
    " gọi trước mỗi việc nhỏ."
)

#: The model sees this, not the person; the note itself already went to the timeline.
PROGRESS_NOTE_OK = "Đã báo tiến trình."

#: An empty note is not worth failing the turn over, but the model should know nothing was
#: shown, or it will assume the person saw something they did not.
PROGRESS_NOTE_EMPTY = "Ghi chú rỗng, không hiển thị gì."
