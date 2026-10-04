/**
 * The kinds beyond markdown and code, as the fake server knows them, with a small canvas of each
 * as a test would seed it. A picture has no text: the store keeps its bytes and `/raw` serves
 * them, so the fake keeps a weight and an empty body, and its detail and versions say
 * `content: null` as the server's do.
 */

/** What a person can make from the web. `image` only comes in by import, so a create refuses it. */
export const CREATABLE_KINDS: readonly string[] = ["markdown", "code", "html", "svg", "mermaid"];

/** What every version of a picture weighs; the fake keeps no bytes. */
export const PICTURE_BYTES = 4096;

type Sample = { kind: string; title: string; content: string | null };

export const SAMPLES = {
  html: {
    kind: "html",
    title: "Trang hẹn giờ",
    content: "<!doctype html>\n<title>Hẹn giờ</title>\n<button>Bắt đầu</button>\n",
  },
  svg: {
    kind: "svg",
    title: "Hình tròn",
    content: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40"/></svg>\n',
  },
  mermaid: { kind: "mermaid", title: "Quy trình", content: "flowchart LR\n  A[Bắt đầu] --> B[Xong]\n" },
  image: { kind: "image", title: "Biểu đồ.png", content: null },
} satisfies Record<string, Sample>;
