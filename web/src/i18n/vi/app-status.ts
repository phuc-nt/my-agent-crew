export const viAppStatus = {
  crashed: "Giao diện gặp lỗi không mong đợi.",
  reload: "Tải lại",
  // The server runs a newer build than this page: loading again picks it up.
  updateAvailable: "Có bản mới",
  updateReloadLabel: "Tải lại để dùng bản mới",
  updateDismissLabel: "Để sau, ẩn thông báo bản mới",
  statusIdle: "Sẵn sàng",
  statusOverBudget: "Đã khoá vì hết ngân sách",
  statusStreaming: "Agent đang trả lời…",
  statusThinking: "Agent đang suy nghĩ…",
  statusTool: (tool: string) => `Đang chạy công cụ ${tool}…`,
  statusAwaiting: "Đang chờ bạn duyệt",
} as const;
