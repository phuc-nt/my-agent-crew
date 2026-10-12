export const viAttention = {
  attention: "Cần bạn xử lý",
  attentionEmpty: "Không có gì cần xử lý.",
  attentionAwaiting: (agent: string) => `${agent} đang chờ bạn duyệt`,
  // A question is not a permission request. "chờ bạn duyệt" would send the person looking
  // for Cho phép / Từ chối, which the server refuses on a question row.
  attentionAsking: (agent: string) => `${agent} đang hỏi bạn`,
  attentionFailed: (agent: string) => `${agent} gặp lỗi`,
  attentionHalted: (agent: string) => `${agent} đã dừng giữa chừng`,
  // A failure stays listed until the person says they have read it, not until it scrolls away.
  attentionSeen: "Đã xem",
  attentionSeenLabel: (what: string) => `Đã xem: ${what}`,
  attentionLoading: "Đang tải yêu cầu…",
  attentionResuming: "Đang chạy tiếp…",
  // A 409 on decide or answer: another tab, Telegram or the expiry sweep closed it first.
  // That is not the conversation being busy, which is what the chat's conflict text says.
  attentionHandled: "Đã được xử lý hoặc đã hết hạn",
  attentionExpiresIn: (clock: string) => `còn ${clock}`,
  attentionExpired: "Đã hết hạn",
  attentionWaitingElsewhere: (n: number) => `${n} việc đang chờ bạn ở mục Duyệt`,
  attentionFailedElsewhere: (n: number) => `${n} lỗi hoặc dừng chưa xem ở mục Hoạt động`,
} as const;
