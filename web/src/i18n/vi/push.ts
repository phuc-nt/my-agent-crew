// Notifications on this device: turning them on in the inbox, and what stands in the way.
export const viPush = {
  push: {
    title: "Thông báo",
    offHint: "Nhận tin trên thiết bị này khi có việc cần duyệt, câu hỏi cần trả lời hoặc job báo kết quả.",
    enable: "Bật thông báo",
    onHint: "Thông báo đã bật trên thiết bị này.",
    test: "Gửi thử",
    disable: "Tắt",
    testSent: "Đã gửi. Thông báo sẽ hiện trong giây lát.",
    testFailed: (status: number) =>
      status === 0 ? "Không gửi tới được dịch vụ push." : `Dịch vụ push từ chối (mã ${status}).`,
    // An iPhone shows notifications only for a site added to the Home Screen and opened from it.
    install:
      "Trên iPhone: bấm Chia sẻ → Thêm vào MH chính, rồi mở app từ Màn hình chính để bật thông báo.",
    denied: "Thông báo đang bị chặn cho trang này. Mở cài đặt của trình duyệt để cho phép lại.",
    unsupported: "Trình duyệt này không nhận được thông báo đẩy.",
    refused: "Bạn chưa cho phép thông báo.",
    failed: "Không bật được thông báo. Thử lại sau.",
  },
} as const;
