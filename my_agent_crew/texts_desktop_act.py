"""Vietnamese strings of `computer_act`: what the model reads back of a call, and what a person
reads on its approval card."""

# computer_act: a call that is not carried out, and what to do instead.
ACT_KIND = "Không có thao tác «{kind}». Các thao tác: {kinds}."
ACT_NEEDS = "Thao tác {kind} cần tham số `{what}`."
ACT_NO_APP = "computer_act cần tham số `app`: ứng dụng sẽ nhận thao tác."
ACT_NO_FRAME = (
    "Từ chối: thao tác {kind} cần `frame_id` của lần computer_screenshot gần nhất, để chắc "
    "rằng bạn đang thao tác trên màn hình bạn đã nhìn. Gọi computer_screenshot trước."
)
ACT_REF_OR_POINT = "Thao tác {kind} cần hoặc `ref`, hoặc cả `x` và `y`, không cả hai."
ACT_NUMBER = "Tham số `{what}` của thao tác {kind} phải là một số không âm."
ACT_OUTSIDE = (
    "Từ chối: `{what}` của thao tác {kind} nằm ngoài ảnh mang frame_id đó, vốn rộng {width} và "
    "cao {height} điểm ảnh. Toạ độ đếm từ 0, theo điểm ảnh của ảnh chụp."
)
ACT_WHOLE = "Tham số `{what}` của scroll phải là số nguyên từ -50 tới 50, và không cùng bằng 0."
ACT_TEXT_LONG = "Chữ của thao tác {kind} dài hơn {limit} ký tự nên không gửi. Rút ngắn lại."
ACT_KEYS = (
    "Không đọc được tổ hợp phím «{keys}». Viết các phím giữ nối bằng dấu + rồi tới một phím, "
    "ví dụ cmd+s, shift+tab, enter. Phím giữ: cmd, shift, opt, ctrl, fn."
)
ACT_KEYS_NEVER = (
    "Từ chối: tổ hợp phím {keys} thoát ứng dụng, đổ thùng rác, khoá máy hoặc buộc thoát. Không "
    "bao giờ được gửi và không cấu hình nào bật được."
)
ACT_KEYS_SPOTLIGHT = (
    "Từ chối: {keys} mở Spotlight, nơi mở được mọi thứ trên máy. Chỉ gửi được khi chủ máy thêm "
    "Spotlight vào computer_apps của agent này."
)
ACT_TEXT_SUDO = "Từ chối: chữ cần gõ có lệnh sudo. Không gõ lệnh chạy bằng quyền quản trị."
ACT_TEXT_RM = "Từ chối: chữ cần gõ có lệnh rm xoá cả thư mục không hỏi lại (rm -rf)."
ACT_TEXT_PIPE = "Từ chối: chữ cần gõ tải một thứ từ mạng về rồi đưa thẳng cho shell chạy."
ACT_SECURE_REF = (
    "Từ chối: {ref} là ô bảo mật (mật khẩu). Không gõ vào đó và không cấu hình nào bật được: "
    "nhập mật khẩu là việc của chủ máy. Hãy báo cho chủ biết ứng dụng đang cần gì."
)
ACT_POSTED = (
    "Đã gửi thao tác {kind} tới {app}. Chưa biết kết quả: gọi computer_screenshot hoặc "
    "computer_observe để xem màn hình lúc này trước khi làm bước kế tiếp."
)
ACT_SET = "Đã đặt nội dung của {ref} trong {app}."
ACT_FOCUSED = "{app} đã lên trước. Gọi computer_screenshot để lấy frame_id mới."
ACT_FRONT_LEFT = (
    "Sau thao tác, ứng dụng ở trước là một ứng dụng ngoài danh sách của agent này: không chụp "
    "và không thao tác được trên nó."
)

# Why a call stops for a person: shown on the approval card as written.
ASK_FOCUS = "Đưa ứng dụng {app} lên trước màn hình của máy."
ASK_KEYS = "Gửi tổ hợp phím {keys} tới {app}: tổ hợp này nằm ngoài nhóm phím thường dùng."
ASK_WORD = "Gõ vào {app} một đoạn có chữ «{word}», là việc phải hỏi chủ."
