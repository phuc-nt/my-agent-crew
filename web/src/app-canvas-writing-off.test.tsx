import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ToolCall } from "./api/types";
import { vi } from "./i18n/vi";
import { box, focusWrites, layout, openChat, startApp } from "./test/canvas-app";
import { landed, sent, stopServer } from "./test/canvas-hook";
import {
  answer,
  canvasToggle,
  done,
  ended,
  frame,
  panel,
  piece,
  shownFrame,
  startTurn,
  started,
  stream,
  writingCards,
} from "./test/canvas-writing-turn";
import type { FakeBackend } from "./test/fake-backend";
import { LIVE_PREVIEW_KEY as KEY } from "./test/live-preview";

const PLAN = "00ff00ff00ff";
const TITLE = "Kế hoạch tuần";
const WRITE = { title: TITLE, kind: "markdown", content: "Việc một\n\nViệc hai" };
const create: ToolCall = { id: "w1", name: "artifact_create", arguments: WRITE };
const TAGGED = `[artifact ${PLAN} v1]\nCanvas "${TITLE}" was created.`;

/** The call's arguments as the model writes them, in three pieces. */
const PIECES = ['{"title":"Kế hoạch tuần","kind":"markdown","content":"Việc', " một\\n\\nViệc", ' hai"}'];

let backend: FakeBackend;

beforeEach(() => {
  backend = startApp();
});

afterEach(stopServer);

const status = () => screen.getByTestId("status-line").firstElementChild;
const preview = () => screen.getByRole("checkbox", { name: vi.canvas.writing.preview });

/** The agent writes the whole canvas, a piece at a time, in a turn that stays open. */
async function written() {
  const turn = await startTurn(backend);
  for (const chunk of PIECES) await stream(turn, piece(chunk));
  return turn;
}

/** The person goes to Settings, flips the switch there, and comes back to the chat. */
async function flipInSettings() {
  fireEvent.click(screen.getByRole("button", { name: new RegExp(vi.manage.open) }));
  await landed();
  const nav = within(screen.getByRole("navigation", { name: vi.manage.nav }));
  fireEvent.click(nav.getByRole("button", { name: new RegExp(`^${vi.settings}`) }));
  await landed();
  fireEvent.click(preview());
  fireEvent.click(screen.getByRole("button", { name: vi.manage.backToChat }));
  await landed();
  await landed();
}

describe("a canvas the agent writes on a device that turned the preview off", () => {
  beforeEach(() => localStorage.setItem(KEY, "off"));

  it("has no card and nothing beside the thread, and the wait reads as it did before the first piece", async () => {
    await openChat(1440);
    act(() => box().focus());
    const turn = await startTurn(backend);
    expect(screen.getByTestId("thinking")).toBeInTheDocument();
    expect(status()).toHaveTextContent(vi.statusStreaming);

    for (const chunk of PIECES) await stream(turn, piece(chunk));

    expect(writingCards()).toEqual([]);
    expect(frame()).toBeNull();
    expect(screen.getByTestId("thinking")).toBeInTheDocument();
    expect(status()).toHaveTextContent(vi.statusStreaming);
    expect(layout()).toHaveClass("with-activity");
    expect(canvasToggle()).toHaveAttribute("aria-expanded", "false");
    expect(box()).toHaveFocus();
  });

  it("still gets the canvas the agent made opened beside the chat, as a wide screen always did", async () => {
    await openChat(1440);
    act(() => box().focus());
    const turn = await written();

    backend.canvas.add({ id: PLAN, title: TITLE, agent_id: "master", content: WRITE.content, conversationIds: ["c1"] });
    await stream(turn, answer([create]), started(create));
    expect(frame()).toBeNull();
    expect(panel()).toBeNull();

    await stream(turn, ended(create, TAGGED));

    expect(frame()).toBeNull();
    expect(within(panel() as HTMLElement).getByRole("heading", { level: 2, name: TITLE })).toBeInTheDocument();
    expect(layout()).toHaveClass("with-canvas");
    expect(box()).toHaveFocus();

    await stream(turn, answer([], "Đã viết kế hoạch."), done);
    await act(async () => turn.release());
    await landed();

    expect(focusWrites(backend)).toEqual([]);
    expect(sent(backend, "PUT")).toEqual([]);
  });

  it("has no card on a narrow screen either", async () => {
    await openChat(390);

    await written();

    expect(writingCards()).toEqual([]);
    expect(frame()).toBeNull();
    expect(screen.getByTestId("thinking")).toBeInTheDocument();
  });
});

describe("the switch in Settings for watching a canvas be written", () => {
  it("turns it off for the canvases written from then on, and leaves no more than a word behind", async () => {
    await openChat(1440);

    await flipInSettings();

    expect(localStorage.getItem(KEY)).toBe("off");
    await written();
    expect(writingCards()).toEqual([]);
    expect(frame()).toBeNull();
  });

  it("turns it back on, and the next canvas fills in beside the thread", async () => {
    localStorage.setItem(KEY, "off");
    await openChat(1440);

    await flipInSettings();

    expect(localStorage.getItem(KEY)).toBeNull();
    await written();
    expect(writingCards()).toHaveLength(1);
    expect(shownFrame()).toHaveTextContent("Việc hai");
  });
});
