---
name: code-review
description: "Checklist soát mã: lỗi thật trước, xếp hạng theo hậu quả, không bàn thẩm mỹ."
---
Soát **diff**, không soát cả repo. Bắt đầu bằng `git diff` (hoặc `git diff --stat` rồi
đọc từng tệp). Không sửa mã — chỉ nói ra.

## Xếp hạng

| Mức | Nghĩa |
|---|---|
| Critical | Mất dữ liệu, lộ bí mật, sập khi chạy thật, lỗ hổng bảo mật |
| High | Sai logic ở luồng chính, hỏng hợp đồng công khai, mất tương thích ngược |
| Medium | Sai ở nhánh hiếm, thiếu xử lý lỗi, thiếu test cho hành vi mới |
| Low | Đặt tên, trùng lặp nhỏ, comment lạc hậu |

Mỗi phát hiện phải có: `file:line`, chuyện gì hỏng, **đầu vào cụ thể nào** làm nó hỏng.
Không nêu được tình huống hỏng thì đó không phải phát hiện — bỏ đi.

## Cần soi

- **Đúng sai**: điều kiện biên, off-by-one, `None`/rỗng, phép so sánh ngược, `await` thiếu.
- **Lỗi**: lỗi bị nuốt, `except` trống, lỗi trả về khác lỗi ném ra.
- **Đồng thời**: trạng thái dùng chung, thứ tự không bảo đảm, ghi đè nhau khi chạy song song.
- **Bảo mật**: dữ liệu người dùng đi thẳng vào truy vấn/lệnh/đường dẫn; bí mật vào log hay repo.
- **Hợp đồng**: đổi chữ ký hàm, kiểu xuất, cột DB, biến môi trường — ai đang gọi?
- **Test**: hành vi mới có test không; test có thật sự hỏng khi mã sai không.
- **Đơn giản hoá**: chỗ nào ngắn lại được mà không mất gì — đề xuất, đừng ép.

## Riêng với mã do mô hình viết

- Hàm gọi "nghe hợp lý" nhưng không tồn tại — kiểm bằng grep.
- Test viết sao cho luôn xanh (khẳng định điều hiển nhiên đúng).
- Lớp trừu tượng cho một chỗ dùng duy nhất.
- Xử lý trường hợp mà mã còn lại không hề gặp.

## Báo cáo

Nhóm theo mức, nặng trước. Cuối cùng: những gì đã kiểm và thấy ổn, rồi câu hỏi còn treo.
