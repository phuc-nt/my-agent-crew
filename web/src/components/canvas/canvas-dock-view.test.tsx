import { act, fireEvent, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useCanvasDock } from "../../hooks/use-canvas-dock";
import { vi } from "../../i18n/vi";
import { saveInBackground } from "../../lib/canvas-handoff";
import { openState } from "../../lib/canvas-machine";
import { landed, startServer, stopServer } from "../../test/canvas-hook";
import { CanvasButton, CanvasDockView, CanvasHandoffNotices } from "./canvas-dock";

const ACTIVITY = "Các bước của lượt chạy";

beforeEach(() => {
  const backend = startServer();
  backend.create({ title: "Một" });
  backend.canvas.add({ title: "Ghi chú", conversationIds: ["c1"] });
});

afterEach(stopServer);

/** The dock as the chat lays it out: the Canvas button, a composer outside the dock, the notices
 *  of saves handed off, and the dock itself. */
function Chat({ mode }: { mode: "column" | "overlay" }) {
  const dock = useCanvasDock("c1", true);
  const trigger = useRef<HTMLButtonElement>(null);
  return (
    <>
      <CanvasButton dock={dock} ref={trigger} />
      <textarea aria-label="Soạn tin" />
      <CanvasHandoffNotices dock={dock} />
      <CanvasDockView dock={dock} mode={mode} activity={<p>{ACTIVITY}</p>} connected agentName={(id) => id} trigger={trigger} />
    </>
  );
}

async function openChat(mode: "column" | "overlay") {
  const view = render(<Chat mode={mode} />);
  await landed();
  return view;
}

const canvasButton = () => screen.getByRole("button", { name: vi.canvas.buttonLabel(1) });
const composer = () => screen.getByRole("textbox", { name: "Soạn tin" });

async function openList() {
  fireEvent.click(canvasButton());
  await landed();
}

describe("focus in the canvas dock", () => {
  it("moves from the Canvas button into the column it opens", async () => {
    await openChat("column");
    canvasButton().focus();

    await openList();

    expect(screen.getByRole("button", { name: vi.canvas.newCanvas })).toHaveFocus();
  });

  it("moves onto the way back to the chat when the dock covers it", async () => {
    await openChat("overlay");
    canvasButton().focus();

    await openList();

    expect(screen.getByRole("button", { name: vi.canvas.backToChat })).toHaveFocus();
  });

  it("stays where the person put it as the dock moves from the list to a canvas", async () => {
    await openChat("column");
    await openList();
    composer().focus();

    fireEvent.click(screen.getByRole("button", { name: /^Ghi chú/ }));
    await landed();

    expect(composer()).toHaveFocus();
  });
});

describe("the dock beside a wide conversation", () => {
  it("shows the activity while nothing is open", async () => {
    await openChat("column");

    expect(screen.getByText(ACTIVITY)).toBeVisible();
  });

  it("puts the activity behind a tab, and shows the dock whole once it covers the chat", async () => {
    const { rerender } = await openChat("column");
    await openList();
    const activityTab = screen.getByRole("tab", { name: vi.canvas.tabs.activity });

    fireEvent.click(activityTab);

    expect(activityTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: vi.canvas.tabs.canvas })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByText(ACTIVITY)).toBeVisible();
    rerender(<Chat mode="overlay" />);
    expect(screen.getByRole("button", { name: vi.canvas.backToChat })).toBeVisible();
  });

  it("is as wide as its edge says", async () => {
    const { container } = await openChat("column");
    await openList();

    const edge = screen.getByRole("separator", { name: vi.canvas.resize });
    const column = container.querySelector<HTMLElement>(".canvas-dock");
    expect(column?.style.getPropertyValue("--canvas-width")).toBe(`${edge.getAttribute("aria-valuenow")}px`);
  });
});

describe("the Canvas button", () => {
  it("counts the conversation's canvases and says whether the dock is open", async () => {
    await openChat("column");
    expect(canvasButton().querySelector(".badge")).toHaveTextContent("1");
    expect(canvasButton()).toHaveAttribute("aria-expanded", "false");

    await openList();

    expect(canvasButton()).toHaveAttribute("aria-expanded", "true");
  });
});

describe("a save handed off that did not land", () => {
  it("names a canvas without a title as untitled", async () => {
    await openChat("column");

    await act(() => saveInBackground({ id: "a9", state: openState("a9", null), flush: async () => null }));

    expect(screen.getByRole("alert")).toHaveTextContent(vi.canvas.handoffFailed(vi.canvas.untitled));
  });
});
