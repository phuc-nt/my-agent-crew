---
name: debug
description: Tìm nguyên nhân gốc bằng bằng chứng thay vì đoán rồi sửa thử.
---
Quy tắc đầu tiên: **không sửa gì trước khi chứng minh được nguyên nhân.** Sửa theo linh cảm
hay làm hỏng thêm, hoặc che triệu chứng và lỗi quay lại chỗ khác.

## Trình tự

1. **Tái hiện.** Lệnh nào, đầu vào nào, kết quả mong đợi là gì, thực tế ra gì. Không tái hiện
   được thì việc đầu tiên là tìm cách tái hiện, chưa phải tìm lỗi.
2. **Thu bằng chứng.** Thông báo lỗi đầy đủ, traceback, log quanh thời điểm đó, giá trị thật
   của biến ở chỗ nghi ngờ.
3. **Hai đến ba giả thuyết.** Viết ra. Một giả thuyết thì chỉ là đoán và sẽ tự bênh nó.
4. **Loại trừ.** Mỗi giả thuyết tìm một phép thử cho kết quả khác nhau tuỳ đúng hay sai.
   In giá trị ra, chạy thử một đoạn nhỏ, sửa ngược cho lỗi biến mất rồi trả lại.
5. **Nguyên nhân gốc.** Chuỗi: đầu vào này → đi qua đây → chỗ này sai → nên thấy thế kia.
   Còn đứt đoạn thì chưa xong.
6. **Sửa nhỏ nhất.** Sửa đúng nguyên nhân, không nhân tiện dọn dẹp quanh đó.
7. **Chứng minh đã sửa.** Chạy lại đúng bước tái hiện, và chạy test của vùng vừa đụng.

## Bẫy quen

- Sửa chỗ triệu chứng hiện ra, không phải chỗ sinh ra nó.
- Lỗi chập chờn: thường là thứ tự, trạng thái dùng chung, hoặc thời gian — không phải "máy lạ".
- Sửa xong lỗi vẫn còn nhưng khác đi — nghĩa là có hai lỗi, đừng gộp làm một.
- "Trên máy tôi chạy được": so phiên bản, biến môi trường, thư mục làm việc.

## Báo cáo

Triệu chứng · Cách tái hiện · Giả thuyết đã loại và vì sao · Nguyên nhân gốc kèm `file:line` ·
Đã sửa gì · Đã chứng minh thế nào · Còn gì chưa chắc.
