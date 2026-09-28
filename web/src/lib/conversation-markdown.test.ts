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
