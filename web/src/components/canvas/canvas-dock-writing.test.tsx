import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { type CanvasDock, useCanvasDock } from "../../hooks/use-canvas-dock";
import { vi } from "../../i18n/vi";
import type { WritingItem } from "../../lib/canvas-writing";
import { landed, startServer, stopServer } from "../../test/canvas-hook";
import { typeInto } from "../../test/canvas-panel";
import { CanvasDockView } from "./canvas-dock";
import { CanvasButton } from "./canvas-dock-controls";

const ACTIVITY = "Các bước của lượt chạy";
const text = vi.canvas.writing;

type Mode = "column" | "overlay";
type Shown = { item: WritingItem; asked: number | null } | null;

const item = (fields: Partial<WritingItem> = {}): WritingItem => ({
  key: 7,
  callId: null,
  updates: 2,
  rewrite: false,
  id: null,
  title: "Kế hoạch tuần",
  kind: "markdown",
  content: "Việc một",
  bytes: 12,
  ...fields,
});

/** A canvas being written that came up by itself, and one the person asked to see. */
const unasked: Shown = { item: item(), asked: null };
const askedFor: Shown = { item: item(), asked: 1 };

beforeEach(() => {
  const backend = startServer();
  backend.create({ title: "Một" });
  backend.canvas.add({ title: "Ghi chú", conversationIds: ["c1"] });
});

afterEach(() => {
  stopServer();
  vitest.unstubAllGlobals();
});

const seen: { dock: CanvasDock | null } = { dock: null };

/** The dock as the chat lays it out, with the canvas being written the chat hands it. */
function Chat({ mode, shown, onLeave }: { mode: Mode; shown: Shown; onLeave(): void }) {
  const dock = useCanvasDock("c1", true, true);
  seen.dock = dock;
  const trigger = useRef<HTMLButtonElement>(null);
  return (
    <>
      <CanvasButton dock={dock} ref={trigger} showing={shown !== null} onLeave={onLeave} />
      <textarea aria-label="Soạn tin" />
      <CanvasDockView
        dock={dock}
        mode={mode}
        activity={<button type="button">{ACTIVITY}</button>}
        connected
        agentName={(id) => id}
        trigger={trigger}
        writing={shown && { ...shown, onLeave }}
      />
    </>
  );
}

async function openChat(mode: Mode, shown: Shown = null) {
  const onLeave = vitest.fn();
  const view = render(<Chat mode={mode} shown={shown} onLeave={onLeave} />);
  await landed();
  /** The chat shows `next`, or nothing being written; `also` happens in the same draw. */
  const show = (next: Shown, also?: () => void) =>
    act(() => {
      also?.();
      view.rerender(<Chat mode={mode} shown={next} onLeave={onLeave} />);
    });
  return { onLeave, show };
}

async function openNote() {
  act(() => seen.dock?.open("a1"));
  await landed();
}

const canvasButton = () => screen.getByRole("button", { name: vi.canvas.buttonLabel(1) });
const composer = () => screen.getByRole("textbox", { name: "Soạn tin" });
const frame = () => screen.queryByTestId("canvas-writing");
const closeButton = () => screen.getByRole("button", { name: text.close });
const backToChat = () => screen.getByRole("button", { name: vi.canvas.backToChat });
const section = () => document.querySelector("#dock-canvas") as HTMLElement;
const held = () => document.querySelector(".dock-held") as HTMLElement;
const parts = () => Array.from(section().children).map((child) => child.className || child.getAttribute("data-testid"));

describe("a canvas being written in the dock beside a wide conversation", () => {
  it("opens the dock on its canvas tab though nothing was open, and gives the column back afterwards", async () => {
    const { show } = await openChat("column");
    expect(document.querySelector(".canvas-dock")).toHaveClass("closed");

    show(unasked);

    expect(document.querySelector(".canvas-dock")).toHaveClass("column");
    expect(screen.getByRole("tab", { name: vi.canvas.tabs.canvas })).toHaveAttribute("aria-selected", "true");
    expect(section()).toContainElement(frame());
    expect(held()).toBeEmptyDOMElement();
    expect(screen.getByText(ACTIVITY)).not.toBeVisible();
    expect(canvasButton()).toHaveAttribute("aria-expanded", "true");
    expect(seen.dock?.view).toBe("closed");

    show(null);

    expect(document.querySelector(".canvas-dock")).toHaveClass("closed");
    expect(screen.queryByRole("tablist")).toBeNull();
    expect(frame()).toBeNull();
    expect(screen.getByText(ACTIVITY)).toBeVisible();
    expect(canvasButton()).toHaveAttribute("aria-expanded", "false");
  });

  it("stands before the canvas the dock held, which waits behind it with what the person typed", async () => {
    const { show } = await openChat("column");
    await openNote();
    fireEvent.click(screen.getByRole("button", { name: vi.canvas.edit }));
    typeInto("chữ đang gõ dở");
    const panel = document.querySelector(".canvas-panel");
    expect(parts()).toEqual(["dock-held"]);

    show(askedFor);

    expect(parts()).toEqual(["canvas-writing", "dock-held"]);
    expect(held()).not.toBeVisible();
    expect(held().querySelector(".canvas-panel")).toBe(panel);
    expect(screen.queryByRole("textbox", { name: vi.canvas.editor })).toBeNull();
    expect(screen.getByRole("textbox", { name: vi.canvas.editor, hidden: true })).toHaveValue("chữ đang gõ dở");

    show(null);

    expect(parts()).toEqual(["dock-held"]);
    expect(held()).toBeVisible();
    expect(document.querySelector(".canvas-panel")).toBe(panel);
    expect(screen.getByRole("textbox", { name: vi.canvas.editor })).toHaveValue("chữ đang gõ dở");
  });

  it("hides the list behind it", async () => {
    const { show } = await openChat("column");
    fireEvent.click(canvasButton());
    await landed();

    show(unasked);
    expect(screen.queryByRole("button", { name: vi.canvas.newCanvas })).toBeNull();

    show(null);
    expect(screen.getByRole("button", { name: vi.canvas.newCanvas })).toBeVisible();
  });
});

describe("a canvas being written over a narrow conversation", () => {
  it("covers the chat with the way back first, though nothing was open", async () => {
    const { show } = await openChat("overlay");
    expect(document.querySelector(".canvas-dock")).toBeNull();

    show(askedFor);

    expect(document.querySelector(".canvas-dock")).toHaveClass("overlay");
    expect(parts()).toEqual(["ghost dock-back", "canvas-writing", "dock-held"]);
    expect(screen.queryByRole("tablist")).toBeNull();
  });
});

describe("leaving a canvas being written from the dock", () => {
  it("is what the way back to the chat does first, and the dock keeps its canvas", async () => {
    const { onLeave, show } = await openChat("overlay");
    await openNote();
    show(askedFor);

    fireEvent.click(backToChat());
    await landed();

    expect(onLeave).toHaveBeenCalledTimes(1);
    expect(seen.dock?.view).toBe("canvas");
  });

  it("gives the way back to the chat its old work once nothing is being written", async () => {
    const { onLeave } = await openChat("overlay");
    await openNote();

    fireEvent.click(backToChat());
    await landed();

    expect(onLeave).not.toHaveBeenCalled();
    expect(seen.dock?.view).toBe("closed");
  });

  it("is what the Canvas button does first, opening nothing", async () => {
    const { onLeave, show } = await openChat("column", unasked);

    fireEvent.click(canvasButton());
    await landed();

    expect(onLeave).toHaveBeenCalledTimes(1);
    expect(seen.dock?.view).toBe("closed");

    show(null);
    fireEvent.click(canvasButton());
    await landed();

    expect(onLeave).toHaveBeenCalledTimes(1);
    expect(seen.dock?.view).toBe("list");
  });

  it("is what its own close button does", async () => {
    const { onLeave } = await openChat("column", unasked);

    fireEvent.click(closeButton());

    expect(onLeave).toHaveBeenCalledTimes(1);
  });
});

describe("the keyboard as a canvas being written comes up", () => {
  it("stays in the composer", async () => {
    const { show } = await openChat("column");
    composer().focus();

    show(unasked);

    expect(composer()).toHaveFocus();
  });

  it("stays nowhere when it was nowhere", async () => {
    const { show } = await openChat("column");

    show(unasked);

    expect(document.body).toHaveFocus();
  });

  it("goes to the frame's close button when the person asked to see it, and nowhere else in the dock", async () => {
    const { show } = await openChat("overlay");
    canvasButton().focus();

    show(askedFor);

    expect(closeButton()).toHaveFocus();
  });
});

describe("the keyboard as a canvas being written goes", () => {
  it("returns to the Canvas button from the frame when the dock is closed again", async () => {
    const { show } = await openChat("column", askedFor);
    expect(closeButton()).toHaveFocus();

    show(null);

    expect(canvasButton()).toHaveFocus();
  });

  it("stays in the composer", async () => {
    const { show } = await openChat("column", unasked);
    composer().focus();

    show(null);

    expect(composer()).toHaveFocus();
  });

  it("stays in the activity, which the closing dock would have taken it from", async () => {
    const { show } = await openChat("column", unasked);
    fireEvent.click(screen.getByRole("tab", { name: vi.canvas.tabs.activity }));
    const step = screen.getByRole("button", { name: ACTIVITY });
    step.focus();

    show(null);

    expect(step).toHaveFocus();
  });

  it("goes from the frame to the dock's first control when the canvas it wrote opens in its place", async () => {
    const { show } = await openChat("overlay", askedFor);
    expect(closeButton()).toHaveFocus();

    show(null, () => seen.dock?.open("a1", { quiet: true }));
    await landed();

    expect(seen.dock?.view).toBe("canvas");
    expect(backToChat()).toHaveFocus();
  });

  it("stays in the composer when the canvas it wrote opens in its place", async () => {
    const { show } = await openChat("overlay", unasked);
    composer().focus();

    show(null, () => seen.dock?.open("a1", { quiet: true }));
    await landed();

    expect(seen.dock?.view).toBe("canvas");
    expect(composer()).toHaveFocus();
  });

  it("goes from the frame to the first control of the dock it stood over", async () => {
    const { show } = await openChat("overlay");
    await openNote();
    show(askedFor);
    expect(closeButton()).toHaveFocus();

    show(null);

    expect(backToChat()).toHaveFocus();
  });

  it("stays in the composer when the dock it stood over shows again", async () => {
    const { show } = await openChat("overlay");
    await openNote();
    show(unasked);
    composer().focus();

    show(null);

    expect(composer()).toHaveFocus();
  });
});

/** The size observer jsdom lacks: it keeps the callback so a case can say the text grew. */
class FakeResizeObserver {
  static latest: FakeResizeObserver | null = null;
  constructor(readonly callback: () => void) {
    FakeResizeObserver.latest = this;
  }
  observe() {}
  disconnect() {}
}

describe("a second canvas being written in the dock", () => {
  function tall(body: HTMLElement, scrollHeight: number) {
    Object.defineProperty(body, "scrollHeight", { configurable: true, value: scrollHeight });
    Object.defineProperty(body, "clientHeight", { configurable: true, value: 300 });
  }
  const body = () => within(frame() as HTMLElement).getByText("Việc một").closest(".canvas-body") as HTMLElement;
  const grew = () => act(() => FakeResizeObserver.latest?.callback());

  it("follows its own last line, wherever the person had scrolled to in the first", async () => {
    FakeResizeObserver.latest = null;
    vitest.stubGlobal("ResizeObserver", FakeResizeObserver);
    const { show } = await openChat("column", unasked);
    const first = body();
    tall(first, 900);
    grew();
    first.scrollTop = 100;
    fireEvent.scroll(first);

    show({ item: item({ key: 8, title: "Danh sách" }), asked: null });
    tall(body(), 500);
    grew();

    expect(body().scrollTop).toBe(500);
  });
});
