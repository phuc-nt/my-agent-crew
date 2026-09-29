"""Strings for a run written out as a file, split out of `texts` so neither file outgrows its
budget. Import them from `my_agent_crew.texts`, which re-exports every name here."""

TRAJECTORY_REDACTED = "[đã che]"
TRAJECTORY_CUT = "\n…[đã cắt: kết quả dài {total} ký tự, tải bản đầy đủ để xem hết]"
TRAJECTORY_NOTICE = (
    "Bản xuất này có cả tham số và kết quả của mọi công cụ, nên có thể chứa dữ liệu cá nhân. "
    "Khoá và mật khẩu được che theo giá trị và theo dạng quen thuộc, không bảo đảm che hết: "
    "đọc lại trước khi dán ra ngoài."
)
TRAJECTORY_TITLE = "# Lượt chạy: {title}"
TRAJECTORY_FACT_LABELS = {
    "id": "Mã",
    "agent_id": "Agent",
    "source": "Nguồn",
    "status": "Trạng thái",
    "summary": "Kết quả",
    "started_at": "Bắt đầu",
    "finished_at": "Kết thúc",
    "steps": "Số bước",
    "spent_usd": "Chi phí",
    "conversation_id": "Hội thoại",
    "slice": "Tin nhắn lấy",
}
TRAJECTORY_UNKNOWN_COST = " (thêm {count} lời gọi không rõ giá)"
TRAJECTORY_SLICES = {
    "by_seq": "đúng các tin của lượt chạy này",
    "by_time": (
        "theo thời gian, vì lượt chạy ghi trước khi có mốc tin; có thể lẫn tin của lượt sát bên"
    ),
    "none": "lượt chạy không gắn với hội thoại nào, chỉ có bản ghi và các bước",
}
TRAJECTORY_MESSAGES = "## Tin nhắn"
TRAJECTORY_NO_MESSAGES = "Không có tin nhắn nào."
TRAJECTORY_STEPS = "## Các bước"
TRAJECTORY_CHILD = "## Agent con {agent} · hội thoại `{conversation}` · lời gọi `{call}`"
TRAJECTORY_ROLES = {
    "user": "người dùng",
    "assistant": "agent",
    "tool": "kết quả",
    "system": "hệ thống",
}
TRAJECTORY_CALL = "Gọi `{name}`:"
