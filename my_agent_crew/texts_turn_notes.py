"""Strings of the memory block a turn reads in front of the message that opens it
(`agent/turn_notes.py`). Imported from here rather than through `texts`, which is at its
line budget."""

# The frame says whose words these are: the block sits beside what the person wrote, and
# must not be read as theirs.
TURN_NOTES_OPEN = "[Bộ nhớ của bạn — hệ thống chèn trước tin này, không phải lời người dùng]"
TURN_NOTES_CLOSE = "[Hết phần bộ nhớ]"
# One heading for each way a section is told: in whole the first time, only the lines added
# since, the new text of one that was rewritten, and one that is no longer there.
TURN_NOTES_WHOLE = "## {title}"
TURN_NOTES_ADDED = "## {title} — phần mới thêm từ lần đọc trước"
TURN_NOTES_REPLACED = "## {title} — bản mới, thay cho bản đã đọc ở trên"
TURN_NOTES_GONE = "## {title} — nay đã trống, bỏ qua bản đã đọc ở trên"
