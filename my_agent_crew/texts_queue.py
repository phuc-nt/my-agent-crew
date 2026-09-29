"""Strings for a message that arrives while its conversation is busy, split out of `texts` so
neither file outgrows its budget. Import them from `my_agent_crew.texts`, which re-exports
every name here."""

# Told to the sender at once, in place of an answer that has not been written yet.
QUEUED_FOLLOW_UP = "Đã xếp hàng: tin này sẽ chạy ngay sau khi lượt hiện tại xong."
QUEUED_STEER = "Đã nhận: tin này sẽ được chèn vào lượt đang chạy ở bước kế tiếp."
STEER_NEEDS_TEXT = "Lệnh /steer cần kèm nội dung, ví dụ: /steer tập trung vào phần chi phí."
QUEUE_FULL = (
    "Hàng chờ của cuộc trò chuyện này đã đủ {limit} tin. Đợi lượt hiện tại xong rồi gửi tiếp."
)
# The result a tool call gets when its turn stopped between the call and its result: the
# process restarted or the turn was cancelled. Nobody knows whether the tool ran, so the model
# is told to look before it acts again.
INTERRUPTED_TOOL = (
    "Lời gọi này bị ngắt giữa chừng: không rõ nó đã chạy hay chưa. Nếu vẫn cần, hãy kiểm tra "
    "trước rồi mới gọi lại."
)
