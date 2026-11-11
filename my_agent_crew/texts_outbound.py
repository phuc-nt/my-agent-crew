"""Strings of the two guards on what an agent sends out by itself: a shell command that
reaches another machine, and a page address the agent put together."""

SHELL_HOST_UNLISTED = (
    "lệnh gửi dữ liệu ra máy chủ `{host}`, nằm ngoài danh sách outbound_hosts của agent"
)
SHELL_HOST_UNREAD = (
    "lệnh chạy chương trình mạng mà không đọc được máy chủ đích (địa chỉ nằm trong biến, "
    "hoặc viết thiếu http://, https://)"
)
FETCH_COMPOSED = (
    "Tải một địa chỉ do agent tự ghép ở máy chủ `{host}`: địa chỉ này không có nguyên văn "
    "trong tin nhắn của chủ hay trong kết quả tìm kiếm, trang web của cuộc trò chuyện, và máy "
    "chủ nằm ngoài danh sách outbound_hosts của agent."
)
