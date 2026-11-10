// What each model provider has cost, on the header pill and the card it opens.
export const viSpend = {
  spend: {
    title: "Chi phí model",
    // The pill's hover: the figures are this month's.
    pillHint: "Chi phí model tháng này. Bấm để xem chi tiết.",
    providers: { anthropic: "Claude", openrouter: "OpenRouter" } as Record<string, string>,
    month: (month: string) => `Tháng ${month.slice(5)}/${month.slice(0, 4)}`,
    today: (usd: string) => `Hôm nay ${usd}`,
    unpriced: (n: number) => `${n} lượt chưa có giá`,
    // OpenRouter's own count for the key, which also includes calls made outside the crew.
    routerReported: "OpenRouter · cả key",
    routerReportedSub: (today: string, week: string) => `Hôm nay ${today} · tuần ${week} (giờ UTC)`,
    routerLeft: (left: string, limit: string) => `Còn ${left} / hạn mức ${limit}`,
    routerNoLimit: "Key không đặt hạn mức",
    routerUnread: "Chưa đọc được số liệu từ OpenRouter.",
    // Beside OpenRouter's own count: the part this crew made and wrote down.
    ledger: "crew ghi",
    // Why Claude's figure is the crew's own: the API has no balance a normal key can read.
    claudeNote:
      "Số của Claude do crew tự tính từ token mỗi lượt gọi. API key thường không đọc được số dư credit; xem số dư trong Claude Console.",
  },
};
