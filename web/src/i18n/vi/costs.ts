export const viCosts = {
  costs: "Chi phí",
  costTotal: "Tổng chi",
  costRuns: "Lượt chạy",
  costModelCalls: "Lượt gọi model",
  costByAgent: "Theo agent",
  costByModel: "Theo model",
  costByDay: "Theo ngày",
  costLastDays: "7 ngày gần đây",
  costModels: "Theo model",
  costPurposes: "Theo mục đích",
  costPurposeHeader: "Mục đích",
  // What a call was for. `chat` is every turn's own calls — a scheduled job or a delegated
  // task runs in a conversation too; the rest were made beside a turn.
  costPurpose: {
    chat: "Trò chuyện",
    title: "Đặt tên cuộc trò chuyện",
    session_summary: "Tóm tắt phiên",
    tool_summary: "Tóm tắt kết quả công cụ",
    image: "Đọc ảnh",
    pdf: "Đọc PDF scan",
    transcribe: "Chép lời",
    consolidate: "Cô đọng bộ nhớ",
    wiki: "Dựng wiki",
    // A model a script asked on its own, to sort a text or to shorten one.
    script: "Script gọi model",
  } as Record<string, string>,
  // Model calls, said as such: a bare "lượt" is how this page counts runs.
  costCalls: (n: number) => `${n} lượt gọi`,
  // Given already shortened ("1.2M"), the way the cache beside them is written.
  tokens: (prompt: string, completion: string) => `${prompt} vào / ${completion} ra`,
  tokensHeader: "token vào / ra",
  // How much of the prompt the provider served from its cache: a drop after a persona
  // edit is the sign the edit broke caching.
  cacheHeader: "cache",
  cacheShare: (percent: number) => `${percent}% cache`,
  costToday: "Hôm nay",
  costWeek: "7 ngày",
  // What a figure is counted over, said beside it rather than left to guess.
  costWindowRecent: (runs: number) => `${runs} lượt gần nhất`,
  costWindowAll: "Toàn bộ",
  costCacheByAgent: "Cache theo agent",
  costPromptTokens: "token vào",
  costNoTokens: "Chưa lượt gọi nào báo số token.",
  // The calls did report their tokens; only the cached part went unsaid.
  costNoCacheFigure: "Chưa lượt gọi nào báo số token cache.",
  costEmpty: "Chưa có chi phí nào được ghi nhận.",
} as const;
