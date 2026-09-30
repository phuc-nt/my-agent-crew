"""Strings for "Sửa và gửi lại từ đây" (rewind and fork a conversation), split out of
`texts` so neither file outgrows its budget. Import them from `my_agent_crew.texts`, which
re-exports every name here."""

FORK_TITLE_SUFFIX = "(nhánh)"
# Closes a tool call the fork copied still open, without running it: running it now would
# act on the branch's own state with none of the approvals or context the original turn
# had, and the model would not even know it happened a second time.
FORK_CALL_NOT_RUN = (
    "Lệnh này chưa chạy vì hội thoại đã được rẽ nhánh trước khi nó kết thúc. Gọi lại nếu vẫn cần."
)
