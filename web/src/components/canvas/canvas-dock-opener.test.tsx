import { act, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { type CanvasDock, useCanvasDock } from "../../hooks/use-canvas-dock";
import { vi } from "../../i18n/vi";
import type { WritingItem } from "../../lib/canvas-writing";
import { landed, startServer, stopServer } from "../../test/canvas-hook";
import { CanvasDockView } from "./canvas-dock";
import { CanvasButton } from "./canvas-dock-controls";

const CARD = "Xem từ thẻ";
const text = vi.canvas.writing;

type Mode = "column" | "overlay";

const draft: WritingItem = {
  key: 7,
  callId: null,
  updates: 2,
  rewrite: false,
  id: null,
  title: "Kế hoạch tuần",
  kind: "markdown",
  content: "Việc một",
  bytes: 12,
};

beforeEach(() => {
  const backend = startServer();
  backend.create({ title: "Một" });
  backend.canvas.add({ title: "Ghi chú", conversationIds: ["c1"] });
});

afterEach(stopServer);

const seen: { dock: CanvasDock | null } = { dock: null };

/** The dock as the chat lays it out, beside a thread that holds a card with a button of its own. */
function Chat({ mode, watching, card }: { mode: Mode; watching: boolean; card: boolean }) {
  const dock = useCanvasDock("c1", true, true);
  seen.dock = dock;
  const trigger = useRef<HTMLButtonElement>(null);
  return (
    <>
      <CanvasButton dock={dock} ref={trigger} />
      {card && <button type="button">{CARD}</button>}
      <textarea aria-label="Soạn tin" />
      <CanvasDockView
        dock={dock}
        mode={mode}
        activity={null}
        connected
        agentName={(id) => id}
        trigger={trigger}
        writing={watching ? { item: draft, asked: 1, onLeave: () => {} } : null}
      />
    </>
  );
}

async function openChat(mode: Mode) {
  const view = render(<Chat mode={mode} watching={false} card />);
  await landed();
  /** The chat shows the canvas being written, or puts it away, with or without the thread's card. */
  const draw = (watching: boolean, card = true) => act(() => view.rerender(<Chat mode={mode} watching={watching} card={card} />));
  return { showDraft: () => draw(true), leaveDraft: (card = true) => draw(false, card) };
}

/** The dock opens the stored canvas as a press of a card's button does, and closes as its own controls do. */
async function openNote() {
  act(() => seen.dock?.open("a1"));
  await landed();
}

async function closeDock() {
  await act(async () => seen.dock?.close());
  await landed();
}

const canvasButton = () => screen.getByRole("button", { name: vi.canvas.buttonLabel(1) });
const cardButton = () => screen.getByRole("button", { name: CARD });
const composer = () => screen.getByRole("textbox", { name: "Soạn tin" });
const closeButton = () => screen.getByRole("button", { name: text.close });
const inDock = () => document.querySelector(".dock-canvas")?.contains(document.activeElement) ?? false;

describe.each<Mode>(["overlay", "column"])("the keyboard as the %s dock closes on what the person opened from the thread", (mode) => {
  it("goes back to that button from a canvas being written", async () => {
    const { showDraft, leaveDraft } = await openChat(mode);
    cardButton().focus();
    showDraft();
    expect(closeButton()).toHaveFocus();

    leaveDraft();

    expect(cardButton()).toHaveFocus();
  });

  it("goes back to that button from a stored canvas", async () => {
    await openChat(mode);
    cardButton().focus();
    await openNote();
    expect(inDock()).toBe(true);

    await closeDock();

    expect(cardButton()).toHaveFocus();
  });

  it("goes to the Canvas button when the button that opened it is gone by then", async () => {
    const { showDraft, leaveDraft } = await openChat(mode);
    cardButton().focus();
    showDraft();

    leaveDraft(false);

    expect(canvasButton()).toHaveFocus();
  });

  it("goes to the Canvas button, not to a button that opened it an earlier time", async () => {
    const { showDraft, leaveDraft } = await openChat(mode);
    cardButton().focus();
    showDraft();
    leaveDraft();
    act(() => (document.activeElement as HTMLElement).blur());
    expect(document.body).toHaveFocus();

    await openNote();
    await closeDock();

    expect(canvasButton()).toHaveFocus();
  });

  it("goes back to the box when it was there as a press that did not take it opened the dock", async () => {
    const { showDraft, leaveDraft } = await openChat(mode);
    composer().focus();
    showDraft();
    expect(closeButton()).toHaveFocus();
    leaveDraft();
    expect(composer()).toHaveFocus();

    await openNote();
    expect(inDock()).toBe(true);
    await closeDock();

    expect(composer()).toHaveFocus();
  });

  it("goes to the Canvas button when it was nowhere as the dock opened", async () => {
    const { showDraft, leaveDraft } = await openChat(mode);
    showDraft();
    expect(closeButton()).toHaveFocus();

    leaveDraft();

    expect(canvasButton()).toHaveFocus();
  });

  it("stays in the box when the person took it back there before the dock closed", async () => {
    const { showDraft, leaveDraft } = await openChat(mode);
    cardButton().focus();
    showDraft();
    composer().focus();

    leaveDraft();

    expect(composer()).toHaveFocus();
  });
});
