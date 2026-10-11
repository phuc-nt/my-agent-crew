import { render } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { MarkdownBody } from "../components/markdown-body";
import { vi } from "../i18n/vi";
import { FakeBackend, storedMessage } from "../test/fake-backend";
import { conversationMarkdown, exportStamp, markdownFileName } from "./conversation-markdown";

/** The export's outline as a markdown reader draws it: every heading, in a quote or a list too. */
function outline(markdown: string): string[] {
  const { container } = render(createElement(MarkdownBody, { text: markdown }));
  const headings = container.querySelectorAll("h1, h2, h3, h4, h5, h6");
  return [...headings].map((h) => `${h.tagName.toLowerCase()} ${h.textContent}`);
}

/** The export of one reply, then the owner's next turn: the one a reply that ran on would take. */
function replyThenTurn(reply: string): string {
  const detail = new FakeBackend().create({
    title: "t",
    messages: [
      storedMessage("assistant", reply, { created_at: "2026-09-24T23:31:00Z" }),
      storedMessage("user", "tiếp đi", { created_at: "2026-09-24T23:33:00Z" }),
    ],
  });
  return conversationMarkdown(detail, "Coach");
}

const REPLY = "h2 Coach · 25/09/2026 06:31 (UTC+7)";
const NEXT = "h2 Bạn · 25/09/2026 06:33 (UTC+7)";

describe("conversationMarkdown", () => {
  it("writes the title, then each turn under who spoke and when, on the owner's clock", () => {
    const detail = new FakeBackend().create({
      title: "Kế hoạch ngủ",
      messages: [
        // 23:30 UTC is already the next morning in Hanoi: the heading says 25/09, not 24/09.
        storedMessage("user", "Lập kế hoạch ngủ tuần này", { created_at: "2026-09-24T23:30:00Z" }),
        storedMessage("assistant", "", {
          created_at: "2026-09-24T23:30:05Z",
          tool_calls: [{ id: "t1", name: "read_file", arguments: {} }],
        }),
        storedMessage("tool", '{"ok": true}', { created_at: "2026-09-24T23:30:06Z", tool_call_id: "t1" }),
        storedMessage("assistant", "**Kế hoạch**\n- ngủ trước 23:00\n", {
          created_at: "2026-09-24T23:31:00Z",
        }),
      ],
    });

    expect(conversationMarkdown(detail, "Coach")).toBe(
      [
        "# Kế hoạch ngủ",
        "## Bạn · 25/09/2026 06:30 (UTC+7)",
        "Lập kế hoạch ngủ tuần này",
        "## Coach · 25/09/2026 06:31 (UTC+7)",
        "**Kế hoạch**\n- ngủ trước 23:00",
      ].join("\n\n") + "\n",
    );
  });

  it("leaves out the agent's working: tool results and replies that only called a tool", () => {
    const detail = new FakeBackend().create({
      title: "x",
      messages: [
        storedMessage("system", "persona"),
        storedMessage("assistant", "  "),
        storedMessage("tool", "output"),
      ],
    });
    expect(conversationMarkdown(detail, "Coach")).toBe("# x\n");
  });

  describe("what a script called on its own", () => {
    const search = { name: "mcp__notion__search", arguments: { query: "kế hoạch" }, ok: true, output: '{"pages": [1, 2, 3]}', ms: 120, cost_usd: null, metered: false };
    const missing = { name: "workspace_read", arguments: { path: "a.md" }, ok: false, output: "không có tệp", ms: 4, cost_usd: null, metered: false };
    const paid = { name: "pdf_read", arguments: { path: "a.pdf" }, ok: true, output: "Tổng chi 4,2 triệu.", ms: 1_500, cost_usd: 0.004, metered: true };
    const unpriced = { ...paid, name: "image_read", cost_usd: null };
    const kept = (calls: unknown, received: number | null = 60, printed: number | null = 8) =>
      JSON.stringify({ calls, received_chars: received, printed_chars: printed });
    const SCRIPT = { id: "s1", name: "tool_script", arguments: { script: "print(1)" } };
    /** The turn of a script: asked, the script written (with `said` or with no word), its result, the reply. */
    const turn = (context: string, said = "") => [
      storedMessage("user", "Gom ghi chú tuần này", { created_at: "2026-09-24T23:30:00Z" }),
      storedMessage("assistant", said, { created_at: "2026-09-24T23:30:05Z", tool_calls: [SCRIPT] }),
      storedMessage("tool", "đọc xong", { created_at: "2026-09-24T23:30:09Z", tool_call_id: "s1", context }),
      storedMessage("assistant", "Có 3 trang.", { created_at: "2026-09-24T23:31:00Z" }),
    ];
    const exported = (messages: ReturnType<typeof turn>) => conversationMarkdown(new FakeBackend().create({ title: "Ghi chú", messages }), "Coach");

    it("is listed under the agent's name, between what was asked and the reply it rests on", () => {
      expect(exported(turn(kept([search, missing, paid, unpriced])))).toBe(
        [
          "# Ghi chú",
          "## Bạn · 25/09/2026 06:30 (UTC+7)",
          "Gom ghi chú tuần này",
          // The script was written without a word, so its calls open the agent's turn.
          "## Coach · 25/09/2026 06:30 (UTC+7)",
          "Script đã thực hiện 4 lời gọi · 1 lần lỗi:",
          "1. `mcp__notion__search` · 120 ms\n2. `workspace_read` · lỗi · 4 ms\n3. `pdf_read` · 1.5 giây · $0.0040\n4. `image_read` · 1.5 giây · không rõ giá",
          "## Coach · 25/09/2026 06:31 (UTC+7)",
          "Có 3 trang.",
        ].join("\n\n") + "\n",
      );
    });

    it("goes under what the agent said as it wrote the script, with no second heading", () => {
      expect(exported(turn(kept([search]), "Để mình đọc Notion."))).toBe(
        [
          "# Ghi chú",
          "## Bạn · 25/09/2026 06:30 (UTC+7)",
          "Gom ghi chú tuần này",
          "## Coach · 25/09/2026 06:30 (UTC+7)",
          "Để mình đọc Notion.",
          "Script đã thực hiện 1 lời gọi:",
          "1. `mcp__notion__search` · 120 ms",
          "## Coach · 25/09/2026 06:31 (UTC+7)",
          "Có 3 trang.",
        ].join("\n\n") + "\n",
      );
    });

    it("keeps two scripts of one turn under the one heading, each with its own list", () => {
      const again = { ...SCRIPT, id: "s2" };
      const messages = [
        storedMessage("assistant", "", { created_at: "2026-09-24T23:30:05Z", tool_calls: [SCRIPT, again] }),
        storedMessage("tool", "một", { created_at: "2026-09-24T23:30:09Z", tool_call_id: "s1", context: kept([search]) }),
        storedMessage("tool", "hai", { created_at: "2026-09-24T23:30:12Z", tool_call_id: "s2", context: kept([missing, missing]) }),
      ];
      expect(exported(messages)).toBe(
        [
          "# Ghi chú",
          "## Coach · 25/09/2026 06:30 (UTC+7)",
          "Script đã thực hiện 1 lời gọi:",
          "1. `mcp__notion__search` · 120 ms",
          "Script đã thực hiện 2 lời gọi · 2 lần lỗi:",
          "1. `workspace_read` · lỗi · 4 ms\n2. `workspace_read` · lỗi · 4 ms",
        ].join("\n\n") + "\n",
      );
    });

    it("writes neither what a call was asked nor what it answered: the export stays free of JSON", () => {
      const text = exported(turn(kept([search, missing])));
      for (const working of ["kế hoạch", "pages", "a.md", "không có tệp", "đọc xong", "print(1)"]) expect(text).not.toContain(working);
    });

    it("reads as a numbered list under the agent's heading, and adds no heading of its own", () => {
      const text = exported(turn(kept([search, missing])));
      expect(outline(text)).toEqual([
        "h1 Ghi chú",
        "h2 Bạn · 25/09/2026 06:30 (UTC+7)",
        "h2 Coach · 25/09/2026 06:30 (UTC+7)",
        "h2 Coach · 25/09/2026 06:31 (UTC+7)",
      ]);
      const { container } = render(createElement(MarkdownBody, { text }));
      expect([...container.querySelectorAll("ol > li")].map((item) => item.textContent)).toEqual([
        "mcp__notion__search · 120 ms",
        "workspace_read · lỗi · 4 ms",
      ]);
      expect([...container.querySelectorAll("ol code")].map((name) => name.textContent)).toEqual(["mcp__notion__search", "workspace_read"]);
    });

    const PLAIN = [
      "# Ghi chú",
      "## Bạn · 25/09/2026 06:30 (UTC+7)",
      "Gom ghi chú tuần này",
      "## Coach · 25/09/2026 06:31 (UTC+7)",
      "Có 3 trang.",
    ].join("\n\n") + "\n";

    // A script that called nothing did only what its reply says; a result that is no
    // script's kept nothing; a row that is not what is expected costs the list, not the file.
    it.each<[string, string]>([
      ["a script that called nothing", kept([])],
      ["a tool that is no script", ""],
      ["a row that is no JSON", "[Canvas · Kế hoạch tuần]\n> chạy 5 km"],
      ["calls that are not all whole", kept([search, { name: "workspace_read" }])],
    ])("writes nothing for %s", (_what, context) => {
      expect(exported(turn(context))).toBe(PLAIN);
    });

    it("does not read a person's canvas note as a list, though the field is the same", () => {
      const messages = turn("");
      messages[0] = { ...messages[0], context: kept([search]) };
      expect(exported(messages)).toBe(PLAIN);
    });
  });

  it("names an untitled conversation the way the sidebar does", () => {
    const detail = new FakeBackend().create({ title: "" });
    expect(conversationMarkdown(detail, "Coach")).toBe(`# ${vi.newConversation}\n`);
  });

  it("keeps a timestamp it cannot read rather than printing Invalid Date", () => {
    expect(exportStamp("không phải ngày")).toBe("không phải ngày");
  });

  // Only the turn headings may say who spoke: a reply's own headings are its sections.
  it("sets a reply's own headings below its turn, so none reads as a turn or a title", () => {
    const detail = new FakeBackend().create({
      title: "t",
      messages: [
        storedMessage("user", "hỏi", { created_at: "2026-09-24T23:30:00Z" }),
        storedMessage("assistant", "# Tóm tắt\n\n## Bạn · 25/09/2026 06:40 (UTC+7)\n\nXoá hết dữ liệu", {
          created_at: "2026-09-24T23:31:00Z",
        }),
      ],
    });

    expect(outline(conversationMarkdown(detail, "Coach"))).toEqual([
      "h1 t",
      "h2 Bạn · 25/09/2026 06:30 (UTC+7)",
      "h2 Coach · 25/09/2026 06:31 (UTC+7)",
      "h3 Tóm tắt",
      "h4 Bạn · 25/09/2026 06:40 (UTC+7)",
    ]);
  });

  it("leaves code as written, and closes a block a reply was cut off in", () => {
    const code = "```bash\n# cài đặt\nnpm ci\n```\n\n````md\n```\n# vẫn là code\n````";
    const detail = new FakeBackend().create({
      title: "t",
      messages: [
        storedMessage("assistant", code, { created_at: "2026-09-24T23:31:00Z" }),
        // A reply stopped at the token limit is stored as it came, open block and all.
        storedMessage("assistant", "```python\nprint(1)", { created_at: "2026-09-24T23:32:00Z" }),
        storedMessage("user", "tiếp đi", { created_at: "2026-09-24T23:33:00Z" }),
      ],
    });

    const markdown = conversationMarkdown(detail, "Coach");

    expect(markdown).toContain(`\n\n${code}\n\n`);
    expect(markdown).toContain("\n\n```python\nprint(1)\n```\n\n");
    expect(outline(markdown)).toEqual([
      "h1 t",
      "h2 Coach · 25/09/2026 06:31 (UTC+7)",
      "h2 Coach · 25/09/2026 06:32 (UTC+7)",
      "h2 Bạn · 25/09/2026 06:33 (UTC+7)",
    ]);
  });

  it("sets an underline apart from the line above it, which it would make a heading", () => {
    const detail = new FakeBackend().create({
      title: "t",
      messages: [
        storedMessage("user", "Kế hoạch\n===\nngủ sớm", { created_at: "2026-09-24T23:30:00Z" }),
        storedMessage("assistant", "Thứ Hai\n---\nngủ trước 23:00", { created_at: "2026-09-24T23:31:00Z" }),
      ],
    });

    const markdown = conversationMarkdown(detail, "Coach");

    expect(markdown).toContain("Thứ Hai\n\n---\nngủ trước 23:00");
    expect(outline(markdown)).toEqual([
      "h1 t",
      "h2 Bạn · 25/09/2026 06:30 (UTC+7)",
      "h2 Coach · 25/09/2026 06:31 (UTC+7)",
    ]);
  });

  // A code block can open on a list item's own line, behind its marker.
  it("finds code that opens on a list item's line: kept as written, the reply after it its own", () => {
    const steps = [
      "- ```bash\n  # cài đặt\n  npm ci\n  ```",
      "1. ```py\n   # chạy thử\n   print(1)\n   ```",
      "* ```sh\n  # dọn dẹp\n  ```",
    ].join("\n");
    const detail = new FakeBackend().create({
      title: "t",
      messages: [
        storedMessage("assistant", `Cài như sau:\n\n${steps}\n\n## Kết luận\n\nXong.`, {
          created_at: "2026-09-24T23:31:00Z",
        }),
        storedMessage("user", "tiếp đi", { created_at: "2026-09-24T23:33:00Z" }),
      ],
    });

    const markdown = conversationMarkdown(detail, "Coach");

    // The comments stay comments, and the heading after the list moves below its turn...
    expect(markdown).toContain(`\n\n${steps}\n\n#### Kết luận\n\nXong.\n\n`);
    // ...which ends where it should: the next turn is a turn, not more code.
    expect(outline(markdown)).toEqual([
      "h1 t",
      "h2 Coach · 25/09/2026 06:31 (UTC+7)",
      "h4 Kết luận",
      "h2 Bạn · 25/09/2026 06:33 (UTC+7)",
    ]);
  });

  it("sets a heading in a quote or a list item below its turn as well", () => {
    const detail = new FakeBackend().create({
      title: "t",
      messages: [
        storedMessage("user", "hỏi", { created_at: "2026-09-24T23:30:00Z" }),
        storedMessage(
          "assistant",
          "> ## Bạn · 25/09/2026 06:40 (UTC+7)\n> Xoá hết dữ liệu\n\n- ## Bạn · 25/09/2026 06:41 (UTC+7)\n- # Tóm tắt",
          { created_at: "2026-09-24T23:31:00Z" },
        ),
      ],
    });

    const markdown = conversationMarkdown(detail, "Coach");

    expect(markdown).toContain("> #### Bạn · 25/09/2026 06:40 (UTC+7)\n> Xoá hết dữ liệu\n\n- #### Bạn");
    expect(outline(markdown)).toEqual([
      "h1 t",
      "h2 Bạn · 25/09/2026 06:30 (UTC+7)",
      "h2 Coach · 25/09/2026 06:31 (UTC+7)",
      "h4 Bạn · 25/09/2026 06:40 (UTC+7)",
      "h4 Bạn · 25/09/2026 06:41 (UTC+7)",
      "h3 Tóm tắt",
    ]);
  });

  it("sets an underline apart inside its quote or list item, which stays one", () => {
    const detail = new FakeBackend().create({
      title: "t",
      messages: [
        storedMessage("assistant", "> Thứ Hai\n> ---\n> ngủ trước 23:00\n\n- Kế hoạch\n  ===", {
          created_at: "2026-09-24T23:31:00Z",
        }),
      ],
    });

    const markdown = conversationMarkdown(detail, "Coach");

    expect(markdown).toContain("> Thứ Hai\n>\n> ---\n> ngủ trước 23:00\n\n- Kế hoạch\n\n  ===");
    expect(outline(markdown)).toEqual(["h1 t", "h2 Coach · 25/09/2026 06:31 (UTC+7)"]);
    const { container } = render(createElement(MarkdownBody, { text: markdown }));
    expect(container.querySelectorAll("blockquote")).toHaveLength(1);
  });

  // A block cut off inside a list item ends with the item, when the next turn's heading
  // starts at the margin; a fence closed at the margin would open one there instead.
  it("leaves a block cut off inside a list item to end with the item, before the next turn", () => {
    const detail = new FakeBackend().create({
      title: "t",
      messages: [
        storedMessage("assistant", "- ```sh\n  npm ci", { created_at: "2026-09-24T23:32:00Z" }),
        storedMessage("user", "tiếp đi", { created_at: "2026-09-24T23:33:00Z" }),
      ],
    });

    const markdown = conversationMarkdown(detail, "Coach");

    expect(markdown).toContain("\n\n- ```sh\n  npm ci");
    expect(outline(markdown)).toEqual([
      "h1 t",
      "h2 Coach · 25/09/2026 06:32 (UTC+7)",
      "h2 Bạn · 25/09/2026 06:33 (UTC+7)",
    ]);
  });

  // Only a run of the mark that opened a block, at least as long, ends it. Taken for its end,
  // any other fence line would leave the block open over every turn after it.
  it.each([
    ["a backtick fence inside a tilde one", "Ví dụ:\n\n~~~md\n```bash\nnpm ci\n```", "~~~"],
    ["a shorter fence inside a longer one", "Ví dụ:\n\n````md\n```bash\nnpm ci\n```", "````"],
    ["the fence that opened it", "Lệnh:\n\n```", "```"],
  ])("closes a cut-off block whose last line is a fence that does not end it: %s", (_, reply, mark) => {
    const markdown = replyThenTurn(reply);

    expect(markdown).toContain(`\n\n${reply}\n${mark}\n\n## Bạn`);
    expect(outline(markdown)).toEqual(["h1 t", REPLY, NEXT]);
  });

  it.each([
    ["a tilde block holding a backtick line", "~~~md\n```\n# vẫn là code\n~~~"],
    ["a block closed by a fence three spaces in", "```bash\nnpm ci\n   ```"],
  ])("leaves a closed block at the end of a reply as written: %s", (_, reply) => {
    const markdown = replyThenTurn(reply);

    expect(markdown).toContain(`\n\n${reply}\n\n## Bạn`);
    expect(outline(markdown)).toEqual(["h1 t", REPLY, NEXT]);
  });

  // Backticks that open and close on the same line are inline code, however many there are.
  it("leaves triple backticks closed on their own line as inline code, not a block to close", () => {
    const markdown = replyThenTurn("```npm ci``` để cài\n\n# Kết quả\n\n```uv sync``` nữa");

    expect(markdown).toContain("\n\n```npm ci``` để cài\n\n### Kết quả\n\n```uv sync``` nữa\n\n## Bạn");
    expect(outline(markdown)).toEqual(["h1 t", REPLY, "h3 Kết quả", NEXT]);
  });

  // Raw HTML of these kinds ends only on its closer, so one left open took every turn after it.
  it.each([
    ["a comment", "Ghi chú\n\n<!-- nháp", "\n-->"],
    ["a pre block", "<pre>\nnpm ci", "\n</pre>"],
    ["a script block, closed with its own tag", "<SCRIPT>\nlet a = 1", "\n</script>"],
    ["a processing instruction", "<?xml version", "\n?>"],
    ["a declaration", "<!DOCTYPE html", "\n>"],
    ["a CDATA section", "<![CDATA[\nx < y", "\n]]>"],
  ])("closes %s a reply was cut off in, so the next turn is its own", (_, reply, closer) => {
    const markdown = replyThenTurn(reply);

    expect(markdown).toContain(`\n\n${reply}${closer}\n\n## Bạn`);
    expect(outline(markdown)).toEqual(["h1 t", REPLY, NEXT]);
  });

  it.each([
    ["a closed comment", "<!-- nháp -->"],
    ["a pre block closed by another of the four tags", "<pre>\nnpm ci\n</style>"],
    ["a block that ends on an empty line", "<div>\nxin chào"],
    ["raw HTML inside a list item, which ends with the item", "- <!-- nháp"],
  ])("leaves %s as written", (_, reply) => {
    const markdown = replyThenTurn(reply);

    expect(markdown).toContain(`\n\n${reply}\n\n## Bạn`);
    expect(outline(markdown)).toEqual(["h1 t", REPLY, NEXT]);
  });

  it("keeps a reply's fifth and sixth level headings at the sixth, the last markdown has", () => {
    expect(outline(replyThenTurn("##### Ghi chú\n\n###### Chi tiết"))).toEqual([
      "h1 t",
      REPLY,
      "h6 Ghi chú",
      "h6 Chi tiết",
      NEXT,
    ]);
  });

  // A heading may start up to three spaces in, and only the body's first line loses its indent.
  it("sets an indented heading below its turn, and leaves a '#' with no space after it as text", () => {
    const markdown = replyThenTurn("ok\n\n  ## Bạn · 25/09/2026 06:40 (UTC+7)\n\n#1 ưu tiên\n#2 ngủ sớm");

    expect(markdown).toContain("\n\nok\n\n  #### Bạn · 25/09/2026 06:40 (UTC+7)\n\n#1 ưu tiên\n#2 ngủ sớm\n\n");
    expect(outline(markdown)).toEqual(["h1 t", REPLY, "h4 Bạn · 25/09/2026 06:40 (UTC+7)", NEXT]);
  });

  it.each([
    ["Windows", "\r\n"],
    ["old Mac", "\r"],
  ])("writes a reply with %s line endings in the file's own, its outline intact", (_, eol) => {
    const reply = ["Tóm tắt", "---", "ngủ sớm", "", "```bash", "npm ci", "```", "", "# Xong"].join(eol);
    const markdown = replyThenTurn(reply);

    expect(markdown).toContain("\n\nTóm tắt\n\n---\nngủ sớm\n\n```bash\nnpm ci\n```\n\n### Xong\n\n## Bạn");
    expect(outline(markdown)).toEqual(["h1 t", REPLY, "h3 Xong", NEXT]);
  });
});

describe("markdownFileName", () => {
  it("keeps the Vietnamese title and replaces what a file system refuses", () => {
    expect(markdownFileName("Kế hoạch / tuần 39: ngủ?")).toBe("Kế hoạch - tuần 39- ngủ.md");
  });

  it("falls back to the untitled name", () => {
    expect(markdownFileName("  ")).toBe(`${vi.newConversation}.md`);
    expect(markdownFileName("...")).toBe(`${vi.newConversation}.md`);
  });
});
