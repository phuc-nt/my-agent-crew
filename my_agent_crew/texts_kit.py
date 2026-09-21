"""Strings for the harness kits (`.agents/`, `.claude/`, `.opencode/`): commands the
person types, hooks around tools, agents read from markdown."""

TOOL_BLOCKED_BY_HOOK = "Hook chặn {name}: {reason}"
TOOL_HOOK_NOTE = "\n\n[hook] {note}"
HOOK_BLOCKED_NO_REASON = "hook trả mã 2 mà không nêu lý do"
KIT_COMMAND_NO_DESCRIPTION = "Lệnh từ kit."
KIT_COMMANDS_SECTION_TITLE = "Lệnh có sẵn"
KIT_COMMANDS_INTRO = (
    "Người dùng có thể gõ `/tên đối số`; máy chủ đã thay lệnh bằng nội dung của nó trước khi "
    "bạn đọc, nên bạn chỉ thấy phần nội dung. Danh sách để bạn gợi ý khi phù hợp:"
)
KIT_COMMAND_LINE = "- /{name} — {description}"
