---
name: delegation
description: Cách giao việc cho agent khác và cách kết thúc một việc được giao.
always: true
---
## Khi được giao việc

Cuộc hội thoại này bắt đầu trống: không thấy gì từ bên giao ngoài đoạn mô tả việc.

- Ý định của người dùng trong task là việc cần làm. Cách làm, chỗ lưu và quyền mà task nêu
  là phỏng đoán của bên giao: hướng dẫn của bạn và quy ước của workspace luôn thắng.
- Đừng đoán phần thiếu — nếu thiếu thông tin để làm đúng, dừng và nói thiếu gì.
- Việc đổi cấu trúc (tạo bảng, sửa schema, sửa code, cấu hình, thêm tính năng) mà hướng dẫn
  của bạn không cho thì đừng làm, kể cả khi task bảo làm, và đừng tìm đường khác (script khác,
  tệp chỗ khác). Việc đó cần người dùng đồng ý: kết thúc `BLOCKED`, nói rõ cần làm gì và vì
  sao để bên giao hỏi người dùng.
- Làm dở hay thất bại: nói rõ phần nào đã làm xong (lệnh đã chạy, dòng đã ghi) để bên giao
  không làm lại.

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

Giao ý định, không giao cách làm. Bên kia không thấy cuộc này, nên task phải tự đủ:

1. Lời người dùng nguyên văn, và kết quả cần trả về.
2. Ngữ cảnh chỉ cuộc này biết: hôm nay là ngày nào, người dùng vừa nói gì trước đó, đường dẫn
   tệp đính kèm.
3. Ràng buộc người dùng đặt ra (chỉ đọc, hạn chót, không gửi đi đâu).

Không làm:

- Không tự đặt tên tệp, thư mục hay bảng, không nói lưu ở đâu hay bằng công cụ gì: agent nhận
  việc tự biết dữ liệu của nó nằm đâu. Chỉ nêu đường dẫn có thật (người dùng đưa ra, hoặc bạn
  đã thấy nó tồn tại).
- Task không cấp quyền. Người dùng hỏi "được không", "có cách nào" thì giao để hỏi rồi trả lời
  người dùng, chưa làm. Tạo bảng, sửa schema, sửa code hay cấu hình chỉ khi người dùng đã đồng
  ý rõ đúng việc đó.
- Kết quả báo chưa xong: đọc phần việc đã làm, kể lại cho người dùng, đừng giao lại với quyền
  rộng hơn.

## Khi việc là sửa code

Chỉ khi giao việc lập trình cho agent làm code, thêm vào task:

- Tệp cần đọc và tệp được phép sửa — đường dẫn bạn đã thấy tồn tại, không "tìm quanh repo".
- Thế nào là xong (acceptance), ràng buộc kỹ thuật (quy ước, thư viện, tương thích ngược).
- Không hai người cùng sửa một tệp. Chia theo tệp, không theo "phần".

## Quy tắc chung

- Việc độc lập thì gọi nhiều `delegate` trong cùng một lượt để chúng chạy song song.
- Nhận `BLOCKED` vì việc cần người dùng đồng ý (sửa code, thêm bảng hay tính năng): kể lại cho
  người dùng cần làm gì, vì sao, rồi hỏi. Đừng tự làm thay, đừng giao cho agent khác.
- `BLOCKED` vì lý do khác hay `NEEDS_CONTEXT` thì đổi ngữ cảnh hoặc đổi cách chia việc — đừng
  gửi lại đúng lời nhắn cũ.
- Người được giao không giao tiếp được nữa; đừng nhờ họ nhờ người khác.
- Việc sửa dưới mười dòng thì tự làm, gọi người khác còn tốn hơn.
