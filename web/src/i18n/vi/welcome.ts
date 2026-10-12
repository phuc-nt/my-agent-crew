export const viWelcome = {
  welcomeTitleFor: (name: string) => `Xin chào! Tôi là ${name} — trợ lý đa năng của bạn.`,
  welcomeBody:
    "Tôi có thể đọc/ghi tệp trong thư mục làm việc, tải trang web, tìm kiếm, chạy lệnh và ghi nhớ. " +
    "Mọi thao tác thay đổi dữ liệu đều hỏi bạn trước.",
  welcomeCrew: (names: string[]) =>
    `Việc cần chuyên môn tôi sẽ giao cho đội: ${names.join(", ")}.`,
  welcomeNoCrew: "Chưa có ai trong đội — mở tab Đội để cài thêm thành viên từ mẫu có sẵn.",
  welcomeSuggestions: [
    "Liệt kê các tệp trong thư mục làm việc",
    "Tóm tắt trang https://example.com",
    "Ghi nhớ: tôi thích trả lời ngắn gọn",
  ],
  welcomeDelegateSuggestion: (name: string) => `Giao cho ${name}: rà soát thư mục làm việc và báo cáo`,
  echoHint: "Đang chạy tuyến fake:echo — gõ /tool <tên> {json} để gọi công cụ trực tiếp.",
} as const;
