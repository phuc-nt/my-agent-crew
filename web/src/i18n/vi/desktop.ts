// The words for an agent's desktop: the machine's row on the connections page, the agent's
// own setting, the card on its page, the marks of the tools grid, a waiting computer_act call
// read in plain words, and the picture a screenshot saved. The sentences the server words
// (a 409, a 422, a tool's answer) are shown as they come and are not here.
import type { ComputerMode } from "../../api/types";

/** The two permissions the helper holds, by their keys in the server's answer. */
const PERMISSION = {
  screen_recording: "Ghi màn hình (Screen Recording)",
  accessibility: "Trợ năng (Accessibility)",
} as const;

export const viDesktop = {
  desktop: {
    title: "Desktop",
    permission: PERMISSION,
    // The machine's row on the connections page. The only thing it sets is a request to
    // macOS, sent on a press: the helper and its permissions are the machine owner's.
    machine: {
      absent:
        "Máy này chưa có trình trợ giúp desktop đang chạy, nên agent chưa nhìn và chưa thao tác được trên màn hình. Việc cài và mở nó là của chủ máy.",
      present: "Trình trợ giúp đang chạy",
      version: (version: string) => `bản ${version}`,
      locked: "Màn hình đang khoá",
      asleep: "Màn hình đang tắt",
      granted: "đã cấp",
      missing: "chưa cấp",
      unknown: "chưa rõ",
      permissionsLabel: "Quyền của trình trợ giúp",
      ask: "Xin quyền",
      asking: "Đang xin quyền…",
      askHint:
        "macOS hiện hộp thoại xin quyền trên màn hình của máy chạy đội, mỗi quyền chỉ một lần. Quyền đã hỏi rồi thì chủ máy cấp trong Cài đặt hệ thống → Quyền riêng tư & Bảo mật.",
      stillMissing: (names: string) =>
        `Vẫn chưa cấp: ${names}. Nút này không làm thêm được gì: chủ máy cấp trong Cài đặt hệ thống → Quyền riêng tư & Bảo mật.`,
    },
    // The agent's own setting, with its tools in the editor.
    editor: {
      sectionHint: "Có hiệu lực từ lượt kế tiếp sau khi lưu, không cần khởi động lại.",
      mode: "Dùng desktop của máy",
      modeOption: { off: "Tắt", on: "Bật" } satisfies Record<ComputerMode, string>,
      modeHint: {
        off: "Agent không có công cụ desktop.",
        on: "Agent có computer_state, computer_screenshot, computer_observe và computer_act: nhìn màn hình của máy, đọc phần tử và thao tác trong các ứng dụng của danh sách bên dưới. computer_act qua cổng duyệt; đưa ứng dụng lên trước, bấm theo toạ độ, bấm đúp, kéo, Enter, Space và tổ hợp phím lạ thì luôn hỏi, kể cả khi hội thoại tự chủ. Đoạn chữ có ký tự điều khiển (trừ Tab và xuống dòng) không bao giờ được gõ.",
      } satisfies Record<ComputerMode, string>,
      helperNote:
        "Trình trợ giúp desktop và hai quyền macOS của nó là việc của chủ máy: cài, mở và cấp quyền trên máy chạy đội. Xem mục Kết nối.",
      apps: "Ứng dụng agent được dùng",
      appsHint:
        "Mỗi dòng một ứng dụng: tên (Notes) hoặc bundle id (com.apple.Notes). Để trống: agent chỉ nhìn màn hình, không đọc phần tử và không thao tác trong ứng dụng nào. Không ghi trình duyệt web (Safari, Chrome, Firefox…): desktop không thao tác trong trình duyệt, trang web là việc của mục Trình duyệt.",
    },
    // Under the tool picker: why the desktop's tools have no tick to give.
    outsideList: "Các công cụ computer_* không có ô chọn ở đây: cả bốn đi kèm mục Desktop của agent (khoá computer).",
    // The card on the agent's page: its setting, the machine as it is for it, and a picture.
    card: {
      mode: { off: "Tắt: agent không có công cụ desktop.", on: "Bật" } satisfies Record<ComputerMode, string>,
      apps: (names: string) => `Ứng dụng: ${names}`,
      lookOnly: "Chưa có ứng dụng nào: agent chỉ nhìn màn hình, không đọc phần tử và không thao tác.",
      noHelper: "Máy này chưa có trình trợ giúp desktop đang chạy. Việc cài và mở nó là của chủ máy.",
      locked: "Màn hình của máy đang khoá.",
      asleep: "Màn hình của máy đang tắt.",
      missing: (name: string) => `Trình trợ giúp chưa được cấp quyền ${name}.`,
      unknown: (name: string) => `Trình trợ giúp chưa cho biết đã có quyền ${name} chưa.`,
      ready: "Sẵn sàng: trình trợ giúp đang chạy, màn hình đang mở và đã có cả hai quyền.",
      tryShot: "Thử chụp",
      shooting: "Đang chụp…",
      tryHint:
        "Chụp cả màn hình như agent tự chụp, trong giới hạn ứng dụng của agent, và lưu vào thư mục desktop/ của agent: trong thư mục đầu tiên của write_paths, hoặc ngay trong workspace khi agent không có write_paths. Ảnh thử là ảnh mới nhất của máy: khung hình agent đang dùng thành cũ, và lần thao tác kế tiếp của agent phải nhìn lại.",
      shotAlt: (width: number, height: number) => `Ảnh thử chụp màn hình, ${width}×${height}`,
      gaveUp: "Trình trợ giúp không trả lời sau 35 giây nên trang đã thôi chờ.",
      readFailed: (message: string) => `Không đọc được trạng thái desktop: ${message}`,
    },
    // The tools grid: the tools no list gives, and why an agent lacks one.
    withDesktop: "đi kèm desktop",
    withDesktopTitle:
      "Không thuộc danh sách công cụ của agent. Agent có cả bốn công cụ này khi hồ sơ đặt Desktop ở Bật, có hay không có trình trợ giúp trên máy.",
    cellOff: "Agent đặt Desktop ở Tắt.",
    // A computer_act call that waits for a person, read from its arguments. Each piece
    // arrives here already flattened and cut to length; a point is "(x, y)" in the
    // pixels of the frame's picture.
    call: {
      click: { click: "Bấm", double_click: "Bấm đúp", right_click: "Bấm chuột phải" },
      byRef: (verb: string, name: string, ref: string, app: string) => `${verb} «${name}» (${ref}) trong ${app}`,
      byRefUnnamed: (verb: string, ref: string, app: string) => `${verb} phần tử ${ref} trong ${app}`,
      byPoint: (verb: string, point: string, app: string) => `${verb} tại điểm ${point} trong ${app}`,
      drag: (from: string, to: string, app: string) => `Kéo từ điểm ${from} tới điểm ${to} trong ${app}`,
      scroll: (dx: string, dy: string, point: string, app: string) =>
        `Cuộn ${dx} dòng ngang, ${dy} dòng dọc tại điểm ${point} trong ${app}`,
      type: (text: string, app: string) => `Gõ «${text}» vào chỗ đang có con trỏ trong ${app}`,
      setValue: (text: string, ref: string, app: string) => `Đặt «${text}» vào phần tử ${ref} trong ${app}`,
      setValueNamed: (text: string, name: string, ref: string, app: string) =>
        `Đặt «${text}» vào ô «${name}» (${ref}) trong ${app}`,
      key: (keys: string, app: string) => `Nhấn ${keys} trong ${app}`,
      focusApp: (app: string) => `Đưa ${app} lên trước màn hình`,
    },
    // The picture an action was chosen on, on its approval card.
    frame: {
      alt: (width: number, height: number) =>
        width > 0 && height > 0
          ? `Khung hình agent chọn thao tác trên đó, ${width}×${height}`
          : "Khung hình agent chọn thao tác trên đó",
      takenAt: (when: string) => `Ảnh chụp lúc ${when}; màn hình có thể đã đổi từ lúc đó.`,
      point: "Điểm thao tác",
      dropPoint: "Điểm thả",
    },
    // A frame whose id names no size gives none: the picture is still the screen.
    screenshotAlt: (width: number, height: number) =>
      width > 0 && height > 0 ? `Ảnh chụp màn hình ${width}×${height}` : "Ảnh chụp màn hình",
  },
} as const;
