import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import type { WritingItem } from "../lib/canvas-writing";
import type { ThreadItem } from "../state/thread-reducer";
import { MessageThread } from "./message-thread";

const text = vi.canvas.writing;
const asked: ThreadItem = { id: "m1", kind: "user", text: "viết kế hoạch đi" };

const writing = (fields: Partial<WritingItem> = {}): WritingItem => ({
  key: 1,
  callId: null,
  updates: 1,
  rewrite: false,
  id: null,
  title: "Kế hoạch tuần",
  kind: "markdown",
  content: "Việc một",
  bytes: 12,
  ...fields,
});

function thread(items: WritingItem[] | null, streaming: string | null = null) {
  const onShow = vitest.fn();
  render(
    <MessageThread
      items={[asked]}
      streaming={streaming}
      busy
      onSuggestion={() => {}}
      echoOnly={false}
      agentId="master"
      writing={items === null ? undefined : { items, onShow }}
    />,
  );
  return onShow;
}

const cards = () => screen.queryAllByTestId("canvas-writing-card");

describe("the thread while the agent writes a canvas", () => {
  it("draws a card for each canvas being written, in the order they started", () => {
    thread([writing(), writing({ key: 2, rewrite: true, title: "Ghi chú" })]);

    expect(cards()).toHaveLength(2);
    expect(within(cards()[0]).getByText("Kế hoạch tuần")).toBeInTheDocument();
    expect(within(cards()[0]).getByText(text.creating)).toBeInTheDocument();
    expect(within(cards()[1]).getByText("Ghi chú")).toBeInTheDocument();
    expect(within(cards()[1]).getByText(text.rewriting)).toBeInTheDocument();
  });

  it("asks to show the canvas whose card was pressed", () => {
    const onShow = thread([writing(), writing({ key: 2, title: "Ghi chú" })]);

    fireEvent.click(within(cards()[1]).getByRole("button", { name: text.showLabel("Ghi chú") }));

    expect(onShow.mock.calls).toEqual([[2]]);
  });

  it("puts the cards after the words of the reply that are arriving", () => {
    thread([writing()], "Để tôi viết kế hoạch.");

    const streaming = screen.getByTestId("streaming");
    expect(streaming.compareDocumentPosition(cards()[0]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(streaming.contains(cards()[0])).toBe(false);
  });

  it("says the agent is writing in place of saying it is thinking", () => {
    thread([writing()]);
    expect(screen.queryByTestId("thinking")).toBeNull();
  });

  it("says the agent is thinking as ever while no canvas is being written", () => {
    thread([]);

    expect(cards()).toEqual([]);
    expect(screen.getByTestId("thinking")).toHaveTextContent(vi.thinking);
  });

  it("draws no card where the screen does not follow the writing", () => {
    thread(null);

    expect(cards()).toEqual([]);
    expect(screen.getByTestId("thinking")).toBeInTheDocument();
  });
});
