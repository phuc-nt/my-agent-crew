export const viNotices = {
  runInterrupted: "Bị ngắt giữa chừng: máy chủ khởi động lại hoặc kết nối bị đóng.",
  errorPrefix: "Lỗi: ",
  stopped: "Đã dừng lượt này.",
  busyConflict: "Cuộc trò chuyện đang chờ duyệt — hãy quyết định trước khi nhắn tiếp.",
  // Why a message did not go, for the box that gets its words back. Picked by status and
  // never copied from the server, some of whose refusals are in English.
  sendFailed: {
    tooFast: "Hàng chờ đã đầy hoặc bạn gửi quá nhanh — đợi lượt hiện tại xong rồi gửi tiếp.",
    // The server refused the passage that went with the message: the canvas changed under it.
    selection: "Đoạn đã chọn không còn khớp với canvas — chọn lại đoạn đó rồi gửi tiếp.",
    other: "Chưa gửi được tin này — thử lại sau một lúc.",
  },
  loadFailed: "Không tải được dữ liệu từ máy chủ.",
  loading: "Đang tải…",
  // One word per action wherever it is offered — asking again after a failure, the next
  // page of a list — so rewording it cannot leave two screens saying it differently.
  retry: "Thử lại",
  showMore: "Xem thêm",
  approvalsTab: "Duyệt",
  markdownImage: {
    // Said on the button that stands in for an image from another site until it is asked for.
    show: (host: string) => `Hiện ảnh từ ${host}`,
  },
  // A request that failed in a way the server did not put in words for people.
  requestErrors: {
    network: "Không gọi được máy chủ — kiểm tra kết nối rồi thử lại.",
    server: (status: number) => `Máy chủ gặp lỗi (HTTP ${status}); thử lại sau.`,
    notFound: "Máy chủ không còn thấy thứ này; tải lại trang để xem hiện giờ.",
    invalid: "Máy chủ không nhận giá trị này.",
    status: (status: number) => `Máy chủ từ chối (HTTP ${status}).`,
  },
} as const;
