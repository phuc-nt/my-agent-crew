import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { ToolCall } from "./api/types";
import { vi } from "./i18n/vi";
import { RETRY_DELAYS_MS } from "./lib/canvas-types";
import { box, openChat, openNote, startApp, typeInCanvas } from "./test/canvas-app";
import { landed, sent, stopServer, wait } from "./test/canvas-hook";
import { editor } from "./test/canvas-panel";
import {
  answer,
  done,
  ended,
  frame,
  type HeldTurn,
  panel,
  piece,
  shownFrame,
  startTurn,
  started,
  stream,
  writingCards,
} from "./test/canvas-writing-turn";
import type { FakeBackend } from "./test/fake-backend";

/** Every canvas the dock was told to open, and how, oldest first. */
const opens = vitest.hoisted(() => [] as [string, { quiet?: boolean } | undefined][]);

// The app's own dock, with each opening counted.
vitest.mock("./hooks/use-canvas-dock", async (importOriginal) => {
  const real = await importOriginal<typeof import("./hooks/use-canvas-dock")>();
  const { useCallback } = await import("react");
  const useCanvasDock: typeof real.useCanvasDock = (...args) => {
    const dock = real.useCanvasDock(...args);
    const { open } = dock;
    const counted: typeof open = useCallback(
      (id, options) => {
        opens.push([id, options]);
        open(id, options);
      },
      [open],
    );
    return { ...dock, open: counted };
  };
  return { ...real, useCanvasDock };
});

const PLAN = "00ff00ff00ff";
const TITLE = "Kế hoạch tuần";
const text = vi.canvas.writing;

const WRITE = { title: TITLE, kind: "markdown", content: "Việc một\n\nViệc hai" };
const create: ToolCall = { id: "w1", name: "artifact_create", arguments: WRITE };
const TAGGED = `[artifact ${PLAN} v1]\nCanvas "${TITLE}" was created.`;

const HEAD = '{"title":"Kế hoạch tuần","kind":"markdown","content":"Việc';
const MORE = " một\\n\\nViệc";
const LAST = ' hai"}';
const THEIRS = "chữ đang gõ dở";

let backend: FakeBackend;

beforeEach(() => {
  opens.length = 0;
  backend = startApp();
});

afterEach(stopServer);

/** The times the dock was told to open the canvas the agent made. */
const opened = () => opens.filter(([id]) => id === PLAN);
const ONCE_QUIETLY = [[PLAN, { quiet: true }]];

const storedTitle = () => {
  const stored = panel();
  return stored && within(stored).queryByRole("heading", { level: 2, name: TITLE });
};
const showButton = () => within(writingCards()[0]).getByRole("button", { name: text.showLabel(TITLE) });
const closeButton = () => within(shownFrame()).getByRole("button", { name: text.close });
const backToChat = () => screen.getByRole("button", { name: vi.canvas.backToChat });
const overlay = () => screen.queryByRole("region", { name: vi.canvas.button });
const keyboardOn = (control: HTMLElement | null) => act(() => control?.focus());

/** The person presses the card's button with the keyboard on it, as a pointer or the Tab key does. */
async function ask() {
  keyboardOn(showButton());
  fireEvent.click(showButton());
  await landed();
}

/** The agent's canvas at its second piece on a screen `px` wide: up by itself where that is wide. */
async function written(px: number) {
  await openChat(px);
  const turn = await startTurn(backend);
  await stream(turn, piece(HEAD));
  await stream(turn, piece(MORE));
  return turn;
}

/** The server stores the canvas, and the call that made it ends. */
async function made(turn: HeldTurn) {
  backend.canvas.add({ id: PLAN, title: TITLE, agent_id: "master", content: WRITE.content, conversationIds: ["c1"] });
  await stream(turn, piece(LAST), answer([create]), started(create));
  await stream(turn, ended(create, TAGGED));
}

/** The turn says its last words and ends. */
async function over(turn: HeldTurn) {
  await stream(turn, answer([], "Đã viết kế hoạch."), done);
  await act(async () => turn.release());
  await landed();
}

/** "Ghi chú" open with words of the person's that the server will not take, and the agent's canvas shown at their request. */
async function watchingOverUnsavedWords(px: number) {
  await openChat(px);
  const turn = await startTurn(backend);
  await stream(turn, piece(HEAD));
  await openNote();
  keyboardOn(editor());
  typeInCanvas(THEIRS);
  backend.canvas.refuseNext("PUT", 500);
  // On a narrow screen the card is under the canvas covering the chat: a person gets here by
  // narrowing a wide window, and the test by pressing what they could not reach.
  await ask();
  await stream(turn, piece(MORE));
  expect(shownFrame()).toHaveTextContent("Việc một");
  expect(sent(backend, "PUT").map((request) => request.body)).toEqual([{ base_version: 1, content: THEIRS }]);
  expect(backend.canvas.content("a1")).toBe("");
  return turn;
}

describe("the canvas the agent made, taking the place of the one it was written in beside a wide chat", () => {
  it("is opened once, by what showed it being written and by nothing else in the turn", async () => {
    const turn = await written(1440);
    expect(frame()).not.toBeNull();

    await made(turn);

    expect(frame()).toBeNull();
    expect(storedTitle()).toBeInTheDocument();
    expect(opened()).toEqual(ONCE_QUIETLY);
    expect(box()).toHaveFocus();

    await over(turn);

    expect(opened()).toEqual(ONCE_QUIETLY);
    expect(storedTitle()).toBeInTheDocument();
  });

  it("is opened though the keyboard is on the close button of what the person asked to see, and takes the keyboard with it", async () => {
    await openChat(1440);
    const turn = await startTurn(backend);
    await stream(turn, piece(HEAD));
    await ask();
    expect(closeButton()).toHaveFocus();

    await made(turn);

    expect(frame()).toBeNull();
    expect(storedTitle()).toBeInTheDocument();
    expect(opened()).toEqual(ONCE_QUIETLY);
    expect(document.querySelector(".dock-canvas")).toContainElement(document.activeElement as HTMLElement);
  });

  it("is opened though the keyboard has gone to a tab of the column since it came up", async () => {
    const turn = await written(1440);
    const tab = screen.getByRole("tab", { name: vi.canvas.tabs.activity });
    keyboardOn(tab);

    await made(turn);

    expect(frame()).toBeNull();
    expect(storedTitle()).toBeInTheDocument();
    expect(opened()).toEqual(ONCE_QUIETLY);
    expect(tab).toHaveFocus();
  });

  it("is opened by nothing over words of theirs no version holds, nor later in the turn once those are saved", async () => {
    const turn = await watchingOverUnsavedWords(1440);

    await made(turn);

    expect(frame()).toBeNull();
    expect(opened()).toEqual([]);
    expect(storedTitle()).toBeNull();
    expect(editor()).toHaveValue(THEIRS);

    // The save is tried again and taken, and the keyboard goes back to the chat box: nothing
    // looks at that call again.
    wait(RETRY_DELAYS_MS[0]);
    await landed();
    expect(backend.canvas.content("a1")).toBe(THEIRS);
    keyboardOn(box());

    await over(turn);

    expect(opened()).toEqual([]);
    expect(storedTitle()).toBeNull();
    expect(editor()).toHaveValue(THEIRS);
  });
});

describe("the canvas the agent made, taking the place of the one it was written in over a narrow chat", () => {
  it("is opened once over the chat when the person was watching, and the keyboard goes to the way back", async () => {
    const turn = await written(1000);
    await ask();
    expect(closeButton()).toHaveFocus();

    await made(turn);

    expect(frame()).toBeNull();
    expect(overlay()).toContainElement(screen.getByRole("heading", { level: 2, name: TITLE }));
    expect(opened()).toEqual(ONCE_QUIETLY);
    expect(backToChat()).toHaveFocus();

    await over(turn);

    expect(opened()).toEqual(ONCE_QUIETLY);
  });

  it("is opened by nothing when the person only had its card", async () => {
    const turn = await written(1000);

    await made(turn);
    await over(turn);

    expect(opened()).toEqual([]);
    expect(overlay()).toBeNull();
  });

  it("is opened by nothing over words of theirs no version holds, and their canvas covers the chat as before", async () => {
    const turn = await watchingOverUnsavedWords(1000);

    await made(turn);

    expect(frame()).toBeNull();
    expect(opened()).toEqual([]);
    expect(overlay()).toContainElement(editor());
    expect(editor()).toHaveValue(THEIRS);

    await over(turn);

    expect(opened()).toEqual([]);
    expect(editor()).toHaveValue(THEIRS);
  });
});
