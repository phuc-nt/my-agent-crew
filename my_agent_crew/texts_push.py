"""Strings of the notifications a phone or a browser shows when the crew pushes to it
(`my_agent_crew/webpush/notices.py`). Constants only, and nothing imported.

A notification passes through the browser maker's push service and lands on a lock screen,
so it says only what kind of thing happened: no agent's words, no tool, no name. What it
was is read on opening it."""

APPROVAL_TITLE = "Cần bạn duyệt"
APPROVAL_BODY = "Một agent đang chờ bạn cho phép một việc. Mở hộp thư để duyệt."
QUESTION_TITLE = "Có câu hỏi cho bạn"
QUESTION_BODY = "Một agent đang chờ bạn trả lời. Mở hộp thư để trả lời."
JOB_RESULT_TITLE = "Job có kết quả mới"
JOB_RESULT_BODY = "Một lịch vừa chạy xong và có điều cần báo. Mở hộp thư để đọc."
JOB_FAILED_TITLE = "Job gặp lỗi"
JOB_FAILED_BODY = "Một lịch vừa chạy hỏng. Mở hộp thư để xem."
REPLY_TITLE = "Có trả lời mới"
REPLY_BODY = "Agent đã làm xong việc bạn giao. Mở để đọc."
TEST_TITLE = "Thông báo đã bật"
TEST_BODY = "Thiết bị này sẽ nhận tin khi có việc cần bạn."
