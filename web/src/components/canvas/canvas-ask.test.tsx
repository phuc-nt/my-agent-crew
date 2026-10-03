import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { vi } from "../../i18n/vi";
import {
  askButton,
  bar,
  cancelButton,
  excerpt,
  openBox,
  questionBox,
  sendButton,
  setupAsk,
  typeQuestion,
} from "../../test/canvas-ask";
import { EXCERPT_CHARS, LONGER_RATIO } from "./canvas-ask";

const ask = vi.canvas.ask;
const longer = () => screen.queryByText(ask.longer);

describe("the bar at the foot of a canvas that asks about a selected passage", () => {
  it("shows nothing while nothing is selected and the box is closed", () => {
    setupAsk({ selection: null });

    expect(bar()).toBeNull();
  });

  it("shows nothing while hidden, whatever is selected", () => {
    setupAsk({ hidden: true });

    expect(bar()).toBeNull();
  });

  it("shows what is selected, where it lies, and the way to ask about it", () => {
    setupAsk();

    expect(excerpt()).toBe("dòng hai dòng ba");
    expect(bar()).toHaveTextContent("Dòng 2–3 · 16 ký tự");
    expect(askButton()).toBeEnabled();
    expect(questionBox()).toBeNull();
  });

  it("names a passage on one line by that line alone", () => {
    setupAsk({ selection: { text: "chỉ một dòng", line_start: 4, line_end: 4, shown: 12 } });

    expect(bar()).toHaveTextContent("Dòng 4 · 12 ký tự");
    expect(bar()).not.toHaveTextContent("4–4");
  });

  it("counts characters as the server does, a pair of code units being one", () => {
    setupAsk({ selection: { text: "a😀b", line_start: 1, line_end: 1, shown: 3 } });

    expect(bar()).toHaveTextContent("Dòng 1 · 3 ký tự");
  });

  it("shows no more of a long passage than the excerpt allows, cut between whole characters", () => {
    setupAsk({ selection: { text: "😀".repeat(EXCERPT_CHARS + 20), line_start: 1, line_end: 1, shown: EXCERPT_CHARS + 20 } });

    const shown = Array.from(excerpt() ?? "");
    expect(shown.slice(0, EXCERPT_CHARS).every((char) => char === "😀")).toBe(true);
    expect(shown.slice(EXCERPT_CHARS)).toEqual(["…"]);
  });

  it("shows a passage that fits whole, without a mark of having been cut", () => {
    setupAsk({ selection: { text: "x".repeat(EXCERPT_CHARS), line_start: 1, line_end: 1, shown: EXCERPT_CHARS } });

    expect(excerpt()).toBe("x".repeat(EXCERPT_CHARS));
  });

  it("leaves the blanks around a passage out, so they do not count against the excerpt", () => {
    setupAsk({ selection: { text: `\t  ${"x".repeat(EXCERPT_CHARS)}  \n`, line_start: 1, line_end: 1, shown: EXCERPT_CHARS + 5 } });

    expect(excerpt()).toBe("x".repeat(EXCERPT_CHARS));
  });

  it("marks the characters that cannot be seen, so the person sees what the agent would be sent", () => {
    setupAsk({ selection: { text: "an\u{200B}toàn\u{202E}", line_start: 1, line_end: 1, shown: 8 } });

    expect(excerpt()).toBe("an[U+200B]toàn[U+202E]");
  });

  it("marks a byte-order mark though a pattern for spaces would take it for one, and joins the spaces after it", () => {
    setupAsk({ selection: { text: "a\u{FEFF}  b", line_start: 1, line_end: 1, shown: 4 } });

    expect(excerpt()).toBe("a[U+FEFF] b");
  });
});

describe("what is said when more is sent than was selected", () => {
  const shown = 10;
  const of = (length: number) => ({ text: "y".repeat(length), line_start: 1, line_end: 3, shown });

  it("says the whole lines go, and points to Sửa, when they hold much more than was chosen", () => {
    setupAsk({ selection: of(shown * LONGER_RATIO + 1) });

    expect(longer()).toBeInTheDocument();
  });

  it("counts in the bar the characters that go, not the ones that were chosen", () => {
    const sent = shown * LONGER_RATIO + 1;
    setupAsk({ selection: of(sent) });

    expect(bar()).toHaveTextContent(`Dòng 1–3 · ${sent} ký tự`);
  });

  it("says nothing of it when the lines hold what was chosen, or not much more", () => {
    setupAsk({ selection: of(shown) });
    expect(longer()).toBeNull();
  });

  it("says nothing of it up to the ratio", () => {
    setupAsk({ selection: of(shown * LONGER_RATIO) });
    expect(longer()).toBeNull();
  });
});

describe("the question box", () => {
  it("opens on the button, takes the cursor, and leaves the passage on show", () => {
    setupAsk();

    openBox();

    expect(questionBox()).toHaveFocus();
    expect(questionBox()).toHaveValue("");
    expect(askButton()).toBeNull();
    expect(excerpt()).toBe("dòng hai dòng ba");
    expect(bar()).toHaveTextContent("Dòng 2–3 · 16 ký tự");
  });

  it("keeps the selection on the page while the button is pressed", () => {
    setupAsk();

    const notPrevented = fireEvent.mouseDown(askButton() as HTMLElement);

    expect(notPrevented).toBe(false);
  });

  it("cannot be sent empty, or from spaces alone, by the button or by Enter", () => {
    const { props } = setupAsk();
    openBox();
    expect(sendButton()).toBeDisabled();

    typeQuestion("   \n ");
    expect(sendButton()).toBeDisabled();
    fireEvent.keyDown(questionBox() as HTMLElement, { key: "Enter" });

    expect(props.flush).not.toHaveBeenCalled();
    expect(props.onAsk).not.toHaveBeenCalled();
  });

  it("takes Enter and Escape from the page, and leaves Shift+Enter and the keys of a word being composed to the box", () => {
    setupAsk();
    openBox();
    const field = questionBox() as HTMLElement;

    // fireEvent answers false when the handler stopped the key's own effect, a line break for Enter.
    expect(fireEvent.keyDown(field, { key: "Enter", shiftKey: true })).toBe(true);
    expect(fireEvent.keyDown(field, { key: "Enter", isComposing: true })).toBe(true);
    expect(fireEvent.keyDown(field, { key: "Escape", isComposing: true })).toBe(true);
    expect(fireEvent.keyDown(field, { key: "Enter" })).toBe(false);
    expect(fireEvent.keyDown(field, { key: "Escape" })).toBe(false);
  });

  it("closes on Cancel, drops what was typed, and opens empty the next time", () => {
    setupAsk();
    openBox();
    typeQuestion("câu hỏi dở");

    fireEvent.click(cancelButton() as HTMLElement);

    expect(questionBox()).toBeNull();
    openBox();
    expect(questionBox()).toHaveValue("");
  });

  it("closes on Escape, drops what was typed, and keeps the passage on show", () => {
    setupAsk();
    openBox();
    typeQuestion("câu hỏi dở");

    fireEvent.keyDown(questionBox() as HTMLElement, { key: "Escape" });

    expect(questionBox()).toBeNull();
    expect(bar()).toHaveTextContent("Dòng 2–3");
    openBox();
    expect(questionBox()).toHaveValue("");
  });

  it("gives the cursor back to the button when it closes by Escape or Cancel, so the keyboard keeps its place", () => {
    setupAsk();
    openBox();
    fireEvent.keyDown(questionBox() as HTMLElement, { key: "Escape" });
    expect(askButton()).toHaveFocus();

    openBox();
    (cancelButton() as HTMLElement).focus();
    fireEvent.click(cancelButton() as HTMLElement);
    expect(askButton()).toHaveFocus();
  });

  it("leaves the cursor where it is when it closes with the cursor somewhere else", () => {
    setupAsk();
    openBox();
    const elsewhere = document.createElement("input");
    document.body.append(elsewhere);
    try {
      elsewhere.focus();

      fireEvent.click(cancelButton() as HTMLElement);

      expect(questionBox()).toBeNull();
      expect(elsewhere).toHaveFocus();
    } finally {
      elsewhere.remove();
    }
  });

  it("keeps the passage chosen as the person leaves the page for the box", () => {
    const { update } = setupAsk();
    openBox();

    update({ selection: null });

    expect(excerpt()).toBe("dòng hai dòng ba");
    expect(questionBox()).toBeInTheDocument();
  });

  it("follows another passage chosen while it is open, and keeps that one when the choice goes", () => {
    const { update } = setupAsk();
    openBox();
    typeQuestion("giữ câu này");

    update({ selection: { text: "đoạn khác", line_start: 7, line_end: 7, shown: 9 } });
    expect(excerpt()).toBe("đoạn khác");
    expect(bar()).toHaveTextContent("Dòng 7 · 9 ký tự");
    update({ selection: null });

    expect(excerpt()).toBe("đoạn khác");
    expect(questionBox()).toHaveValue("giữ câu này");
  });

  it("is gone while hidden and comes back as it was left", () => {
    const { update } = setupAsk();
    openBox();
    typeQuestion("câu hỏi");

    update({ hidden: true });
    expect(bar()).toBeNull();
    update({ hidden: false });

    expect(questionBox()).toHaveValue("câu hỏi");
  });
});

describe("why asking is off", () => {
  const reasons = ["busy", "pending", "budget"] as const;

  it.each(reasons)("turns the button off and says why when it is %s, and nothing of the other reasons", (reason) => {
    setupAsk({ disabled: reason });

    expect(askButton()).toBeDisabled();
    expect(screen.getByText(ask[reason])).toBeInTheDocument();
    for (const other of reasons.filter((r) => r !== reason)) expect(screen.queryByText(ask[other])).toBeNull();
  });

  it("says nothing of it, and offers the button, when asking is on", () => {
    setupAsk();

    for (const reason of reasons) expect(screen.queryByText(ask[reason])).toBeNull();
    expect(askButton()).toBeEnabled();
  });

  it("turns Gửi off with a box open, keeps the question where it can still be written, and gives it back", () => {
    const { props, update } = setupAsk();
    openBox();
    typeQuestion("câu hỏi");

    update({ disabled: "busy" });
    expect(sendButton()).toBeDisabled();
    expect(screen.getByText(ask.busy)).toBeInTheDocument();
    expect(questionBox()).not.toHaveAttribute("readonly");
    typeQuestion("câu hỏi dài hơn");
    expect(questionBox()).toHaveValue("câu hỏi dài hơn");
    fireEvent.keyDown(questionBox() as HTMLElement, { key: "Enter" });
    expect(props.flush).not.toHaveBeenCalled();

    update({ disabled: null });
    expect(sendButton()).toBeEnabled();
    expect(screen.queryByText(ask.busy)).toBeNull();
  });
});
