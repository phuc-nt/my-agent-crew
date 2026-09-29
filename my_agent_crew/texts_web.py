"""Strings of the web tools, `fetch_url` and `web_search`. Re-exported through `texts`."""

URL_SCHEME = "Chỉ hỗ trợ http và https."
URL_PRIVATE = "Từ chối truy cập địa chỉ nội bộ."
URL_REDIRECT = "Trang chuyển hướng tới: {location}"
URL_UNREACHABLE = "Không tới được trang: {error}"
URL_STATUS = "Trang trả về HTTP {status}."
URL_ACCEPTED_NOT_READY = (
    "Máy chủ đã nhận yêu cầu (HTTP 202) nhưng chưa có kết quả để đọc. Thử lại sau hoặc tìm "
    "nguồn khác."
)
URL_EMPTY_BODY = (
    "Trang không có chữ nào đọc được (thân rỗng, hoặc nội dung chỉ dựng bằng JavaScript). "
    "Tìm nguồn khác."
)

SEARCH_UNREACHABLE = "Không tới được dịch vụ tìm kiếm: {error}"
SEARCH_EMPTY = "Không có kết quả cho: {query}"
