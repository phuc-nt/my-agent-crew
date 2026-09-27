import { render } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { MarkdownBody } from "../components/markdown-body";
import { vi } from "../i18n/vi";
import { FakeBackend, storedMessage } from "../test/fake-backend";
import { conversationMarkdown, exportStamp, markdownFileName } from "./conversation-markdown";

/** The export's outline as a markdown reader draws it: every heading not nested in a block. */
function outline(markdown: string): string[] {
  const { container } = render(createElement(MarkdownBody, { text: markdown }));
  const headings = container.querySelectorAll(":is(h1, h2, h3, h4, h5, h6):is(.md > *)");
  return [...headings].map((h) => `${h.tagName.toLowerCase()} ${h.textContent}`);
}

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
