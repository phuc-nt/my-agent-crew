import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { type CanvasDock, useCanvasDock } from "../../hooks/use-canvas-dock";
import { vi } from "../../i18n/vi";
import { saveInBackground } from "../../lib/canvas-handoff";
import { canvasTemplate } from "../../lib/canvas-templates";
import { landed, startServer, stopServer } from "../../test/canvas-hook";
import { leftCanvas } from "../../test/canvas-left";
import { editor, mode } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";
import { CanvasDockView } from "./canvas-dock";
import { CanvasButton, CanvasChatNotices } from "./canvas-dock-controls";

const ACTIVITY = "Các bước của lượt chạy";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
  backend.create({ title: "Một" });
  backend.canvas.add({ title: "Ghi chú", conversationIds: ["c1"] });
});

afterEach(stopServer);

/** The dock the chat last drew, for the tests that open a canvas without a click. */
const seen: { dock: CanvasDock | null } = { dock: null };

/** The dock as the chat lays it out: the Canvas button, a composer outside the dock, what the
 *  canvases have to say in the chat, and the dock itself, whose activity can hold the keyboard. */
function Chat({ mode }: { mode: "column" | "overlay" }) {
  const dock = useCanvasDock("c1", true, true);
  seen.dock = dock;
  const trigger = useRef<HTMLButtonElement>(null);
  return (
    <>
      <CanvasButton dock={dock} ref={trigger} />
      <textarea aria-label="Soạn tin" />
      <CanvasChatNotices dock={dock} />
      <CanvasDockView dock={dock} mode={mode} activity={<p tabIndex={-1}>{ACTIVITY}</p>} connected agentName={(id) => id} trigger={trigger} />
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

describe("making a canvas of a kind from the list", () => {
  it("asks for the kind chosen with what it starts from, and opens it to edit as text", async () => {
    await openChat("column");
    await openList();

    fireEvent.change(screen.getByRole("combobox", { name: vi.canvas.kindLabel }), { target: { value: "html" } });
    fireEvent.click(screen.getByRole("button", { name: vi.canvas.newCanvas }));
    await landed();

    const body = { title: vi.canvas.untitled, kind: "html", content: canvasTemplate("html"), conversation_id: "c1" };
    expect(backend.requests.filter((request) => request.method === "POST")).toEqual([{ method: "POST", path: "/artifacts", body }]);
    expect(mode()).toBe(vi.canvas.edit);
    expect(editor()?.value).toBe(canvasTemplate("html"));
    expect(editor()).toHaveClass("code");
    expect(document.querySelector("iframe")).toBeNull();
  });
});

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

  // The activity is part of the dock's element whether the dock is open or not, so a keyboard
  // there is in the dock already when it opens and still in it when it closes.
  it("is left in the activity when the column opens from a press that did not take it, the activity going behind its tab", async () => {
    await openChat("column");
    const activity = screen.getByText(ACTIVITY);
    activity.focus();

    await openList();

    expect(screen.getByRole("tab", { name: vi.canvas.tabs.canvas })).toHaveAttribute("aria-selected", "true");
    expect(activity).toHaveFocus();
  });

  it("goes back to the Canvas button from the activity when the dock closes", async () => {
    await openChat("column");
    await openList();
    fireEvent.click(screen.getByRole("tab", { name: vi.canvas.tabs.activity }));
    const activity = screen.getByText(ACTIVITY);
    activity.focus();

    await act(async () => seen.dock?.close());
    await landed();

    expect(screen.queryByRole("tab")).toBeNull();
    expect(screen.getByText(ACTIVITY)).toBe(activity);
    expect(canvasButton()).toHaveFocus();
  });
});

describe("focus when a canvas opens without being asked for", () => {
  const dockOpen = () => document.querySelector(".dock-canvas");
  const inDock = () => dockOpen()?.contains(document.activeElement) ?? false;

  it("goes into the dock from nowhere, as any opening does", async () => {
    await openChat("column");

    act(() => seen.dock?.open("a1"));
    await landed();

    expect(inDock()).toBe(true);
  });

  it("goes into the dock from the composer, as any opening does", async () => {
    await openChat("column");
    composer().focus();

    act(() => seen.dock?.open("a1"));
    await landed();

    expect(inDock()).toBe(true);
  });

  it("stays nowhere when it was nowhere", async () => {
    await openChat("column");

    act(() => seen.dock?.open("a1", { quiet: true }));
    await landed();

    expect(dockOpen()).not.toBeNull();
    expect(document.body).toHaveFocus();
  });

  it("stays in the composer when it was there", async () => {
    await openChat("column");
    composer().focus();

    act(() => seen.dock?.open("a1", { quiet: true }));
    await landed();

    expect(dockOpen()).not.toBeNull();
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

  it("shows no count until it knows of a canvas", async () => {
    render(<Chat mode="column" />);
    const before = screen.getByRole("button", { name: vi.canvas.buttonLabel(0) });
    expect(before.querySelector(".badge")).toBeNull();

    await landed();

    expect(canvasButton()).toBe(before);
    expect(before.querySelector(".badge")).toHaveTextContent("1");
  });
});

describe("a save handed off that did not land", () => {
  it("names a canvas without a title as untitled", async () => {
    await openChat("column");

    await act(() => saveInBackground(leftCanvas("a9", async () => null)));

    expect(screen.getByRole("alert")).toHaveTextContent(vi.canvas.handoffFailed(vi.canvas.untitled, true));
    // The words themselves, since the line above would follow a swap inside the function.
    expect(screen.getByRole("alert")).toHaveTextContent("bản nháp vẫn trên máy này");
  });

  it("says the draft is in this tab alone when this device could not keep one, and how to save it", async () => {
    await openChat("column");

    await act(() => saveInBackground(leftCanvas("a9", async () => null, { draftFailed: true })));

    const notice = screen.getByRole("alert");
    expect(notice).toHaveTextContent(vi.canvas.handoffFailed(vi.canvas.untitled, false));
    expect(notice).not.toHaveTextContent(vi.canvas.handoffFailed(vi.canvas.untitled, true));
    expect(notice).toHaveTextContent("bản nháp chỉ còn trong tab này, mở lại canvas để lưu");
    expect(notice).not.toHaveTextContent("vẫn trên máy này");
  });
});

describe("the line saying a message went before its canvas was saved", () => {
  it("is not there until the dock says so, and is a status, not an alarm", async () => {
    await openChat("column");
    expect(screen.queryByRole("status")).toBeNull();

    act(() => seen.dock?.noteSentUnsaved(true));

    expect(screen.getByRole("status")).toHaveTextContent(vi.canvas.sentUnsaved);
    expect(screen.getByRole("status")).toHaveClass("notice", "warn", "canvas-notice");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("stands beside a save that did not land, and each is put away by its own button", async () => {
    await openChat("column");
    await act(() => saveInBackground(leftCanvas("a9", async () => null)));
    act(() => seen.dock?.noteSentUnsaved(true));

    fireEvent.click(within(screen.getByRole("status")).getByRole("button", { name: vi.canvas.dismiss }));
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByRole("alert")).toBeInTheDocument();

    act(() => seen.dock?.noteSentUnsaved(true));
    fireEvent.click(within(screen.getByRole("alert")).getByRole("button", { name: vi.canvas.dismiss }));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});

describe("the open canvas's own page", () => {
  it.each(["column", "overlay"] as const)("is one click from its panel in the %s, at the canvas's address on the manage screen", async (mode) => {
    await openChat(mode);
    const open = vitest.spyOn(window, "open").mockReturnValue(null);
    act(() => seen.dock?.open("a1"));
    await landed();

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.openStandalone }));

    expect(open.mock.calls).toEqual([["#/manage/canvas/a1", "_blank", "noopener,noreferrer"]]);
  });
});
