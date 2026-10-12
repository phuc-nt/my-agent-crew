export const viJobs = {
  jobs: "Lịch chạy",
  jobsEmpty: "Chưa agent nào có lịch chạy. Thêm lịch trong trang sửa agent, ở mục Đội.",
  jobNext: "Lần tới",
  jobLast: "Lần trước",
  jobNever: "chưa chạy",
  jobDisabled: "tắt",
  jobPaused: "tạm dừng",
  jobEnabled: "Bật lịch",
  jobDisabledInProfile: "Tắt trong hồ sơ agent — bấm Sửa lịch để bật lại.",
  jobRunning: "đang chạy…",
  // Only a chat-origin job ("tạo từ chat") gets a delete button — a profile job needs its
  // `agent.yaml` edited and a restart instead, so there is nothing to confirm-delete here.
  jobFromChat: "tạo từ chat",
  jobDelete: "Xoá lịch",
  jobDeleteConfirm: (name: string) => `Xoá lịch "${name}"? Không thể hoàn tác.`,
  runNow: "Chạy ngay",
  jobHistory: "Lịch sử chạy",
  showHistory: "Xem lịch sử",
  hideHistory: "Ẩn lịch sử",
  jobHistoryEmpty: "Lịch này chưa chạy lần nào.",
  jobKindPrompt: "nhắc agent",
  jobKindCommand: "lệnh shell",
  jobKindScript: "chạy script",
  jobKindConsolidate: "cô đọng bộ nhớ",
  // Under a script job's source: the prompt a turn is opened with when the script printed
  // something, and with nothing printed no model is called at all.
  jobThenPrompt: "Có kết quả thì nhắc agent",
  jobSkills: "Kỹ năng gắn sẵn",
  jobRow: {
    edit: "Sửa lịch",
    editOf: (job: string) => `Sửa lịch ${job}`,
    openCrew: "Mở mục Đội",
    // The back link of an editor or a run opened from a job's row, which it returns to.
    back: "← Lịch chạy",
    // After a relative time on the row: "sau 3 giờ, lúc 07:00".
    atClock: (clock: string) => `, lúc ${clock}`,
    // Visibly the run cards' own "Xem riêng", which opens the same page from the history.
    openRunOf: (job: string) => `Xem riêng lượt chạy gần nhất của ${job}`,
    // Beside the Jobs entry in the nav: the count alone is red, this is what it counts.
    failing: (n: number) => `${n} lịch lỗi ở lần chạy gần nhất`,
    // A cron read aloud. The hour is the server's own clock, which is the owner's.
    cron: {
      every: (n: number, unit: string) => (n === 1 ? `Mỗi ${unit}` : `Mỗi ${n} ${unit}`),
      units: { s: "giây", m: "phút", h: "giờ", d: "ngày" } as Record<string, string>,
      atMinute: (every: string, minute: number) => `${every} vào phút ${minute}`,
      daily: (time: string) => `Mỗi ngày ${time}`,
      weekdays: (time: string) => `Thứ Hai–Thứ Sáu ${time}`,
      weekend: (time: string) => `Cuối tuần ${time}`,
      weekly: (days: string, time: string) => `${days} hằng tuần ${time}`,
      monthly: (day: number, time: string) => `Ngày ${day} hằng tháng ${time}`,
      days: ["Chủ Nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy"],
    },
  },
} as const;
