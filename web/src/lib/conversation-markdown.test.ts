import { describe, expect, it } from "vitest";
import { vi } from "../i18n/vi";
import { FakeBackend, storedMessage } from "../test/fake-backend";
import { conversationMarkdown, exportStamp, markdownFileName } from "./conversation-markdown";

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
