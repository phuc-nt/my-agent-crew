import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, expect, it, vi as vitest } from "vitest";
import type { MessageCanvas } from "../../api/artifact-types";
import type { PageReport } from "../../hooks/use-page-report";
import { vi } from "../../i18n/vi";
import { errorReport } from "../../lib/error-report";
import type { FrameError } from "../../lib/frame-messages";
import type { SendResult } from "../../lib/send-result";
import type { AskDisabled } from "./canvas-ask";
import { CanvasErrors } from "./canvas-errors";

const { pageErrors } = vi.canvas;

type Ask = (canvas: MessageCanvas, question: string) => Promise<SendResult>;

const error = (message: string, rest: Partial<FrameError> = {}): FrameError => ({
  message,
  source: "",
  line: 0,
  column: 0,
  ...rest,
});

const reportOf = (errors: FrameError[], rest: Partial<PageReport> = {}): PageReport => ({
  mount: 1,
  version: 4,
  count: errors.length,
  recent: errors,
  silenced: false,
  ...rest,
});

/** A promise that settles when the test says so, to look at a state while the step is still out. */
function held<T>() {
  let settle: (value: T) => void = () => {};
  const promise = new Promise<T>((resolve) => {
    settle = resolve;
  });
  return { promise, resolve: settle };
}

const accepted: Ask = async () => ({ status: "sent" });

/** An answer for each press of the button, in order, then acceptance. */
const answering =
  (...replies: SendResult[]): Ask =>
  async () =>
    replies.shift() ?? { status: "sent" };

type Setup = {
  report?: PageReport;
  disabled?: AskDisabled;
  flush?: () => Promise<number | null>;
  /** The chat's send; `false` leaves it out, as a panel with no chat beside it does. */
  ask?: Ask | false;
};

function setup({ report, disabled, flush, ask }: Setup = {}) {
  const saved = vitest.fn<() => Promise<number | null>>(flush ?? (async () => 4));
  const onAsk = vitest.fn<Ask>(ask || accepted);
  const props = {
    artifactId: "a1",
    title: "Trang chủ",
    report: report ?? reportOf([error("boom")]),
    disabled: disabled ?? null,
    flush: saved,
    onAsk: ask === false ? undefined : onAsk,
  };
  const view = render(<CanvasErrors {...props} />);
  const show = (next: Partial<ComponentProps<typeof CanvasErrors>>) =>
    view.rerender(<CanvasErrors {...props} {...next} />);
  return { ...view, flush: saved, onAsk, show };
}

const sendButton = () => screen.getByRole("button", { name: pageErrors.send }) as HTMLButtonElement;

/** Presses the send button and lets every step that needs no timer run. */
async function press() {
  await act(async () => {
    fireEvent.click(sendButton());
  });
}

const messages = (container: HTMLElement) =>
  Array.from(container.querySelectorAll(".canvas-error-message")).map((node) => node.textContent);

describe("the errors a page reported", () => {
  it("shows nothing while the page has reported nothing", () => {
    const { container } = setup({ report: reportOf([]) });

    expect(container.firstChild).toBeNull();
  });

  it("says how many errors the page reported, and keeps the list closed until asked", () => {
    const { container } = setup({ report: reportOf([error("boom")], { count: 25 }) });

    expect(screen.getByRole("group", { name: pageErrors.group })).toBeTruthy();
    expect(container.querySelector(".canvas-errors-count")?.textContent).toBe(pageErrors.count(25));
    expect(screen.getByRole("button", { name: pageErrors.show }).getAttribute("aria-expanded")).toBe("false");
    expect(container.querySelector(".canvas-errors-list")).toBeNull();
  });

  it("says the page may have reported more once the frame no longer hears it, however many reports it counted", () => {
    const counted = (count: number, silenced: boolean) =>
      setup({ report: reportOf([error("boom")], { count, silenced }) }).container.querySelector(".canvas-errors-count")?.textContent;

    expect(counted(49, false)).toBe(pageErrors.count(49));
    expect(counted(50, false)).toBe(pageErrors.count(50));
    expect(counted(50, false)).not.toContain("+");
    expect(counted(50, true)).toBe(pageErrors.count(50, true));
    expect(counted(50, true)).toContain("50+");
    // Some of the fifty messages were no reports: the page was heard out all the same.
    expect(counted(49, true)).toContain("49+");
    expect(counted(1, true)).toContain("1+");
  });

  it("says the page is no longer heard when it was heard out without one report, with nothing to list or send", () => {
    setup({ report: reportOf([], { silenced: true }) });

    const group = screen.getByRole("group", { name: pageErrors.group });
    expect(group.textContent).toBe(pageErrors.unheard);
    expect(within(group).getByRole("status").textContent).toBe(pageErrors.unheard);
    expect(pageErrors.unheard).toBe("Trang gửi quá nhiều tin nên lỗi nó báo từ đây không còn được nghe");
    expect(screen.queryAllByRole("button")).toEqual([]);
  });

  it("leaves saying so to the count once the page has reported something", () => {
    setup({ report: reportOf([error("boom")], { silenced: true }) });

    expect(screen.queryByText(pageErrors.unheard)).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
    expect(sendButton().disabled).toBe(false);
  });

  it("lists the errors it keeps, oldest first, when asked, and closes the list again", () => {
    const { container } = setup({
      report: reportOf([error("first"), error("second", { source: "app.js", line: 3, column: 7 })], { count: 9 }),
    });

    fireEvent.click(screen.getByRole("button", { name: pageErrors.show }));

    const hide = screen.getByRole("button", { name: pageErrors.hide });
    expect(hide.getAttribute("aria-expanded")).toBe("true");
    expect(messages(container)).toEqual(["first", "second"]);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0].querySelector(".canvas-error-place")).toBeNull();
    expect(items[1].querySelector(".canvas-error-place")?.textContent).toBe("app.js:3:7");

    fireEvent.click(hide);

    expect(container.querySelector(".canvas-errors-list")).toBeNull();
    expect(screen.getByRole("button", { name: pageErrors.show })).toBeTruthy();
  });

  it("draws what the page wrote as text and never as markup, with hidden characters as marks", () => {
    const markup = `<img src=x onerror="alert(1)"><b>bold</b>`;
    // A file named so that it reads as another: the override turns "gnp.js" round.
    const named = error("x", { source: "app\u202egnp.js", line: 3 });
    const { container } = setup({ report: reportOf([error(markup), error("ab‮cd"), named]) });

    fireEvent.click(screen.getByRole("button", { name: pageErrors.show }));

    expect(messages(container)).toEqual([markup, "ab[U+202E]cd", "x"]);
    expect(container.querySelector("img, b")).toBeNull();
    const places = [...container.querySelectorAll(".canvas-error-place")].map((each) => each.textContent);
    expect(places).toEqual(["app[U+202E]gnp.js:3"]);
  });
});

describe("sending the errors to the agent", () => {
  it("is offered only where there is a chat to send to", () => {
    setup({ ask: false });

    expect(screen.queryByRole("button", { name: pageErrors.send })).toBeNull();
    expect(screen.getByRole("button", { name: pageErrors.show })).toBeTruthy();
  });

  it("sends nothing until the button is pressed, however many errors arrive", () => {
    const { onAsk, flush, show } = setup({ report: reportOf([error("one")]) });

    fireEvent.click(screen.getByRole("button", { name: pageErrors.show }));
    show({ report: reportOf([error("one"), error("two")]) });
    show({ report: reportOf([error("one"), error("two"), error("three")]) });

    expect(onAsk).not.toHaveBeenCalled();
    expect(flush).not.toHaveBeenCalled();
  });

  it("saves the canvas, then sends the errors in one message that names the page and its version", async () => {
    const errors = [error("boom", { source: "page.html", line: 3, column: 7 }), error("late")];
    const { flush, onAsk } = setup({ report: reportOf(errors, { version: 9 }) });

    await press();

    expect(flush).toHaveBeenCalledTimes(1);
    expect(onAsk).toHaveBeenCalledTimes(1);
    expect(onAsk).toHaveBeenCalledWith({ artifact_id: "a1", selection: null }, errorReport("Trang chủ", 9, errors));
    expect(flush.mock.invocationCallOrder[0]).toBeLessThan(onAsk.mock.invocationCallOrder[0]);
  });

  it("sends the newest five of the errors the page reported, and counts those five", async () => {
    const kept = Array.from({ length: 5 }, (_, at) => error(`failure ${at + 21}`));
    const { onAsk } = setup({ report: reportOf(kept, { count: 25 }) });

    await press();

    expect(onAsk.mock.calls[0][1]).toBe(errorReport("Trang chủ", 4, kept));
    expect(screen.getByRole("status").textContent).toBe(pageErrors.sent(5));
  });

  it("holds the button while the save and the send are out, and sends once however often it is pressed", async () => {
    const saving = held<number | null>();
    const answer = held<SendResult>();
    const { flush, onAsk } = setup({ flush: () => saving.promise, ask: () => answer.promise });

    await press();
    expect(sendButton().disabled).toBe(true);
    fireEvent.click(sendButton());
    expect(onAsk).not.toHaveBeenCalled();

    await act(async () => saving.resolve(4));
    expect(onAsk).toHaveBeenCalledTimes(1);
    expect(sendButton().disabled).toBe(true);
    fireEvent.click(sendButton());

    await act(async () => answer.resolve({ status: "sent" }));
    expect(flush).toHaveBeenCalledTimes(1);
    expect(onAsk).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status").textContent).toBe(pageErrors.sent(1));
  });

  it("says the canvas was not saved, sends nothing, and lets the person try again", async () => {
    const versions: Array<number | null> = [null, 5];
    const { flush, onAsk } = setup({ flush: async () => versions.shift() ?? null });

    await press();

    expect(screen.getByRole("alert").textContent).toBe(pageErrors.notSaved);
    expect(onAsk).not.toHaveBeenCalled();
    expect(sendButton().disabled).toBe(false);

    await press();

    expect(flush).toHaveBeenCalledTimes(2);
    expect(onAsk).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe(pageErrors.sent(1));
  });

  it("shows the words of a send the server refused, and sends again on the next press", async () => {
    const refusal: SendResult = { status: "failed", error: "Cuộc trò chuyện đang bận" };
    const { onAsk } = setup({ ask: answering(refusal) });

    await press();

    expect(screen.getByRole("alert").textContent).toBe("Cuộc trò chuyện đang bận");
    expect(screen.queryByRole("status")).toBeNull();
    expect(sendButton().disabled).toBe(false);

    await press();

    expect(onAsk).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe(pageErrors.sent(1));
  });

  it("tells a send that threw, or a save that threw, in one general sentence", async () => {
    const throwing = async () => {
      throw new Error("socket closed");
    };
    const { unmount } = setup({ ask: throwing });
    await press();
    expect(screen.getByRole("alert").textContent).toBe(vi.sendFailed.other);
    expect(sendButton().disabled).toBe(false);
    unmount();

    const { onAsk } = setup({ flush: throwing });
    await press();
    expect(screen.getByRole("alert").textContent).toBe(vi.sendFailed.other);
    expect(onAsk).not.toHaveBeenCalled();
  });

  it("counts a queued message as sent, and stays off until the page reports something new", async () => {
    const { show } = setup({ report: reportOf([error("one"), error("two")]), ask: answering({ status: "queued" }) });

    await press();

    expect(screen.getByRole("status").textContent).toBe(pageErrors.sent(2));
    expect(sendButton().disabled).toBe(true);

    show({ report: reportOf([error("one"), error("two"), error("three")]) });

    expect(screen.queryByRole("status")).toBeNull();
    expect(sendButton().disabled).toBe(false);
  });

  it("sends the errors that were listed when it was pressed, not the ones that came while the save was out", async () => {
    const saving = held<number | null>();
    const before = [error("one")];
    const { onAsk, show } = setup({ report: reportOf(before), flush: () => saving.promise });

    await press();
    show({ report: reportOf([...before, error("two")]) });
    await act(async () => saving.resolve(4));

    expect(onAsk).toHaveBeenCalledTimes(1);
    expect(onAsk.mock.calls[0][1]).toBe(errorReport("Trang chủ", 4, before));
    // The newer error was not in what went, so it can still be sent.
    expect(screen.queryByRole("status")).toBeNull();
    expect(sendButton().disabled).toBe(false);
  });

  it.each(["busy", "pending", "budget"] as const)("is off while the chat is %s, and says why", (why) => {
    const { flush, onAsk } = setup({ disabled: why });

    expect(sendButton().disabled).toBe(true);
    expect(screen.getByText(vi.canvas.ask[why])).toBeTruthy();
    fireEvent.click(sendButton());

    expect(flush).not.toHaveBeenCalled();
    expect(onAsk).not.toHaveBeenCalled();
  });

  it("gives no reason for being off where there is no chat to send to", () => {
    setup({ ask: false, disabled: "busy" });

    expect(screen.queryByText(vi.canvas.ask.busy)).toBeNull();
  });

  it("is on, with no note, while the chat can take a message", () => {
    const { container } = setup();

    expect(sendButton().disabled).toBe(false);
    expect(container.querySelector(".canvas-ask-note")).toBeNull();
  });
});
