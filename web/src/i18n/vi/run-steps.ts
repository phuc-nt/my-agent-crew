export const viRunSteps = {
  /** "chat" / "telegram" / "api" / "job:<id>" / "delegate:<conversation>" → a label. */
  runSource: (source: string) => {
    if (source === "chat") return "trò chuyện";
    if (source === "telegram") return "Telegram";
    if (source === "api") return "API";
    if (source.startsWith("delegate:")) return "giao việc";
    return source.replace(/^job:/, "lịch ");
  },
  /** "telegram:123" → "Telegram"; an unknown channel shows its own name. */
  channelName: (channel: string) => {
    const kind = channel.split(":")[0];
    return kind === "telegram" ? "Telegram" : kind;
  },
  runSteps: (n: number) => `${n} bước`,
  stepModel: "trả lời",
  // A call its run ended without: no model name came back, and "Đang suy nghĩ" would claim
  // it is still going. Read with the role and state beside it: "Mô hình trả lời dở dang".
  stepModelUnnamed: "Mô hình",
  stepFallback: "đổi tuyến",
  stepEscalation: "leo thang",
  // Why a turn moved to its escalation route, said under the row that names the route.
  stepEscalationReason: {
    loop: "Lượt gọi cùng một lệnh nhiều lần liên tiếp.",
    error: "Không tuyến chính nào trả lời.",
  },
  stepQuestion: "hỏi bạn",
  // Not "ghi chú": that would suggest something was written down and kept. The note only
  // reports what is happening right now, and disappears with the run.
  stepNote: "đang làm",
  // Said the way a note is said, but by a person rather than the agent: "bạn chèn" reads
  // as "you cut in", the same instant it happened.
  stepSteer: "bạn chèn",
  routeFallback: (detail: string) => `Tuyến ${detail} không trả lời, đã chuyển sang tuyến dự phòng.`,
  routeEscalated: (reason: "loop" | "error", route: string) =>
    reason === "loop"
      ? `Lượt này gọi cùng một lệnh nhiều lần liên tiếp; phần còn lại chạy trên tuyến leo thang ${route}.`
      : `Không tuyến chính nào trả lời; phần còn lại của lượt chạy trên tuyến leo thang ${route}.`,
  stepDuration: (ms: number) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)} giây` : `${ms} ms`),
  stepChars: (n: number) => `${n} ký tự`,
  stepCostUnknown: "không rõ giá",
  // A tool that asked a model itself (a picture read, a long output summarised), priced.
  stepToolCost: (price: string) => `Có gọi model · ${price}`,
  // Under the step of a script (`tool_script`): the calls it made on its own, which the
  // model never read. Counted in calls, since a script may call one tool many times, and
  // said of calls rather than of tools, since some of them ask a model and name no tool.
  scriptCalls: (count: number, failed: number) =>
    failed > 0 ? `Script đã thực hiện ${count} lời gọi · ${failed} lần lỗi` : `Script đã thực hiện ${count} lời gọi`,
  // On a call that changed something and was let through by the approval gate. Said in
  // words beside the call's name, so nobody has to tell it from a colour.
  scriptCallGated: "qua cổng duyệt",
  // A script asking a model itself rather than a tool. It is listed with the script's other
  // calls under these words: the name such a call travels under (`llm.classify`) is no
  // tool's, and nobody should have to read it as one.
  scriptModelCall: {
    "llm.classify": "Phân loại bằng model",
    "llm.summarise": "Tóm tắt bằng model",
  } as Record<string, string>,
  // A model call there is no word for here yet: still said to be one, with what was asked
  // of it as the server named it.
  scriptModelCallOther: (what: string) => `Gọi model (${what})`,
  // On a task a script handed to another agent: what that agent spent on it. The money is
  // the other conversation's, so it is said apart from what the script's own calls paid.
  scriptCallChildSpent: (price: string) => `Cuộc con đã chi ${price}`,
  // Under those calls once the script ended: what the calls handed the script, none of which
  // the model read, against what the script printed (of which the model reads what the
  // agent's cap on a tool's result lets through). A dash stands for a number nobody counted,
  // on a run from before the two were measured.
  scriptMeasures: (received: number | null, calls: number, printed: number | null) => {
    const chars = (n: number | null) => (n === null ? "—" : n.toLocaleString("vi-VN"));
    return `Nhận ${chars(received)} ký tự từ ${calls} lời gọi, trả về ${chars(printed)} ký tự`;
  },
  // The usage half of a model step's detail line: "openrouter:deepseek · TTFT 1.2s ·
  // 12.3k tok (8.1k cache) · suy nghĩ". TTFT is the wait before the first word came back.
  stepTtft: (ms: number) => `TTFT ${ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`}`,
  stepTokens: (tokens: string) => `${tokens} tok`,
  stepCached: (tokens: string) => `(${tokens} cache)`,
  stepThinking: "suy nghĩ",
  // Says what the model actually read, not what the tool actually printed.
  stepShaped: (kind: string, originalChars: number) => {
    const how =
      kind === "json"
        ? "rút gọn theo cấu trúc, giữ đủ key"
        : kind === "summary"
          ? "phần giữa được tóm tắt, đầu và cuối nguyên văn"
          : "cắt bớt phần cuối";
    return `Kết quả dài ${originalChars} ký tự — ${how}.`;
  },
  openConversation: "Mở cuộc trò chuyện",
} as const;
