"""The words about the window a person signs in through on an agent's browser, in the owner's
language. All but the first are read by the person who asked for the window."""

# What a browser tool answers a model while the window is open.
LOGIN_OPEN = (
    "Lúc này không dùng được trình duyệt: chủ đang mở cửa sổ đăng nhập trên chính hồ sơ trình "
    "duyệt của agent này. Cửa sổ đóng khi chủ bấm Xong, hoặc tự đóng sau một lúc; khi đó gọi lại "
    "browser_navigate, các tab cũ không còn."
)

# Why no window is opened.
LOGIN_OFF = (
    "Agent này không có trình duyệt: chưa bật cho agent, hoặc máy chưa bật hay chưa cài trình "
    "duyệt. Không có hồ sơ nào để đăng nhập."
)
LOGIN_NO_CONSOLE = (
    "Máy chủ của đội không chạy trong phiên màn hình nào đang mở, nên không có chỗ để hiện cửa sổ."
)
LOGIN_LOCKED = "Màn hình của máy đang khoá. Mở khoá rồi bấm lại."
LOGIN_BUSY = (
    "Agent đang dùng trình duyệt cho một lần gọi. Chờ lần gọi đó xong rồi bấm lại, hoặc dừng "
    "trình duyệt trước."
)
LOGIN_STOPPING = "Máy chủ của đội đang dừng nên không mở cửa sổ nào nữa. Bấm lại khi nó chạy lại."
LOGIN_FAILED = "Không mở được cửa sổ trình duyệt: {error}"
