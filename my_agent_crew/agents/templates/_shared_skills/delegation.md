---
name: delegation
description: Cách giao việc cho agent khác và cách kết thúc một việc được giao.
always: true
---
## Khi được giao việc

Cuộc hội thoại này bắt đầu trống: không thấy gì từ bên giao ngoài đoạn mô tả việc.
Đừng đoán phần thiếu — nếu thiếu thông tin để làm đúng, dừng và nói thiếu gì.

Kết thúc câu trả lời bằng đúng khối này:

```
Status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
Summary: 1–2 câu
Concerns/Blockers: (bỏ trống nếu không có)
```

- `DONE` — làm xong, đã tự kiểm.
- `DONE_WITH_CONCERNS` — xong nhưng có điều bên giao cần biết.
- `BLOCKED` — không làm được; nói rõ vướng gì.
- `NEEDS_CONTEXT` — thiếu thông tin; nói rõ cần gì.

## Khi giao việc

Mỗi lần gọi `delegate` phải nói đủ, vì bên kia không thấy gì khác:

1. Việc cần làm, một câu.
2. Tệp cần đọc (đường dẫn cụ thể, không "tìm quanh repo").
3. Tệp được phép sửa — và chỉ những tệp đó.
4. Thế nào là xong (acceptance).
5. Ràng buộc: quy ước, thư viện, tương thích ngược.
6. Nơi ghi báo cáo, nếu cần.

Quy tắc:

- Không hai người cùng sửa một tệp. Chia theo tệp, không theo "phần".
- Việc độc lập thì gọi nhiều `delegate` trong cùng một lượt để chúng chạy song song.
- Nhận `BLOCKED` hay `NEEDS_CONTEXT` thì đổi ngữ cảnh hoặc đổi cách chia việc — đừng gửi lại
  đúng lời nhắn cũ.
- Người được giao không giao tiếp được nữa; đừng nhờ họ nhờ người khác.
- Việc sửa dưới mười dòng thì tự làm, gọi người khác còn tốn hơn.
