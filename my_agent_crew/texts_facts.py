"""Texts of the shared facts about the person: what the tools say back and how the model
is told to use them."""

USER_MEMORY_BASIS_DESCRIPTION = (
    "said: người dùng nói hoặc xác nhận trực tiếp; inferred: bạn tự suy ra (từ mail, dữ"
    " liệu, ngữ cảnh). Điều suy ra không ghi đè được điều người dùng đã nói: nó thành đề"
    " xuất chờ người dùng duyệt."
)
USER_MEMORY_VALID_FROM = (
    "YYYY-MM-DD, ngày bắt đầu đúng, khi điều này chỉ đúng từ một ngày sau hôm nay"
    " (vd. đổi công ty từ 1/12). Bản cũ vẫn là bản đúng tới hôm trước, nên body chỉ"
    " nói điều đúng từ ngày đó, không chép lại bản cũ."
)
USER_MEMORY_VALID_UNTIL = "YYYY-MM-DD, ngày cuối còn đúng, khi đã biết (vd. chuyến đi)."
USER_MEMORY_CREATED = "Đã ghi nhớ mới về người dùng: {name} (phiên bản 1)."
USER_MEMORY_CONFIRMED = "Ghi nhớ {name} không đổi; đã thêm bằng chứng (phiên bản {version})."
USER_MEMORY_SUPERSEDED = (
    "Đã cập nhật ghi nhớ {name} lên phiên bản {version}; bản cũ giữ trong lịch sử."
)
USER_MEMORY_DISPUTED = (
    "Không ghi đè {name}: bản hiện có do {held}, còn đây là điều agent suy ra. Đã đề xuất"
    " cho người dùng duyệt; trong lúc chờ, vẫn dùng bản hiện có."
)
USER_MEMORY_DISPUTE_REASON = (
    "Agent suy ra điều này, trái với bản hiện có do {held} (phiên bản {version}); bản đó"
    " vẫn được dùng cho tới khi bạn duyệt."
)
USER_MEMORY_RETRACTED = (
    "Đã rút lại ghi nhớ {name}: không còn trong prompt, lịch sử vẫn giữ (người dùng xoá hẳn"
    " được trên web)."
)
USER_MEMORY_GET_DESCRIPTION = (
    "Đọc đầy đủ một ghi nhớ về người dùng theo tên trong danh mục: nội dung, ai đứng sau"
    " (người dùng nói / agent suy ra), hiệu lực từ-đến, nguồn, và lịch sử các phiên bản."
    " as_of=YYYY-MM-DD để hỏi điều gì đúng vào ngày đó."
)
USER_MEMORY_AS_OF = "YYYY-MM-DD; bỏ trống là hôm nay."
USER_MEMORY_NOTHING_ON = "Không có phiên bản nào của {name} đúng vào {day}."
USER_MEMORY_FACTS_HINT = (
    "Mỗi dòng: mô tả · loại · ai đứng sau. Đọc đủ nội dung, nguồn, lịch sử bằng user_memory_get."
)
