// The phone's inbox: what waits on the person, then what the jobs reported.
export const viInbox = {
  inbox: {
    title: "Hộp thư",
    // The header button that opens it, said with what it holds since a badge is only for the eye.
    open: "Mở hộp thư",
    openWith: (n: number) => `Mở hộp thư (${n} mục mới hoặc đang chờ)`,
    back: "Về cuộc trò chuyện",
    results: "Kết quả job",
    noResults: "Chưa có job nào báo kết quả.",
    // A row's own label: the job, who ran it and when, so a screen reader hears the card.
    resultLabel: (title: string, agent: string, at: string) => `${title}, ${agent}, ${at}`,
    unread: "Mới",
    loadFailed: "Không tải thêm được kết quả cũ; đang hiện những gì đã có.",
  },
} as const;
