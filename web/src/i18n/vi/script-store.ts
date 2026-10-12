export const viScriptStore = {
  // Manage → Ghi nhớ → "Script giữ lại": what an agent's scripts keep from one run to the
  // next with `store(key, value)`, set out per schedule and per conversation, each against
  // the most one of them holds. The words are the server's own for it: "giữ", "khoá".
  scriptStore: {
    tab: "Script giữ lại",
    intro:
      "Những gì script của agent giữ lại bằng store(khoá, giá_trị) để lần chạy sau đọc bằng load(khoá), xếp theo từng lịch và từng cuộc trò chuyện.",
    empty: "Script của agent này chưa giữ lại gì: giá trị script lưu bằng store(khoá, giá_trị) sẽ hiện ở đây.",
    kinds: { job: "Lịch", conv: "Cuộc trò chuyện", other: "Nơi khác" },
    // How a sentence names a namespace, as in "Xoá cả 3 khoá của lịch "Bản tin sáng"?". A name
    // comes to a sentence between its quotes already, escaped and cut to length
    // (`quotedName` in lib/quoted-name.ts): to these two, to `gone` and to the delete
    // sentences below. None of them adds quotes of its own.
    named: {
      job: (quoted: string) => `lịch ${quoted}`,
      conv: (quoted: string) => `cuộc trò chuyện ${quoted}`,
    },
    orphan: "Không còn nơi dùng",
    orphanHint: {
      job: "Agent không còn khai lịch này, nên không lần chạy nào đọc lại các khoá dưới đây. Có thể xoá.",
      conv: "Cuộc trò chuyện này đã bị xoá, nên không lần chạy nào đọc lại các khoá dưới đây. Có thể xoá.",
      other: "Không còn lịch hay cuộc trò chuyện nào đọc lại các khoá dưới đây. Có thể xoá.",
    },
    keyCount: (count: number) => `${count.toLocaleString("vi-VN")} khoá`,
    size: (chars: number, limit: number) => `${chars.toLocaleString("vi-VN")} / ${limit.toLocaleString("vi-VN")} ký tự`,
    sizeAlone: (chars: number) => `${chars.toLocaleString("vi-VN")} ký tự`,
    sizeLabel: (where: string) => `Chỗ đã dùng của ${where}`,
    // Said in words under the bar, so the warning is not left to a colour.
    nearLimit: "Sắp đầy: khi hết chỗ, store của script sẽ bị từ chối cho tới khi xoá bớt.",
    full: "Đã đầy: store của script bị từ chối cho tới khi xoá bớt.",
    entryChars: (chars: number) => `${chars.toLocaleString("vi-VN")} ký tự`,
    view: "Xem giá trị",
    hide: "Ẩn giá trị",
    // A key comes to the name of a button written out, whole and without quotes
    // (`writtenName` in lib/quoted-name.ts): the same writing its row has.
    viewLabel: (key: string) => `Xem giá trị của khoá ${key}`,
    hideLabel: (key: string) => `Ẩn giá trị của khoá ${key}`,
    valueLabel: (key: string) => `Giá trị của khoá ${key}`,
    valueLoading: "Đang đọc giá trị…",
    valueRaw: "Không đọc được như JSON nên hiện nguyên văn.",
    gone: (quoted: string) => `Khoá ${quoted} không còn nữa; đã tải lại danh sách.`,
    deleteKey: "Xoá",
    deleteKeyLabel: (key: string) => `Xoá khoá ${key}`,
    deleteKeyConfirm: (quoted: string, where: string) => `Xoá khoá ${quoted} của ${where}? Không thể hoàn tác.`,
    deleteAll: "Xoá tất cả",
    deleteAllLabel: (where: string) => `Xoá mọi khoá của ${where}`,
    deleteAllConfirm: (count: number, where: string) => `Xoá cả ${count} khoá của ${where}? Không thể hoàn tác.`,
    deletedKey: (quoted: string) => `Đã xoá khoá ${quoted}.`,
    deletedAll: (count: number, where: string) => `Đã xoá ${count} khoá của ${where}.`,
    nothingDeleted: "Không còn gì để xoá: phần này đã không còn trên máy chủ.",
  },
} as const;
