---
name: test
description: Chọn test nào phải chạy theo diff, và viết test thật sự bắt được lỗi.
---
## Chạy test nào

Xem diff trước (`git diff --stat`), rồi chọn theo mức lan:

| Diff đụng vào | Chạy |
|---|---|
| Một tệp, không đổi chữ ký hàm | test của tệp đó |
| Nhiều tệp trong một module | test của module |
| Hàm/kiểu công khai, schema, cấu hình | toàn bộ suite |
| Không chắc lan tới đâu | toàn bộ suite |

Chạy hẹp mà xanh nhưng diff có đổi hợp đồng dùng chung thì **vẫn phải** chạy rộng.
Rẻ hơn nhiều so với một hồi quy lọt lưới.

## Viết test

- Một test một hành vi, tên test nói rõ hành vi đó: đọc tên là biết cái gì hỏng.
- Test phải **hỏng được**: thử sửa ngược mã cho sai, test phải đỏ. Test luôn xanh là test vô dụng.
- Kiểm hành vi nhìn thấy được, đừng kiểm chi tiết bên trong — nếu không mỗi lần dọn mã là
  một lần sửa test.
- Trường hợp biên: rỗng, một phần tử, rất nhiều, `None`, âm, unicode, gọi lại lần hai.
- Không đặt mã plan, số phase hay nhãn audit vào tên test; mô tả hành vi thôi.

## Báo cáo

Số test chạy / xanh / đỏ. Mỗi test đỏ: tên, dòng lỗi, nguyên nhân một câu.
Nói rõ phần nào của diff **không** có test nào chạm tới.
