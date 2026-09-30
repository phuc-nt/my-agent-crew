import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { agentFileUrl } from "../api/client";
import type { RunInfo, RunStep } from "../api/types";
import { vi } from "../i18n/vi";
import type { ThreadItem } from "../state/thread-reducer";
import { fakeRun } from "../test/fake-backend";
import { MessageThread, splitMedia } from "./message-thread";

const userItem: ThreadItem = { id: "m1", kind: "user", text: "tìm sách đi" };

function waiting(liveRun: RunInfo | null) {
  return render(
    <MessageThread
      items={[userItem]}
      streaming={null}
      busy
      liveRun={liveRun}
      onSuggestion={() => {}}
      echoOnly={false}
      agentId="master"
    />,
  );
}

const openTool: RunStep = {
  kind: "tool",
  name: "web_search",
  tool_call_id: "t1",
  arguments: {},
  ok: null,
  output: null,
  duration_ms: null,
};

describe("MessageThread while the agent is working", () => {
  it("names the tool the turn is blocked on instead of only saying it is thinking", () => {
    // The whole point of putting the header here: a reader who never opens the
    // rail still learns what the wait is for.
    waiting(fakeRun({ status: "running", steps: [openTool] }));
    expect(screen.getByTestId("thinking")).toHaveTextContent(vi.runDoing("web_search"));
  });

  it("counts the steps and the clock, so a long wait reads as progress not a hang", () => {
    waiting(
      fakeRun({
        status: "running",
        steps: [{ ...openTool, tool_call_id: "t0", ok: true, duration_ms: 20 }, openTool],
      }),
    );
    expect(screen.getByTestId("thinking")).toHaveTextContent(vi.runStepCount(1, 2));
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("says the plain word when no run has arrived yet", () => {
    // The gap between sending and the first activity event: there is nothing
    // truthful to show beyond the fact that something was sent.
    waiting(null);
    expect(screen.getByTestId("thinking")).toHaveTextContent(vi.thinking);
    expect(screen.queryByRole("progressbar")).toBeNull();
  });
});

describe("who gets their text formatted", () => {
  function thread(items: ThreadItem[]) {
    return render(
      <MessageThread
        items={items}
        streaming={null}
        busy={false}
        onSuggestion={() => {}}
        echoOnly={false}
        agentId="master"
      />,
    );
  }

  it("formats the agent's reply", () => {
    const { container } = thread([
      { id: "a1", kind: "assistant", text: "**ngủ đủ** giúp hồi phục", model: null },
    ]);
    expect(container.querySelector("strong")?.textContent).toBe("ngủ đủ");
  });

  it("leaves what the person typed exactly as they typed it", () => {
    // Someone who writes an asterisk means an asterisk; their message is not a
    // document the app gets to reinterpret.
    const { container } = thread([{ id: "m2", kind: "user", text: "**giữ nguyên** nhé" }]);
    expect(container.querySelector("strong")).toBeNull();
    expect(screen.getByTestId("message-user").textContent).toContain("**giữ nguyên**");
  });

  it("keeps images inline when a reply mixes prose and a MEDIA line", () => {
    const { container } = thread([
      { id: "a2", kind: "assistant", text: "**Biểu đồ**\nMEDIA: out/chart.png\nXong.", model: null },
    ]);
    expect(container.querySelector("strong")?.textContent).toBe("Biểu đồ");
    expect(container.querySelector("img.media")?.getAttribute("src")).toContain(
      encodeURIComponent("out/chart.png"),
    );
  });

  it("turns a FILE line into a download link rather than printing the path", () => {
    // The same reply text goes to Telegram, where the person receives the file itself.
    // Leaving the line unparsed would show the web reader a path instead.
    const { container } = thread([
      { id: "a3", kind: "assistant", text: "Bảng đây:\nFILE: out/so-lieu.csv", model: null },
    ]);
    const link = screen.getByTestId("message-file");
    expect(link.getAttribute("href")).toContain(encodeURIComponent("out/so-lieu.csv"));
    expect(link.getAttribute("download")).toBe("so-lieu.csv");
    expect(link.textContent).toBe(vi.attachmentDownload("so-lieu.csv"));
    expect(container.textContent).not.toContain("FILE:");
  });

  it("shows a photo and a document in one reply as their own two things", () => {
    thread([
      {
        id: "a4",
        kind: "assistant",
        text: "MEDIA: out/chart.png\nFILE: out/brief.pdf",
        model: null,
      },
    ]);
    expect(screen.getByTestId("message-file")).toBeInTheDocument();
    expect(screen.getByRole("img")).toBeInTheDocument();
  });
});

describe("what the person sent through Telegram", () => {
  const inbox = "/home/owner/.my-agent-crew/agents/default/workspace/inbox";
  function sent(text: string) {
    return render(
      <MessageThread
        items={[{ id: "u1", kind: "user", text }]}
        streaming={null}
        busy={false}
        onSuggestion={() => {}}
        echoOnly={false}
        agentId="default"
      />,
    );
  }

  it("turns a saved document line into a named download chip served from the agent's files", () => {
    const path = `${inbox}/20260925-081500-bao-cao.pdf`;
    const { container } = sent(`[Tệp đính kèm đã lưu: ${path}]\nxem giúp`);
    const chip = screen.getByTestId("attachment-file");
    expect(chip.getAttribute("href")).toBe(agentFileUrl("default", path));
    // The arrival stamp the channel prefixed is dropped: the sender named it bao-cao.pdf.
    expect(chip.getAttribute("download")).toBe("bao-cao.pdf");
    expect(chip).toHaveTextContent(vi.attachmentDownload("bao-cao.pdf"));
    expect(screen.getByTestId("message-user")).toHaveTextContent("xem giúp");
    expect(container.textContent).not.toContain("Tệp đính kèm đã lưu");
  });

  it("shows a photo as a thumbnail that opens the full file", () => {
    const path = `${inbox}/20260925-081500-file_12.jpg`;
    sent(`[Tệp đính kèm đã lưu: ${path}]`);
    const link = screen.getByTestId("attachment-image");
    expect(link.getAttribute("href")).toBe(agentFileUrl("default", path));
    expect(link.getAttribute("target")).toBe("_blank");
    expect(screen.getByRole("img", { name: vi.attachmentImage("file_12.jpg") })).toHaveAttribute(
      "src",
      agentFileUrl("default", path),
    );
  });

  it("leaves a sentence that only quotes the words as the person wrote it", () => {
    sent("Bot hay ghi [Tệp đính kèm đã lưu: x] ở đầu tin");
    expect(screen.queryByTestId("attachment-file")).toBeNull();
    expect(screen.getByTestId("message-user")).toHaveTextContent("[Tệp đính kèm đã lưu: x]");
  });

  // Only the whole line is the channel's: words before the bracket, or after it, are the person's.
  it("leaves a sentence that ends with the quoted words as written", () => {
    sent("Bot ghi thế này: [Tệp đính kèm đã lưu: x]");
    expect(screen.queryByTestId("attachment-file")).toBeNull();
    expect(screen.getByTestId("message-user")).toHaveTextContent("Bot ghi thế này: [Tệp đính kèm đã lưu: x]");
  });

  it("leaves a sentence that starts with the quoted words as written", () => {
    sent("[Tệp đính kèm đã lưu: x] là dòng bot ghi");
    expect(screen.queryByTestId("attachment-file")).toBeNull();
    expect(screen.getByTestId("message-user")).toHaveTextContent("[Tệp đính kèm đã lưu: x] là dòng bot ghi");
  });
});

describe("the actions under a reply", () => {
  it("sit under each finished agent reply but not under what the person typed", () => {
    render(
      <MessageThread
        items={[userItem, { id: "a1", kind: "assistant", text: "**xong**", model: null }]}
        streaming="đang viết"
        busy
        onSuggestion={() => {}}
        echoOnly={false}
        agentId="master"
      />,
    );
    expect(screen.getAllByTestId("bubble-actions")).toHaveLength(1);
    expect(screen.getByTestId("message-assistant")).toContainElement(screen.getByTestId("bubble-actions"));
    expect(screen.getByTestId("streaming").querySelector(".bubble-actions")).toBeNull();
  });
});

describe("the fork button under a saved user message", () => {
  const assistantItem: ThreadItem = { id: "a1", kind: "assistant", text: "trả lời", model: null };

  function thread(extra: { busy?: boolean; onFork?: (item: ThreadItem) => void } = {}) {
    return render(
      <MessageThread
        items={[userItem, assistantItem]}
        streaming={null}
        busy={extra.busy ?? false}
        onSuggestion={() => {}}
        echoOnly={false}
        agentId="master"
        onFork={extra.onFork}
      />,
    );
  }

  it("sits under the user bubble but not under the assistant's reply", () => {
    thread({ onFork: () => {} });
    expect(screen.getByTestId("message-user").querySelector(".fork-button")).not.toBeNull();
    expect(screen.getByTestId("message-assistant").querySelector(".fork-button")).toBeNull();
  });

  it("is absent without an onFork handler, even while idle", () => {
    thread();
    expect(screen.queryByTestId("message-user")?.querySelector(".fork-button")).toBeNull();
  });

  it("is hidden while the thread is busy", () => {
    thread({ busy: true, onFork: () => {} });
    expect(screen.getByTestId("message-user").querySelector(".fork-button")).toBeNull();
  });

  it("calls onFork with the item it sits under, not the conversation as a whole", () => {
    let picked: ThreadItem | null = null;
    thread({ onFork: (item) => (picked = item) });
    screen.getByTestId("message-user").querySelector<HTMLButtonElement>(".fork-button")?.click();
    expect(picked).toEqual(userItem);
  });
});

describe("splitMedia", () => {
  it("keeps the order the reply named its attachments in", () => {
    expect(splitMedia("a\nFILE: one.pdf\nb\nMEDIA: two.png\nc")).toEqual([
      { kind: "text", value: "a" },
      { kind: "file", value: "one.pdf" },
      { kind: "text", value: "b" },
      { kind: "media", value: "two.png" },
      { kind: "text", value: "c" },
    ]);
  });

  it("leaves a sentence that merely mentions the word as prose", () => {
    // Only a line that starts with the prefix is an attachment, so an agent explaining
    // the convention does not accidentally link to nothing.
    const text = "Dùng FILE: ở đầu dòng để gửi tệp";
    expect(splitMedia(`Mẹo: ${text}`)).toEqual([{ kind: "text", value: `Mẹo: ${text}` }]);
  });

  it("leaves a bare prefix with no path as prose", () => {
    // Otherwise it would become a download link aimed at the workspace root.
    expect(splitMedia("FILE:")).toEqual([{ kind: "text", value: "FILE:" }]);
  });
});
