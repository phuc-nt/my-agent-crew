"""Strings of the browser tools: the words that make an action stop for a person, what the
tools say of themselves and what they answer when they refuse."""

# A click, a key or a choice on an element named with one of these stops for a person, in an
# autonomous conversation too. Whole words, any case; a name written without accents is
# matched too. `browser_ask_patterns` in `config.yaml` replaces the list.
DEFAULT_ASK_WORDS = (
    "mua",
    "thanh toán",
    "đặt hàng",
    "đặt mua",
    "gửi",
    "xoá",
    "xóa",
    "huỷ đơn",
    "hủy đơn",
    "xác nhận",
    "đồng ý",
    "chuyển khoản",
    "chuyển tiền",
    "đăng xuất",
    "pay",
    "buy",
    "purchase",
    "order",
    "checkout",
    "check out",
    "submit",
    "send",
    "delete",
    "remove",
    "confirm",
    "agree",
    "transfer",
    "publish",
    "post",
    "log out",
    "logout",
    "sign out",
)

# Refusals of a page address, before any tab is opened.
URL_SCHEME = "Trình duyệt chỉ mở địa chỉ http và https đầy đủ, ví dụ https://shop.example/don-hang."
URL_UNREACHABLE = "Không phân giải được tên máy chủ {host}: {error}"
URL_PRIVATE = (
    "Từ chối mở {host}: đó là địa chỉ nội bộ (máy này, mạng riêng hoặc mạng nội bộ). Trình duyệt "
    "của đội chỉ tới địa chỉ công khai, và không cấu hình nào bật được việc này."
)
