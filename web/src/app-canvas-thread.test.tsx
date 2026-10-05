import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { AgentEvent } from "./api/types";
import { vi } from "./i18n/vi";
import { bodies, box, focusWrites, layout, openChat, openNote, say, startApp } from "./test/canvas-app";
import { landed, stopServer } from "./test/canvas-hook";
import { editor } from "./test/canvas-panel";
import { type FakeBackend, storedMessage } from "./test/fake-backend";

const PLAN = "00ff00ff00ff";
const TITLE = "Kế hoạch tuần";
const WRITE = { title: TITLE, content: "Việc một\n\nViệc hai" };
const TAGGED = `[artifact ${PLAN} v1]\nCanvas "${TITLE}" was created.`;

let backend: FakeBackend;

beforeEach(() => {
  backend = startApp();
});

afterEach(stopServer);

/** The canvas an agent made, shared with the first conversation. */
const plan = () =>
  backend.canvas.add({ id: PLAN, title: TITLE, agent_id: "master", content: WRITE.content, conversationIds: ["c1"] });

/** A turn in which the agent makes the canvas and says so, as the server streams it. */
const createTurn = (): AgentEvent[] => [
  {
    type: "assistant_message",
    message_id: "a1",
    content: "",
    tool_calls: [{ id: "w1", name: "artifact_create", arguments: WRITE }],
    provider: null,
    model: null,
    cost_usd: null,
  },
  { type: "tool_call", tool_call_id: "w1", name: "artifact_create", arguments: WRITE },
  { type: "tool_result", tool_call_id: "w1", name: "artifact_create", ok: true, output: TAGGED },
  {
    type: "assistant_message",
    message_id: "a2",
    content: "Đã viết kế hoạch.",
    tool_calls: [],
    provider: null,
    model: null,
    cost_usd: null,
  },
  { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
];

/** The first conversation already holds the turn above, saved in an earlier visit. */
function saveEarlierTurn() {
  const call = { id: "old1", name: "artifact_create", arguments: WRITE };
  backend.conversations
    .get("c1")
    ?.messages.push(
      storedMessage("user", "viết kế hoạch tuần"),
      storedMessage("assistant", "", { tool_calls: [call] }),
      storedMessage("tool", TAGGED, { tool_call_id: "old1", name: "artifact_create" }),
      storedMessage("assistant", "Đã viết kế hoạch."),
    );
}

const panelTitle = (name = TITLE) => screen.queryByRole("heading", { level: 2, name });
const main = () => document.querySelector("main") as HTMLElement;
const card = () => screen.getByTestId("canvas-card");
const openButton = () => within(card()).getByRole("button", { name: vi.canvas.card.openLabel(TITLE) });

describe("a canvas the agent makes in a turn this tab is showing", () => {
  it("opens beside the thread at once, leaves the keyboard in the box and writes nothing", async () => {
    plan();
    await openChat(1440);
    act(() => box().focus());
    backend.nextTurn = createTurn();

    await say("viết kế hoạch tuần");

    expect(layout()).toHaveClass("with-canvas");
    expect(panelTitle()).toBeInTheDocument();
    expect(box()).toHaveFocus();
    expect(within(card()).getByText(TITLE)).toBeInTheDocument();
    expect(focusWrites(backend)).toEqual([]);
  });

  it("goes with the next message the person sends as the canvas they have open", async () => {
    plan();
    await openChat(1440);
    backend.nextTurn = createTurn();
    await say("viết kế hoạch tuần");

    await say("thêm một việc");

    expect(bodies(backend)).toEqual([
      { text: "viết kế hoạch tuần" },
      { text: "thêm một việc", canvas: { artifact_id: PLAN, selection: null } },
    ]);
  });

  it("does not take the panel from a canvas the person has the keyboard in", async () => {
    await openChat(1440);
    await openNote();
    plan();
    act(() => editor()?.focus());
    backend.nextTurn = createTurn();

    await say("viết kế hoạch tuần");

    expect(panelTitle()).toBeNull();
    expect(panelTitle("Ghi chú")).toBeInTheDocument();
    expect(editor()).toHaveFocus();
    expect(card()).toBeInTheDocument();
  });

  it("does not take the panel from a canvas the person has the keyboard on a button of, and still opens from its card", async () => {
    await openChat(1440);
    await openNote();
    plan();
    const view = screen.getByRole("button", { name: vi.canvas.view });
    act(() => view.focus());
    backend.nextTurn = createTurn();

    await say("viết kế hoạch tuần");

    expect(panelTitle()).toBeNull();
    expect(panelTitle("Ghi chú")).toBeInTheDocument();
    expect(view).toHaveFocus();

    fireEvent.click(openButton());
    await landed();

    expect(panelTitle()).toBeInTheDocument();
    expect(panelTitle("Ghi chú")).toBeNull();
  });

  it("opens only the once, however the person goes from the chat to the crew and back", async () => {
    plan();
    await openChat(1440);
    backend.nextTurn = createTurn();
    await say("viết kế hoạch tuần");
    fireEvent.click(screen.getByRole("button", { name: vi.canvas.close }));
    await landed();
    await landed();
    expect(layout()).not.toHaveClass("with-canvas");

    fireEvent.click(screen.getByRole("button", { name: /Quản lý/ }));
    await landed();
    fireEvent.click(screen.getByRole("button", { name: vi.manage.backToChat }));
    await landed();
    await landed();

    expect(card()).toBeInTheDocument();
    expect(layout()).not.toHaveClass("with-canvas");
    expect(panelTitle()).toBeNull();
  });

  it("opens when its call ends after the person left the chat mid-turn and came back", async () => {
    plan();
    await openChat(1440);
    const [asks, , ...rest] = createTurn();
    const waits = { approval_id: "ap1", tool_call_id: "w1", name: "artifact_create", arguments: WRITE, reason: "", expires_at: "2099-01-01T00:00:00Z" };
    backend.nextTurn = [asks, { type: "approval_required", ...waits }];
    await say("viết kế hoạch tuần");
    fireEvent.click(screen.getByRole("button", { name: /Quản lý/ }));
    await landed();
    fireEvent.click(screen.getByRole("button", { name: vi.manage.backToChat }));
    await landed();
    await landed();
    expect(panelTitle()).toBeNull();
    backend.nextTurn = rest;

    fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: vi.approve }));
    await landed();
    await landed();
    await landed();

    expect(layout()).toHaveClass("with-canvas");
    expect(panelTitle()).toBeInTheDocument();
    expect(card()).toBeInTheDocument();
    expect(focusWrites(backend)).toEqual([]);
  });
});

describe("a canvas the agent makes on a screen too narrow to hold it beside the thread", () => {
  it("shows its card with a way to open it, and opens nothing by itself", async () => {
    plan();
    await openChat(1000);
    backend.nextTurn = createTurn();

    await say("viết kế hoạch tuần");

    expect(main()).not.toHaveAttribute("inert");
    expect(screen.queryByRole("region", { name: vi.canvas.button })).toBeNull();
    expect(openButton()).toBeInTheDocument();

    fireEvent.click(openButton());
    await landed();

    expect(screen.getByRole("region", { name: vi.canvas.button })).toBeInTheDocument();
    expect(panelTitle()).toBeInTheDocument();
    expect(main()).toHaveAttribute("inert");
  });
});

describe("a canvas an earlier turn made", () => {
  it("is a card in the saved thread, and opens only when asked, taking the keyboard into the dock", async () => {
    plan();
    saveEarlierTurn();
    await openChat(1440);

    expect(layout()).not.toHaveClass("with-canvas");
    expect(panelTitle()).toBeNull();
    expect(within(card()).getByText(TITLE)).toBeInTheDocument();

    act(() => openButton().focus());
    fireEvent.click(openButton());
    await landed();

    expect(layout()).toHaveClass("with-canvas");
    expect(panelTitle()).toBeInTheDocument();
    expect(document.querySelector(".dock-canvas")).toContainElement(document.activeElement as HTMLElement);
  });

  it("says so, with nothing to open, when the server no longer has the canvas", async () => {
    saveEarlierTurn();
    await openChat(1440);
    await landed();

    expect(within(card()).getByText(vi.canvas.gone)).toBeInTheDocument();
    expect(within(card()).queryByRole("button")).toBeNull();
    expect(layout()).not.toHaveClass("with-canvas");
  });
});
