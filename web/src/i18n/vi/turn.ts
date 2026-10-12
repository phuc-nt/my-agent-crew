export const viTurn = {
  awaitingApproval: "Agent muốn chạy một công cụ cần bạn duyệt.",
  approvalTitle: (tool: string) => `Cho phép chạy ${tool}?`,
  approve: "Cho phép",
  deny: "Từ chối",
  alwaysAllow: "Luôn cho phép",
  alwaysAllowHint: "Cho phép lần này và không hỏi lại công cụ này trong cuộc trò chuyện này.",
  approvalDeadline: (time: string) => `Không ai trả lời thì tự từ chối lúc ${time}.`,
  autoApproved: "Luôn cho phép",
  autoApprovedHint: "Công cụ chạy không hỏi trong cuộc trò chuyện này. Bấm để hỏi lại.",
  autoApprovedRevoke: (tool: string) => `Hỏi lại khi chạy ${tool}`,
  approvalHistory: "Lịch sử duyệt",
  approvalHistoryEmpty: "Chưa có yêu cầu duyệt nào.",
  approvalOptions: "Lựa chọn:",
  approvalAnswer: (answer: string) => `Bạn đã trả lời: ${answer}`,
  approvalStatus: {
    pending: "chờ duyệt",
    approved: "đã cho phép",
    denied: "đã từ chối",
    expired: "hết hạn",
    answered: "đã trả lời",
  } as Record<string, string>,
  // A question is not a permission request: the agent is stuck on something only the
  // person knows, and an unanswered one falls back to its default instead of refusing.
  awaitingAnswer: "Agent đang hỏi bạn một câu.",
  questionTitle: "Agent hỏi",
  questionPlaceholder: "Trả lời…",
  questionSend: "Gửi trả lời",
  questionEmpty: "Hãy nhập câu trả lời.",
  questionDeadline: (time: string) => `Không trả lời thì agent tự dùng mặc định lúc ${time}.`,
  questionAsked: (asked: string) => `Câu hỏi: ${asked}`,
  toolRunning: "đang chạy",
  toolDone: "xong",
  toolFailed: "lỗi",
  toolAwaiting: "chờ duyệt",
  toolDenied: "đã từ chối",
  // The turn ended before the call answered: nothing is running it any more.
  toolStopped: "đã dừng",
  // A step left open when its run ended: it neither succeeded nor reported a
  // failure, and saying so is more honest than picking one of the two.
  toolStalled: "dở dang",
  // Nothing is being computed and no time is being bought: the run is stopped until a
  // person types. "đang chạy" would show effort that is not happening.
  toolWaiting: "đang chờ trả lời",
  stepDelegate: "giao việc",
  stepRepeat: (n: number) => `×${n}`,
  // The live header, one line: what the agent is doing right now.
  runDoing: (label: string) => `Đang ${label}`,
  runThinking: "Đang suy nghĩ",
  // Not "Đang suy nghĩ": the agent is not working on anything, it is stopped until the
  // person answers, and the header is where someone looks to find out why nothing moves.
  runWaitingAnswer: "Đang chờ bạn trả lời",
  // And the same line once the run has settled. A finished run has no "right
  // now", so it says how it ended rather than borrowing a present tense.
  runEndedDone: "Đã xong",
  runEndedHalted: "Đã dừng",
  runEndedError: "Đã lỗi",
  // Under the header of a run the server carried on after a restart. It explains the two
  // things that would otherwise look wrong: a step closed as cut off, and a clock that
  // started before the server did.
  runResumed: "Tiếp tục sau khi server khởi động lại",
  runStepCount: (done: number, total: number) => `${done}/${total} bước`,
  runElapsed: (ms: number) =>
    ms >= 60_000
      ? `${Math.floor(ms / 60_000)} phút ${Math.floor((ms % 60_000) / 1000)} giây`
      : `${(ms / 1000).toFixed(1)} giây`,
  showOutput: "Xem kết quả",
  hideOutput: "Ẩn kết quả",
  arguments: "Tham số",
  argumentsMore: "Xem đầy đủ",
  argumentsLess: "Thu gọn",
  delegateTo: "Giao cho {agent}",
  delegateTask: "Việc đã giao",
  delegateRunning: "đang làm",
  delegateSteps: "{n} bước",
  // What a handed-off task came to, keyed by the `outcome=` word the server writes.
  delegateOutcome: {
    done: "xong",
    done_with_concerns: "xong, còn lưu ý",
    blocked: "bị chặn",
    needs_context: "cần thêm thông tin",
    failed: "không xong",
  } as Record<string, string>,
  delegateTimeout: "Hết thời gian chờ, agent con vẫn đang làm",
  // A tool approval the child asked for, refused, or left unanswered until it lapsed.
  delegateRefused: {
    denied: (tool: string) => `${tool} bị từ chối`,
    expired: (tool: string) => `${tool} hết hạn duyệt`,
  } as Record<string, (tool: string) => string>,
  delegateOpenChild: "Mở cuộc con",
  delegateUnknownAgent: "agent khác",
  delegateChildOf: "cuộc con của {parent}",
  delegateIncludesChildren: "gồm {n} cuộc con",
  modeWork: "Làm việc",
  modeAssistant: "Trợ lý",
  toolCount: "{n} công cụ",
  delegatesTo: "giao được cho",
  delegateChild: "cuộc do agent khác mở",
  modeWorkHint: "tự chủ · cap ${cap} · {steps} bước",
} as const;
