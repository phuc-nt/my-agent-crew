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
  // Over the chat: the requests of the agents this conversation handed work to, decided here.
  attentionDelegated: "Việc đã giao đang chờ bạn",
  attentionFailedElsewhere: (n: number) => `${n} lỗi hoặc dừng chưa xem ở mục Hoạt động`,
  // A memory rewrite the gate held: it waits on the person as much as an approval does.
  attentionProposals: (n: number) => `${n} đề xuất trí nhớ chờ bạn duyệt ở mục Trí nhớ`,
  // A row that stands for every failure in a row of the same job.
  attentionRepeats: (n: number) => `${n} lần liên tiếp`,
  attentionSeenAll: (n: number) => `Đã xem cả ${n}`,
} as const;
