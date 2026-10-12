export const viEditor = {
  editor: {
    back: "← Đội",
    notFound: (id: string) => `Không có agent nào tên ${id}.`,
    readOnly: "Agent này định nghĩa sẵn trong bộ mẫu nên không sửa được ở đây.",
    definedAt: (path: string) => `Định nghĩa tại ${path}`,
    save: "Lưu",
    saving: "Đang lưu…",
    saved: "Đã lưu.",
    revert: "Hoàn tác",
    dirty: (n: number) => `${n} thay đổi chưa lưu`,
    clean: "Chưa có thay đổi",
    saveFailed: (message: string) => `Không lưu được: ${message}`,
    // After a save that changed when the agent runs: a schedule used to wait for a restart,
    // so the person is told this one does not.
    scheduleLive: "Đã lưu. Lịch chạy mới có hiệu lực ngay, không cần khởi động lại.",
    sectionIdentity: "Nhận dạng",
    sectionModel: "Mô hình",
    sectionPersona: "Tính cách",
    sectionTools: "Công cụ",
    sectionDelegates: "Giao việc",
    sectionLimits: "Giới hạn",
    sectionSchedules: "Lịch chạy",
    sectionTelegram: "Telegram",
    sectionSkills: "Kỹ năng",
    name: "Tên",
    description: "Mô tả",
    descriptionHint: "Master đọc câu này để quyết định khi nào giao việc cho agent.",
    mode: "Chế độ",
    modeChat: "Trò chuyện",
    modeWork: "Làm việc",
    modeHint: "Chế độ làm việc mở thêm các công cụ ghi và chạy lệnh.",
    workspace: "Thư mục làm việc",
    workspaceHint: "Phải nằm trong thư mục nhà của đội.",
    routes: "Tuyến mô hình",
    routesHint: "Thử lần lượt từ trên xuống. Mỗi dòng một tuyến.",
    provider: "Nhà cung cấp",
    model: "Mô hình",
    addRoute: "+ Thêm tuyến",
    escalationRoute: "Tuyến leo thang",
    escalationRouteHint:
      "Chỉ dùng khi một lượt bị kẹt: gọi cùng một lệnh nhiều lần liên tiếp, hoặc mọi tuyến ở trên đều lỗi. Phần còn lại của lượt đó chạy trên tuyến này; lượt sau quay về các tuyến ở trên.",
    escalationRouteNone: "Chưa đặt: lượt bị kẹt sẽ dừng như trước.",
    addEscalationRoute: "+ Đặt tuyến leo thang",
    removeEscalationRoute: "Bỏ tuyến leo thang",
    escalationModelMissing: "Nhập tên mô hình, hoặc bỏ tuyến leo thang.",
    escalationSameAsRoute: "Tuyến leo thang phải khác mọi tuyến ở trên.",
    remove: "Xoá",
    persona: "Tệp tính cách",
    personaHint: "Nội dung các tệp này được ghép vào lời nhắc hệ thống mỗi lượt.",
    personaSaved: (name: string) => `Đã ghi ${name}.`,
    personaSave: "Ghi tệp",
    personaEmpty: "(trống)",
    sectionPrompt: "Lời nhắc hệ thống",
    promptHint:
      "Nội dung agent được đọc ở đầu mỗi lượt: khung chung, các tệp tính cách, trí nhớ dài hạn và kỹ năng.",
    promptOpening: "Đọc ngay trước tin đầu của cuộc mới",
    promptOpeningHint:
      "Ghi chú hôm qua và hôm nay không nằm trong lời nhắc hệ thống: agent đọc chúng ngay trước tin mở đầu lượt, và lượt sau chỉ đọc phần mới thêm. Tóm tắt cuộc trò chuyện trước của từng kênh cũng được đọc ở đó.",
    promptChars: (chars: number) => `${chars.toLocaleString("vi-VN")} ký tự`,
    promptShow: "Xem lời nhắc",
    promptHide: "Ẩn",
    promptFailed: "Không đọc được lời nhắc.",
    toolsAll: "Dùng tất cả công cụ hợp lệ",
    toolsPick: "Chỉ dùng các công cụ được chọn",
    toolsHint: "Bỏ trống danh sách nghĩa là agent dùng mọi công cụ hợp lệ với chế độ của nó.",
    mcp: "Máy chủ MCP",
    mcpHint: "Bật máy chủ nào thì agent có công cụ của máy chủ đó. Công cụ MCP không theo danh sách chọn ở trên, và luôn hỏi trước khi chạy trừ khi config.yaml ghi là chỉ đọc.",
    mcpNone: "Chưa khai máy chủ MCP nào trong config.yaml.",
    mcpGone: "không còn trong config.yaml, bỏ chọn rồi mới lưu được",
    delegates: "Có thể giao việc cho",
    delegatesHint: "Chỉ agent chính mới nên giao việc; agent con giao chéo dễ thành vòng lặp.",
    delegatesEmpty: "Không giao cho ai.",
    costCap: "Trần chi phí mỗi cuộc trò chuyện (USD)",
    maxSteps: "Số bước tối đa",
    autonomous: "Tự chủ — không hỏi trước khi thay đổi dữ liệu",
    askPatterns: "Lệnh vẫn phải hỏi",
    askPatternsHint: "Mỗi dòng một mẫu. Vẫn được hỏi kể cả khi agent tự chủ.",
    toolOutputChars: "Cắt kết quả công cụ (ký tự)",
    memoryConsolidate: "Lịch gom ghi nhớ (cron)",
    memoryConsolidateHint: "Bỏ trống để không gom. Ví dụ 0 3 * * * là 3 giờ sáng mỗi ngày.",
    schedules: "Lịch chạy",
    schedulesHint: "Mỗi lịch chạy theo cron hoặc theo chu kỳ, rồi nhắc agent, chạy một lệnh shell hoặc chạy một script.",
    schedulesEmpty: "Agent này chưa có lịch nào.",
    scheduleId: "Mã",
    scheduleIdHint: "Bỏ trống để tự đặt. Giữ nguyên mã thì lịch sử chạy không bị tách.",
    // For a row that runs a script, in place of the hint above: what the script keeps is
    // stored under the row's id, so the row is not saved without one.
    scheduleIdHintScript: "Những gì script giữ lại được lưu theo mã này. Giữ nguyên mã thì script đọc lại được và lịch sử chạy không bị tách.",
    scheduleIdMissing: "Nhập mã cho lịch này: những gì script giữ lại được lưu theo mã, còn mã bỏ trống thì đổi theo vị trí của lịch trong danh sách.",
    scheduleIdTaken: "Mã này đã có ở lịch khác; mỗi lịch cần một mã riêng.",
    scheduleIdReserved: "Mã memory-consolidate dành cho lịch gom ghi nhớ; đặt mã khác.",
    scheduleName: "Tên",
    scheduleEnabled: (name: string) => `Bật lịch ${name}`,
    scheduleTiming: "Chạy khi nào",
    scheduleCron: "Cron",
    scheduleEvery: "Chu kỳ",
    scheduleCronHint: "5 trường: phút giờ ngày tháng thứ, ví dụ 0 7 * * *.",
    scheduleEveryHint: "Ví dụ 30m, 2h hoặc 1d; tối thiểu 1 phút.",
    // Replaces the format hint once what was typed reads as words, so the person checks
    // the reading rather than counting fields.
    scheduleReads: (words: string) => `Tức là: ${words}.`,
    scheduleAction: "Làm gì",
    schedulePrompt: "Nhắc agent",
    scheduleCommand: "Lệnh shell",
    // A job that runs a script with no model call. Under its box: what runs it, how to
    // indent in a box the Tab key leaves, and the two things only the server can refuse.
    scheduleScript: "Script",
    scheduleScriptHint:
      "Chạy bằng bộ máy của tool_script, không mở lượt nào của agent. Thụt lề bằng dấu cách (phím Tab chuyển sang ô kế tiếp); dấu tab dán vào được giữ nguyên. Tối đa 20.000 ký tự; máy chủ xét cú pháp khi lưu.",
    scheduleThenPrompt: "Nhắc agent khi script in ra kết quả",
    scheduleSkillsEmpty: "Agent này chưa có kỹ năng nào để gắn.",
    // A row not named yet goes by its place in the list: "Xoá lịch số 2".
    scheduleUnnamed: (position: number) => `số ${position}`,
    scheduleRemove: (name: string) => `Xoá lịch ${name}`,
    addSchedule: "+ Thêm lịch",
    cronInvalid: "Cron cần 5 trường: phút 0–59, giờ 0–23, ngày 1–31, tháng 1–12, thứ 0–7. Ví dụ 0 7 * * *.",
    everyInvalid: "Chu kỳ dạng 30m, 2h hoặc 1d, tối thiểu 1 phút.",
    promptMissing: "Nhập lời nhắc cho agent.",
    commandMissing: "Nhập lệnh shell cần chạy.",
    problemsHoldSave: "Sửa các ô báo lỗi rồi mới lưu được.",
    telegramEnabled: "Bật kênh Telegram",
    telegramTokenEnv: "Tên biến môi trường chứa token",
    telegramHint: "Chỉ ghi TÊN biến. Giá trị token đặt ở mục Kết nối, không nhập ở đây.",
    telegramChatId: "Mã cuộc trò chuyện (chat_id)",
    telegramChatIdHint: "Số nguyên Telegram gán cho cuộc trò chuyện; nhóm có dấu trừ ở đầu.",
    chatIdInvalid: "chat_id phải là số nguyên khác 0.",
    telegramOnlyMaster: "Hiện chỉ agent chính nhận tin Telegram; cấu hình ở agent khác sẽ bị bỏ qua.",
    skillsEmpty: "Agent này chưa nạp kỹ năng nào.",
    deleteTitle: "Xoá agent",
    deleteHint: (id: string) => `Gõ ${id} để xác nhận. Thư mục được chuyển vào .trash chứ không xoá hẳn.`,
    // What the folder in .trash does not bring back: the server drops these with the agent.
    deleteLost:
      "Xoá hẳn, không lấy lại được: những gì script của agent này giữ lại, các lịch nó được tạo từ chat và trạng thái bật/tắt của từng lịch. Hội thoại và lịch sử run vẫn giữ nguyên.",
    deleteConfirm: "Xoá agent",
    deleted: (id: string, kept: string) => `Đã gỡ ${id}. Thư mục còn ở ${kept}.`,
    deleteFailed: (message: string) => `Không xoá được: ${message}`,
    // What the agent's scripts may reach, and whether they may ask a model. Both hold from
    // the turn after a save: a turn under way ends with what it began with.
    sectionScript: "Script",
    scriptHint:
      "Script là đoạn mã agent tự viết để gọi nhiều công cụ trong một lần chạy (công cụ tool_script). Hai mục này có hiệu lực từ lượt kế tiếp sau khi lưu, không cần khởi động lại; lượt đang chạy giữ nguyên như lúc bắt đầu.",
    scriptCalls: "Script gọi được gì",
    scriptCallsOption: {
      none: "Không dùng script",
      read_only: "Chỉ công cụ đọc",
      gated: "Cả công cụ thay đổi dữ liệu",
    },
    scriptCallsHint: {
      none: "Agent không được trao tool_script. Script của một lịch chạy vẫn chạy, và chỉ đọc.",
      read_only: "Script chỉ gọi được các công cụ đọc.",
      gated:
        "Script gọi được cả công cụ thay đổi dữ liệu, mỗi lời gọi đi qua cổng duyệt; lời gọi nào phải hỏi người thì script dừng ở đó. Nếu agent tự chủ, các lời gọi ấy chạy luôn, không ai được hỏi.",
    },
    // In place of the gated hint while the form has autonomy switched on: what the two
    // settings mean together, for this agent.
    scriptCallsGatedAutonomous:
      "Agent này đang tự chủ nên script của nó thay đổi dữ liệu mà không ai được hỏi. Chỉ lệnh khớp mục “Lệnh vẫn phải hỏi” mới làm script dừng lại.",
    scriptLlm: "Cho script hỏi mô hình",
    scriptLlmHint:
      "Đây là phần duy nhất của script tốn tiền: mỗi script hỏi mô hình tối đa 10 lần. Tắt thì script trong lượt và script của lịch chạy đều không hỏi được.",
    // The way from here to the screen that shows what this agent's scripts keep.
    scriptStoreLink: "Xem những gì script của agent này giữ lại",
    // A schedule that runs a script, written in the form. Under the box of the prompt its
    // output goes on with: when a turn is opened, and that otherwise nobody hears of the run.
    scheduleThenPromptHint:
      "Không bắt buộc. Khi script in ra kết quả, một lượt được mở với lời nhắc này kèm phần đã in, và câu trả lời được gửi qua Telegram. Bỏ trống, hoặc script không in gì, thì không ai được báo.",
    scriptMissing: "Nhập script cần chạy.",
    scriptTooLong: (most: number) => `Script dài quá ${most.toLocaleString("vi-VN")} ký tự; rút gọn rồi mới lưu được.`,
    // What the tool picker says of `delegate` while no agent holds it: the registry then
    // has no row for it, and so no description of its own to show.
    toolDelegate: "Giao một việc trọn vẹn cho agent khác và chờ kết quả.",
    // Under a name the list holds that the server says it has no say over for this agent
    // today: a tool of a mode it is not in, one the machine cannot run now, one handed
    // whatever the list says. The row stays ticked until the person unticks it.
    toolNotGiven: "Hiện giờ danh sách không đem lại công cụ này cho agent. Bỏ chọn thì tên này rời khỏi danh sách.",
    // Under the picker while the form holds an unsaved change to the mode or to whom the
    // agent hands work: both move which tools a list has a say over, once they are saved.
    toolsFollowSaved:
      "Các công cụ ở trên theo agent như đã lưu. Lưu thay đổi ở “Chế độ” hoặc “Có thể giao việc cho” trước, rồi mới chọn công cụ.",
  },
} as const;
