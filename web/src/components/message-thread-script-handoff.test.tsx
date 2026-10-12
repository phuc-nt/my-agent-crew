import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { vi } from "../i18n/vi";
import { conversationMarkdown } from "../lib/conversation-markdown";
import type { ThreadItem } from "../state/thread-reducer";
import { FakeBackend, storedMessage } from "../test/fake-backend";
import { handedOn, lookalikes } from "../test/script-handoff-message";
import { MessageThread } from "./message-thread";

const PROMPT = "Tóm tắt các đơn mới cho tôi.";
const PRINTED = "2 đơn mới\n  - Tiki #123 · 250.000đ\n\n  - Shopee #456 · 99.000đ";
const STORED = handedOn(PROMPT, PRINTED);
const LONG = Array.from({ length: 40 }, (_, i) => `đơn ${i + 1}`).join("\n");

const user = (text: string, extra: Partial<Extract<ThreadItem, { kind: "user" }>> = {}): ThreadItem => ({ kind: "user", id: "7", text, ...extra });

function thread(items: ThreadItem[], onFork?: (item: ThreadItem) => void) {
  return render(
    <MessageThread items={items} streaming={null} busy={false} onSuggestion={() => {}} echoOnly={false} agentId="purchases" onFork={onFork} />,
  );
}

/** What the bubble says, without the name a screen reader hears before it. */
const said = () => screen.getByTestId("message-user").textContent?.replace(vi.you, "");

describe("the message a script job handed on", () => {
  it("is the schedule's prompt in the bubble, with no marker and no word of the sentence for the model", () => {
    thread([user(STORED)]);

    expect(said()).toBe(PROMPT);
    expect(document.body.textContent).not.toContain("SCRIPT_IN_RA");
    expect(document.body.textContent).not.toContain("DỮ LIỆU");
  });

  it("has what the script printed right under the bubble, labelled, exactly as printed", () => {
    thread([user(STORED), { kind: "assistant", id: "8", text: "Có 2 đơn mới.", model: null }]);

    const bubble = screen.getByTestId("message-user");
    const block = screen.getByRole("group", { name: vi.scriptHandoff.printed });
    expect(bubble.nextElementSibling).toBe(block);
    // Beside the bubble, not in it: the bubble is the person's words, and this is not.
    expect(bubble).not.toContainElement(block);
    expect(within(block).getByTestId("script-printed-text").textContent).toBe(PRINTED);
    expect(within(block).getByText(vi.scriptHandoff.asData)).toBeInTheDocument();
  });

  it("is open while short, says how long it is, and folds and opens when pressed", async () => {
    thread([user(STORED)]);
    const block = screen.getByTestId("script-printed");
    const toggle = within(block).getByRole("button", { name: vi.scriptHandoff.toggle(4) });

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveAttribute("aria-controls", within(block).getByTestId("script-printed-text").id);
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(within(block).queryByTestId("script-printed-text")).toBeNull();
    // What it was given as is said whether or not the text is open.
    expect(within(block).getByText(vi.scriptHandoff.asData)).toBeInTheDocument();
    await userEvent.click(toggle);
    expect(within(block).getByTestId("script-printed-text").textContent).toBe(PRINTED);
  });

  it("stays folded when long, until it is asked for, and is then all there", async () => {
    thread([user(handedOn(PROMPT, LONG))]);
    const block = screen.getByTestId("script-printed");
    const toggle = within(block).getByRole("button", { name: vi.scriptHandoff.toggle(40) });

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(within(block).queryByTestId("script-printed-text")).toBeNull();
    expect(said()).toBe(PROMPT);
    await userEvent.click(toggle);
    expect(within(block).getByTestId("script-printed-text").textContent).toBe(LONG);
  });

  it("can be reached and scrolled from the keyboard once open", async () => {
    thread([user(STORED)]);
    await userEvent.tab();
    expect(screen.getByRole("button", { name: vi.scriptHandoff.toggle(4) })).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByTestId("script-printed-text")).toHaveFocus();
  });

  it("keeps a prompt of several paragraphs, and the files a channel saved with it, as any message's", () => {
    const prompt = `Xem tệp này.\n[${vi.attachmentSaved}: inbox/20261012-074000-don.csv]\n\nRồi tóm tắt.`;
    thread([user(handedOn(prompt, PRINTED))]);

    expect(screen.getByTestId("attachment-file")).toBeInTheDocument();
    expect(screen.getByTestId("message-user")).toHaveTextContent("Rồi tóm tắt.");
    expect(screen.getByTestId("script-printed-text").textContent).toBe(PRINTED);
  });

  it("stands over the canvas note of a message that carries one too", () => {
    thread([user(STORED, { context: "[Canvas · Đơn hàng]\n> dòng 1" })]);

    const block = screen.getByTestId("script-printed");
    expect(screen.getByTestId("message-user").nextElementSibling).toBe(block);
    expect(block.nextElementSibling).toBe(screen.getByTestId("canvas-note"));
  });
});

describe("characters nobody would see in what a script printed", () => {
  // A right-to-left override and a zero-width space, as a tool hands them on from a web page.
  const SLY = "đơn \u202Egnp.exe\u200B mới";
  const SHOWN = "đơn [U+202E]gnp.exe[U+200B] mới";
  const RAW = /[\u202E\u200B]/;

  it("are written out as their code points in a text that is open, and again each time it is opened", async () => {
    thread([user(handedOn(PROMPT, SLY))]);
    const block = screen.getByTestId("script-printed");
    const toggle = within(block).getByRole("button", { name: vi.scriptHandoff.toggle(1) });

    expect(within(block).getByTestId("script-printed-text").textContent).toBe(SHOWN);
    expect(block.textContent).not.toMatch(RAW);
    await userEvent.click(toggle);
    expect(block.textContent).not.toMatch(RAW);
    await userEvent.click(toggle);
    expect(within(block).getByTestId("script-printed-text").textContent).toBe(SHOWN);
  });

  it("are drawn nowhere while a long text is folded, and written out once it is opened", async () => {
    thread([user(handedOn(PROMPT, `${LONG}\n${SLY}`))]);
    const block = screen.getByTestId("script-printed");
    // The text is as long as it is stored, not as long as it is drawn.
    const toggle = within(block).getByRole("button", { name: vi.scriptHandoff.toggle(41) });

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(block.textContent).not.toMatch(RAW);
    await userEvent.click(toggle);
    expect(within(block).getByTestId("script-printed-text").textContent).toBe(`${LONG}\n${SHOWN}`);
    expect(block.textContent).not.toMatch(RAW);
  });

  // 795 characters stored, and 802 once the one mark is written out: still short.
  it("do not make a text long by the room their marks take", () => {
    thread([user(handedOn(PROMPT, `${"x".repeat(794)}\u200B`))]);

    expect(screen.getByRole("button", { name: vi.scriptHandoff.toggle(1) })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("script-printed-text").textContent).toBe(`${"x".repeat(794)}[U+200B]`);
  });
});

describe("a message that is not exactly one handed on", () => {
  it.each(lookalikes(PROMPT, PRINTED))("is drawn as the plain message it is: %s", (_, text) => {
    thread([user(text)]);

    expect(said()).toBe(text);
    expect(screen.queryByTestId("script-printed")).toBeNull();
  });

  it("is drawn as the reply it is when the agent wrote the very same text", () => {
    thread([{ kind: "assistant", id: "8", text: STORED, model: null }]);

    expect(screen.getByTestId("message-assistant")).toHaveTextContent("SCRIPT_IN_RA 9f3a61c07be4d258>>>");
    expect(screen.queryByTestId("script-printed")).toBeNull();
  });
});

describe("what is sent again or copied of a handed-on message", () => {
  it("is the message as it is stored: the fork is handed the whole of it", async () => {
    const forked: ThreadItem[] = [];
    thread([user(STORED)], (item) => forked.push(item));

    await userEvent.click(screen.getByRole("button", { name: vi.fork.fromHere }));

    expect(forked).toEqual([user(STORED)]);
  });

  it("is the message as it is stored: the exported conversation holds every line of it", () => {
    const detail = new FakeBackend().create({ title: "Đơn mới", messages: [storedMessage("user", STORED)] });

    const exported = conversationMarkdown(detail, "Thủ kho");

    for (const line of STORED.split("\n")) expect(exported).toContain(line);
  });
});
