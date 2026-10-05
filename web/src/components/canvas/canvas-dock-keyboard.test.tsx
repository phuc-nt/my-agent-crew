import { act, fireEvent, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { type CanvasDock, useCanvasDock } from "../../hooks/use-canvas-dock";
import { vi } from "../../i18n/vi";
import { landed, startServer, stopServer } from "../../test/canvas-hook";
import { editor, typeInto } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";
import { CanvasDockView } from "./canvas-dock";
import { CanvasButton } from "./canvas-dock-controls";

const ACTIVITY = "Các bước của lượt chạy";
const NOTE = "a1";
const PAGE = "a2";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
  backend.create({ title: "Một" });
  backend.canvas.add({ title: "Ghi chú", content: "Bước một", conversationIds: ["c1"] });
  backend.canvas.add({ title: "Trang", kind: "html", agent_id: "ming", content: "<input>", conversationIds: ["c1"] });
});

afterEach(stopServer);

/** The dock the chat last drew. */
const seen: { dock: CanvasDock | null } = { dock: null };

/** The dock as the chat lays it out on a wide screen: the Canvas button and a composer outside it,
 *  and inside it the conversation's activity, which has a control of its own. */
function Chat() {
  const dock = useCanvasDock("c1", true, true);
  seen.dock = dock;
  const trigger = useRef<HTMLButtonElement>(null);
  return (
    <>
      <CanvasButton dock={dock} ref={trigger} />
      <textarea aria-label="Soạn tin" />
      <CanvasDockView
        dock={dock}
        mode="column"
        activity={<button type="button">{ACTIVITY}</button>}
        connected
        agentName={(id) => id}
        trigger={trigger}
      />
    </>
  );
}

async function openChat() {
  render(<Chat />);
  await landed();
}

/** A canvas opens the way one opened by itself does: the keyboard is left where it was. */
async function shown(id: string) {
  act(() => seen.dock?.open(id, { quiet: true }));
  await landed();
}

const composer = () => screen.getByRole("textbox", { name: "Soạn tin" });
const typing = () => seen.dock?.typing();
const focus = (element: HTMLElement | null) => act(() => element?.focus());

describe("whether the person has the keyboard in the dock, which a canvas opening by itself would take from them", () => {
  it("is no while the keyboard is nowhere or in the composer, with a canvas open beside it", async () => {
    await openChat();
    await shown(NOTE);

    expect(document.body).toHaveFocus();
    expect(typing()).toBe(false);
    focus(composer());

    expect(composer()).toHaveFocus();
    expect(typing()).toBe(false);
  });

  it("is yes on a button of the open canvas, though its text does not have the keyboard", async () => {
    await openChat();
    await shown(NOTE);

    focus(screen.getByRole("button", { name: vi.canvas.view }));

    expect(document.activeElement).not.toBe(editor());
    expect(typing()).toBe(true);
  });

  it("is yes on a tab of the dock, which is no part of the canvas", async () => {
    await openChat();
    await shown(NOTE);

    focus(screen.getByRole("tab", { name: vi.canvas.tabs.activity }));

    expect(typing()).toBe(true);
  });

  it("is yes on a canvas in the dock's list, where no panel is open to say so", async () => {
    await openChat();
    fireEvent.click(screen.getByRole("button", { name: vi.canvas.buttonLabel(2) }));
    await landed();

    focus(screen.getByRole("button", { name: /^Trang/ }));

    expect(typing()).toBe(true);
  });

  it("is yes while the page of a canvas has the keyboard, which the app sees as its frame", async () => {
    await openChat();
    await shown(PAGE);
    const frame = document.querySelector("iframe");

    focus(frame);

    expect(frame).not.toBeNull();
    expect(document.activeElement).toBe(frame);
    expect(typing()).toBe(true);
  });

  it("is yes in the activity the dock shows while no canvas is open", async () => {
    await openChat();

    focus(screen.getByRole("button", { name: ACTIVITY }));

    expect(typing()).toBe(true);
  });

  it("is no again once the keyboard leaves the dock for the composer", async () => {
    await openChat();
    await shown(NOTE);
    focus(screen.getByRole("button", { name: vi.canvas.view }));
    expect(typing()).toBe(true);

    focus(composer());

    expect(typing()).toBe(false);
  });

  it("stays yes for words no version holds after the keyboard went back to the composer", async () => {
    await openChat();
    await shown(NOTE);
    typeInto("Bước một và hai");

    focus(composer());

    expect(typing()).toBe(true);
  });
});
