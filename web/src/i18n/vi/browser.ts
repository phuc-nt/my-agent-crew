// The words for an agent's browser: the machine's card, the agent's own setting, the card of
// what runs with the window a person signs in through and the hosts it may be signed in to,
// the marks of the tools grid, a waiting call read in plain words, and a screenshot's caption.
import type { BrowserMode } from "../../api/types";

/** How long a tab or the browser has sat unused: seconds under a minute, then minutes. */
function idleFor(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return whole < 60 ? `${whole} giây` : `${Math.floor(whole / 60)} phút`;
}

export const viBrowser = {
  browser: {
    title: "Trình duyệt",
    // The machine's card on the connections page. Nothing there sets anything: the switch is
    // the machine's own file, and a restart reads it.
    machine: {
      off: "Đang tắt. Bật bằng browser_enabled: true trong config.yaml rồi khởi động lại máy chủ.",
      on: "Đang bật",
      channel: { chromium: "Chromium của đội", chrome: "Chrome của máy" },
      missingPlaywright: "Thiếu gói playwright.",
      missingChromium: "Chưa cài Chromium.",
      missingChrome:
        "Máy chưa có Google Chrome. Cài Chrome, hoặc bỏ browser_channel: chrome trong config.yaml để dùng Chromium của đội.",
      installWith: "Cài bằng lệnh:",
      running: (count: number, names: string) => `Đang chạy cho ${count} agent: ${names}`,
      noneRunning: "Chưa agent nào đang mở trình duyệt.",
    },
    // The agent's own setting, with its tools in the editor.
    sectionHint:
      "Có hiệu lực từ lượt kế tiếp sau khi lưu, không cần khởi động lại. Đặt về Tắt thì trình duyệt đang chạy của agent dừng ngay.",
    mode: "Mức dùng trình duyệt",
    modeOption: { off: "Tắt", read: "Đọc", act: "Thao tác" } satisfies Record<BrowserMode, string>,
    modeHint: {
      off: "Agent không có công cụ trình duyệt.",
      read: "Agent mở trang và đọc: browser_navigate, browser_snapshot, browser_text, browser_tabs, browser_screenshot, browser_pdf (in một trang thành PDF vào workspace). Mở một trang là việc phải duyệt, trừ khi máy chủ của trang nằm trong danh sách bên dưới hoặc hội thoại đang tự chủ.",
      act: "Thêm browser_act (bấm, gõ, chọn, tải tệp lên trên trang) và browser_download (bấm một nút, một liên kết để tải tệp về workspace). Cả hai luôn qua cổng duyệt; phần tử có chữ như thanh toán, đặt hàng, xoá, gửi thì luôn hỏi, kể cả khi hội thoại tự chủ.",
    } satisfies Record<BrowserMode, string>,
    hosts: "Máy chủ mở không cần hỏi",
    hostsHint:
      "Mỗi dòng một máy chủ, ví dụ shop.example hoặc *.shop.example. Trang ở các máy chủ này mở không cần hỏi. Khi có danh sách, trang và thao tác ở máy chủ ngoài danh sách luôn phải hỏi, kể cả khi tự chủ. Để trống: không giới hạn, và mở trang hỏi như mọi công cụ đổi trạng thái.",
    hostInvalid: (line: string) => `«${line}» không phải tên máy chủ: bỏ https://, cổng và đường dẫn.`,
    // Why an agent that asks for a browser has none: the machine's two facts.
    machineOffForAgent:
      "Máy này đang tắt trình duyệt (browser_enabled trong config.yaml), nên agent chưa có công cụ trình duyệt nào.",
    machineMissingForAgent: "Máy này chưa cài trình duyệt, nên agent chưa có công cụ trình duyệt nào. Xem mục Kết nối.",
    // Under the tool picker: why the browser's tools have no tick to give.
    outsideList: "Các công cụ browser_* không có ô chọn ở đây: chúng đi kèm mục Trình duyệt của agent.",
    // The card of what runs now, on the agent's page.
    card: {
      machineOff: "Máy này đang tắt trình duyệt, nên agent chưa mở được trang nào.",
      notInstalled: "Máy này chưa cài trình duyệt. Xem mục Kết nối.",
      stopped: "Chưa chạy. Trình duyệt tự mở khi agent gọi một công cụ trình duyệt, và tự tắt sau một lúc không dùng.",
      // In place of the line above while a person's own window holds the profile.
      loginOpen: "Agent không dùng được trình duyệt trong lúc cửa sổ đăng nhập đang mở.",
      running: (tabs: number) => `Đang chạy · ${tabs} tab`,
      working: "đang làm việc",
      inUse: "đang dùng",
      idle: (seconds: number) => `rảnh ${idleFor(seconds)}`,
      tabs: "Các tab đang mở",
      untitled: "(chưa có tiêu đề)",
      blank: "(trang trống)",
      scheduled: "Việc theo lịch",
      conversation: "Mở cuộc trò chuyện",
      conversationOf: (label: string) => `Mở cuộc trò chuyện của tab ${label}`,
      inConversation: "Trong một cuộc trò chuyện",
      closeTab: "Đóng tab",
      closeTabNamed: (label: string) => `Đóng tab ${label}`,
      closing: "Đang đóng…",
      stop: "Dừng trình duyệt",
      stopping: "Đang dừng…",
      stopNote: "Đăng nhập vẫn được giữ; lần gọi kế tiếp của agent sẽ mở lại trình duyệt.",
      // The state could not be read again: what is on screen may be a few seconds old.
      readFailed: (message: string) => `Không đọc được trạng thái trình duyệt: ${message}`,
    },
    // The window a person signs in through, on the card. It opens on the screen of the
    // machine the crew runs on, which may not be the one this page is read on.
    login: {
      open: (clock: string | null) =>
        `Cửa sổ đăng nhập đang mở trên màn hình của máy chạy đội.${clock === null ? "" : ` Tự đóng lúc ${clock}.`}`,
      done: "Xong",
      closing: "Đang đóng…",
      address: "Địa chỉ mở sẵn (không bắt buộc)",
      start: "Mở cửa sổ đăng nhập",
      starting: "Đang mở…",
      hint: "Cửa sổ hiện trên màn hình của máy chạy đội, không phải trên thiết bị đang xem trang này. Trong lúc cửa sổ mở, trình duyệt của agent dừng và các tab của nó đóng. Cửa sổ tự đóng sau một lúc.",
      // What is in the way, by the server's own word for it.
      why: {
        no_console: "Máy chủ của đội không chạy trong phiên màn hình nào đang mở, nên không có chỗ hiện cửa sổ đăng nhập.",
        locked: "Màn hình của máy đang khoá. Mở khoá thì mở được cửa sổ đăng nhập.",
        busy: "Agent đang dùng trình duyệt cho một lần gọi. Chờ lần gọi đó xong, hoặc dừng trình duyệt, rồi mở cửa sổ đăng nhập.",
      },
      // For a word a later server adds.
      notNow: "Lúc này chưa mở được cửa sổ đăng nhập.",
    },
    // Where the browser may still be signed in, on the card: read off its cookies.
    signedIn: {
      label: "Có thể đang đăng nhập ở",
      until: (date: string) => `đến ${date}`,
      nothing: "chưa thấy đăng nhập",
      none: "Chưa thấy đăng nhập ở máy chủ nào.",
      more: (count: number) => `+${count} máy chủ nữa`,
      caveat:
        "Đoán từ cookie còn hạn trong hồ sơ trình duyệt: là dấu hiệu, không phải bằng chứng. Trang có thể đã tự đăng xuất, và có trang giữ cookie như vậy cho cả người chưa đăng nhập.",
    },
    // The tools grid: the tools no list gives, and why an agent lacks one.
    withBrowser: "đi kèm trình duyệt",
    withBrowserTitle:
      "Không thuộc danh sách công cụ của agent. Agent có các công cụ này khi hồ sơ đặt Trình duyệt ở Đọc hoặc Thao tác và máy đã bật trình duyệt.",
    cellOff: "Agent đặt Trình duyệt ở Tắt.",
    cellReadOnly: "Agent chỉ đọc trang; công cụ này cần mức Thao tác.",
    // A call that waits for a person, read from its arguments. What is named comes from a
    // model and from the page it is on: each piece arrives here already cut to length.
    call: {
      navigate: (host: string) => `Mở trang ${host}`,
      click: (name: string) => `Bấm «${name}»`,
      type: (text: string, name: string) => `Gõ «${text}» vào «${name}»`,
      fill: (text: string, name: string) => `Điền «${text}» vào «${name}»`,
      press: (key: string, name: string) => `Nhấn ${key} tại «${name}»`,
      select: (value: string, name: string) => `Chọn «${value}» ở «${name}»`,
      hover: (name: string) => `Rê chuột lên «${name}»`,
      scroll: (name: string) => `Cuộn tới «${name}»`,
      upload: (path: string, name: string) => `Tải tệp ${path} lên «${name}»`,
      download: (name: string) => `Bấm «${name}» để tải tệp về`,
      downloadAs: (name: string, file: string) => `Bấm «${name}» để tải tệp về, lưu thành ${file}`,
    },
    screenshotAlt: (label: string) => `Ảnh chụp tab ${label}`,
  },
} as const;
