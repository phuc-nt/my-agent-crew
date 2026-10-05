import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ToolCall } from "./api/types";
import { vi } from "./i18n/vi";
import { bodies, box, focusWrites, layout, openChat, openNote, say, startApp, typeInCanvas } from "./test/canvas-app";
import { landed, sent, stopServer } from "./test/canvas-hook";
import { editor } from "./test/canvas-panel";
import {
  answer,
  canvasToggle,
  done,
  ended,
  frame,
  panel,
  piece,
  shownFrame,
  startOver,
  startTurn,
  started,
  stream,
  writingCards,
} from "./test/canvas-writing-turn";
import type { FakeBackend } from "./test/fake-backend";

const PLAN = "00ff00ff00ff";
const TITLE = "Kế hoạch tuần";
const text = vi.canvas.writing;

const WRITE = { title: TITLE, kind: "markdown", content: "Việc một\n\nViệc hai" };
const create: ToolCall = { id: "w1", name: "artifact_create", arguments: WRITE };
const TAGGED = `[artifact ${PLAN} v1]\nCanvas "${TITLE}" was created.`;

/** The call's arguments as the model writes them, in three pieces. */
const HEAD = '{"title":"Kế hoạch tuần","kind":"markdown","content":"Việc';
const MORE = " một\\n\\nViệc";
const LAST = ' hai"}';

let backend: FakeBackend;

beforeEach(() => {
  backend = startApp();
});

afterEach(stopServer);

/** The server stores the canvas the call made, as it does before the call's result goes out. */
const store = () =>
  backend.canvas.add({ id: PLAN, title: TITLE, agent_id: "master", content: WRITE.content, conversationIds: ["c1"] });

/** The agent's canvas as a stored one names itself in its panel, which the frame's own heading is not. */
const storedTitle = () => {
  const stored = panel();
  return stored && within(stored).queryByRole("heading", { level: 2, name: TITLE });
};
const showButton = (title = TITLE) => within(writingCards()[0]).getByRole("button", { name: text.showLabel(title) });
const changes = () => backend.requests.filter((r) => r.method !== "GET" && r.path.startsWith("/artifacts"));
/** What the saves of "Ghi chú" carried, oldest first. */
const saved = () => sent(backend, "PUT").map((r) => r.body);
const THEIRS = "chữ đang gõ dở";

/** The person leaves the editor for the card's button and presses it, as a pointer or the Tab key does. */
async function pressShow() {
  act(() => showButton().focus());
  fireEvent.click(showButton());
  await landed();
}

/** A wide screen on which the agent has written enough of the canvas for it to come up. */
async function watching() {
  await openChat(1440);
  act(() => box().focus());
  const turn = await startTurn(backend);
  await stream(turn, piece(HEAD));
  await stream(turn, piece(MORE));
  return turn;
}

describe("a canvas the agent is writing, beside a wide conversation", () => {
  it("is a card at the first piece, with nothing beside the thread yet", async () => {
    await openChat(1440);
    const turn = await startTurn(backend);

    await stream(turn, piece(HEAD));

    expect(writingCards()).toHaveLength(1);
    expect(within(writingCards()[0]).getByText(TITLE)).toBeInTheDocument();
    expect(within(writingCards()[0]).getByText(text.creating)).toBeInTheDocument();
    expect(screen.queryByTestId("thinking")).toBeNull();
    expect(frame()).toBeNull();
    expect(layout()).toHaveClass("with-activity");
    expect(canvasToggle()).toHaveAttribute("aria-expanded", "false");
  });

  it("fills in beside the thread from the second piece, and leaves the keyboard in the box", async () => {
    const turn = await watching();

    expect(shownFrame()).toHaveTextContent("Việc một");
    expect(shownFrame()).not.toHaveTextContent("hai");
    expect(within(shownFrame()).getByText(text.unsaved)).toBeInTheDocument();
    expect(layout()).toHaveClass("with-canvas");
    expect(canvasToggle()).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("tab", { name: vi.canvas.tabs.canvas })).toHaveAttribute("aria-selected", "true");
    expect(panel()).toBeNull();
    expect(box()).toHaveFocus();

    await stream(turn, piece(LAST));

    expect(shownFrame()).toHaveTextContent("Việc hai");
    expect(writingCards()).toHaveLength(1);
    expect(box()).toHaveFocus();
  });

  it("gives way to the canvas the agent made, in the same column, having written nothing to the server", async () => {
    const turn = await watching();
    const column = document.querySelector(".canvas-dock");
    await stream(turn, piece(LAST));

    store();
    await stream(turn, answer([create]), started(create));

    expect(writingCards()).toEqual([]);
    expect(within(shownFrame()).getByText(text.saving)).toBeInTheDocument();
    expect(storedTitle()).toBeNull();

    await stream(turn, ended(create, TAGGED));

    expect(frame()).toBeNull();
    expect(storedTitle()).toBeInTheDocument();
    expect(layout()).toHaveClass("with-canvas");
    expect(document.querySelector(".canvas-dock")).toBe(column);
    expect(box()).toHaveFocus();

    await stream(turn, answer([], "Đã viết kế hoạch."), done);
    await act(async () => turn.release());
    await landed();

    expect(storedTitle()).toBeInTheDocument();
    expect(focusWrites(backend)).toEqual([]);
    expect(changes()).toEqual([]);
    expect(bodies(backend)).toEqual([{ text: "viết kế hoạch tuần" }]);
  });

  it("goes with no message the person sends while it shows", async () => {
    await watching();

    await say("thêm một việc nữa");

    expect(bodies(backend)).toEqual([{ text: "viết kế hoạch tuần" }, { text: "thêm một việc nữa" }]);
    expect(focusWrites(backend)).toEqual([]);
    expect(frame()).not.toBeNull();
  });

  it("goes at once when the model starts its answer over, and the next is built from nothing", async () => {
    const turn = await watching();

    await stream(turn, ...startOver(1));

    expect(frame()).toBeNull();
    expect(writingCards()).toEqual([]);
    expect(layout()).toHaveClass("with-activity");

    await stream(turn, piece('{"title":"Bản mới","content":"A', { attempt: 1 }));

    expect(within(writingCards()[0]).getByText("Bản mới")).toBeInTheDocument();
    expect(frame()).toBeNull();

    await stream(turn, piece("B", { attempt: 1 }));

    expect(within(shownFrame()).getByRole("heading", { level: 2, name: "Bản mới" })).toBeInTheDocument();
    expect(shownFrame().querySelector("pre.canvas-code")?.textContent).toBe("AB");
    expect(shownFrame()).not.toHaveTextContent("Việc");
  });

  it("leaves nothing on the screen when the person stops the turn", async () => {
    await watching();

    fireEvent.click(screen.getByRole("button", { name: vi.stop }));
    await landed();
    await landed();

    expect(frame()).toBeNull();
    expect(writingCards()).toEqual([]);
    expect(layout()).toHaveClass("with-activity");
    expect(canvasToggle()).toHaveAttribute("aria-expanded", "false");
  });
});

describe("putting away a canvas the agent is writing", () => {
  it("is what the Canvas button does first, and it stays away for the rest of the turn", async () => {
    const turn = await watching();

    fireEvent.click(canvasToggle());
    await landed();

    expect(frame()).toBeNull();
    expect(layout()).toHaveClass("with-activity");
    expect(screen.queryByRole("button", { name: vi.canvas.newCanvas })).toBeNull();
    expect(writingCards()).toHaveLength(1);

    await stream(turn, piece(LAST));
    expect(frame()).toBeNull();

    await stream(turn, ...startOver(1));
    await stream(turn, piece('{"content":"A', { attempt: 1 }));
    await stream(turn, piece("B", { attempt: 1 }));

    expect(frame()).toBeNull();
    expect(writingCards()).toHaveLength(1);
  });

  it("leaves its card to bring it back, and the Canvas button to open the list afterwards", async () => {
    await watching();
    fireEvent.click(within(shownFrame()).getByRole("button", { name: text.close }));
    expect(frame()).toBeNull();

    fireEvent.click(showButton());
    expect(shownFrame()).toHaveTextContent("Việc một");
    expect(within(shownFrame()).getByRole("button", { name: text.close })).toHaveFocus();

    fireEvent.click(canvasToggle());
    await landed();
    expect(frame()).toBeNull();

    fireEvent.click(canvasToggle());
    await landed();
    expect(screen.getByRole("button", { name: vi.canvas.newCanvas })).toBeInTheDocument();
    expect(frame()).toBeNull();
  });

  it("does not keep the canvas the agent made from opening by itself", async () => {
    const turn = await watching();
    fireEvent.click(within(shownFrame()).getByRole("button", { name: text.close }));

    store();
    await stream(turn, piece(LAST), answer([create]), started(create));
    expect(storedTitle()).toBeNull();
    await stream(turn, ended(create, TAGGED));

    expect(frame()).toBeNull();
    expect(storedTitle()).toBeInTheDocument();
    expect(layout()).toHaveClass("with-canvas");
  });
});

describe("a canvas the agent is writing while the person types in another", () => {
  /** "Ghi chú" open with the person typing in it, and the agent at the first piece of its own. */
  async function typing() {
    await openChat(1440);
    await openNote();
    const turn = await startTurn(backend);
    act(() => editor()?.focus());
    typeInCanvas(THEIRS);
    await stream(turn, piece(HEAD));
    return turn;
  }

  it("does not come up over their canvas, and showing it from its card saves theirs as leaving it does", async () => {
    const turn = await typing();
    await stream(turn, piece(MORE));

    expect(frame()).toBeNull();
    expect(writingCards()).toHaveLength(1);
    expect(editor()).toHaveFocus();
    expect(saved()).toEqual([]);

    const opened = focusWrites(backend).length;
    await pressShow();

    expect(shownFrame()).toHaveTextContent("Việc một");
    expect(within(shownFrame()).getByRole("button", { name: text.close })).toHaveFocus();
    expect(editor()).toBeNull();
    expect(saved()).toEqual([{ base_version: 1, content: THEIRS }]);
    expect(focusWrites(backend)).toHaveLength(opened);

    fireEvent.click(within(shownFrame()).getByRole("button", { name: text.close }));
    await landed();

    expect(frame()).toBeNull();
    expect(editor()).toHaveValue(THEIRS);
    expect(saved()).toHaveLength(1);
    expect(backend.canvas.content("a1")).toBe(THEIRS);
  });

  it("gives way to the canvas the agent made once theirs is saved, their text in the store", async () => {
    const turn = await typing();
    await pressShow();
    expect(frame()).not.toBeNull();

    store();
    await stream(turn, piece(MORE + LAST), answer([create]), started(create));
    await stream(turn, ended(create, TAGGED));

    expect(frame()).toBeNull();
    expect(storedTitle()).toBeInTheDocument();
    expect(backend.canvas.content("a1")).toBe(THEIRS);
    expect(saved()).toEqual([{ base_version: 1, content: THEIRS }]);
    expect(backend.canvas.content(PLAN)).toBe(WRITE.content);
  });

  it("gives their canvas back with what they typed when it could not be saved, though they watched the agent's be written", async () => {
    const turn = await typing();
    backend.canvas.refuseNext("PUT", 500);
    await pressShow();
    expect(frame()).not.toBeNull();
    expect(backend.canvas.content("a1")).toBe("");

    store();
    await stream(turn, piece(MORE + LAST), answer([create]), started(create));
    await stream(turn, ended(create, TAGGED));

    expect(frame()).toBeNull();
    expect(storedTitle()).toBeNull();
    expect(editor()).toHaveValue(THEIRS);
    expect(saved()).toEqual([{ base_version: 1, content: THEIRS }]);
    expect(backend.canvas.content("a1")).toBe("");
  });
});
