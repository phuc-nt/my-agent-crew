/** Said of a tool that asks before it runs; used on its own and inside the tools summary. */
const requiresApproval = "cần duyệt";

export const viSettings = {
  settingsSections: {
    routes: "Tuyến model (thứ tự dự phòng)",
    keys: "Khoá API",
    tools: "Công cụ",
    skills: "Kỹ năng có sẵn",
    crew: "Đội agent",
    system: "Hệ thống",
    // The page's build and the server's, which differ once the server restarts on a new one.
    versions: (page: string | null, server: string | null) =>
      [page && `Giao diện ${page}`, server && `Máy chủ ${server}`].filter(Boolean).join(" · "),
    toolsSummary: (total: number, gated: number) => `${total} · ${gated} ${requiresApproval}`,
    toolsHint: "Công cụ nào agent nào dùng được: xem ở mục Công cụ.",
    openTools: "Xem theo agent →",
    openCrew: "Sửa đội →",
    openConnections: "Đặt khoá ở Kết nối →",
    primary: "chính",
    fallback: "dự phòng",
  },
  keyPresent: "đã có",
  keyMissing: "chưa có",
  requiresApproval,
  home: "Thư mục cấu hình",
  workspace: "Thư mục làm việc",
  usersDir: "Thư mục ghi nhớ chung",
  timezone: "Múi giờ",
  machineZone: "theo máy",
  maxSteps: "Số bước tối đa mỗi lượt",
  defaultCap: "Ngân sách mặc định",
  you: "Bạn",
  agent: "Agent",

  agents: "Agent",
  agentPersona: (files: number) => `${files} tệp nhân cách`,
  agentSchedules: (n: number) => `${n} lịch`,
  agentCommands: (n: number) => `${n} lệnh`,
  agentHooks: (n: number) => `${n} hook`,
  agentKits: "Kit",
} as const;
