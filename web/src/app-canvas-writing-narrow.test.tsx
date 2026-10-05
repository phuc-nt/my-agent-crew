import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ToolCall } from "./api/types";
import { vi } from "./i18n/vi";
import { bodies, focusWrites, openChat, startApp } from "./test/canvas-app";
import { landed, stopServer } from "./test/canvas-hook";
import {
  answer,
  canvasToggle,
  ended,
  frame,
  type HeldTurn,
  piece,
  shownFrame,
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

const HEAD = '{"title":"Kế hoạch tuần","kind":"markdown","content":"Việc';
const MORE = " một\\n\\nViệc";
const LAST = ' hai"}';

let backend: FakeBackend;
let turn: HeldTurn;

/** A narrow screen on which the agent has written enough of the canvas for a wide one to show it. */
beforeEach(async () => {
  backend = startApp();
  await openChat(1000);
  turn = await startTurn(backend);
  await stream(turn, piece(HEAD));
  await stream(turn, piece(MORE));
});

afterEach(stopServer);

const main = () => document.querySelector("main") as HTMLElement;
const overlay = () => screen.queryByRole("region", { name: vi.canvas.button });
const showButton = () => within(writingCards()[0]).getByRole("button", { name: text.showLabel(TITLE) });
const closeButton = () => within(shownFrame()).getByRole("button", { name: text.close });

/** The person presses the card's button with the keyboard on it. */
function ask() {
  showButton().focus();
  fireEvent.click(showButton());
}

describe("a canvas the agent is writing on a screen too narrow to hold it beside the thread", () => {
  it("is a card in the thread and covers nothing by itself", () => {
    expect(writingCards()).toHaveLength(1);
    expect(frame()).toBeNull();
    expect(overlay()).toBeNull();
    expect(main()).not.toHaveAttribute("inert");
    expect(canvasToggle()).toHaveAttribute("aria-expanded", "false");
  });

  it("covers the chat when the person asks to see it, with the keyboard on its close button", async () => {
    ask();

    expect(overlay()).toContainElement(shownFrame());
    expect(shownFrame()).toHaveTextContent("Việc một");
    expect(main()).toHaveAttribute("inert");
    expect(closeButton()).toHaveFocus();
    expect(canvasToggle()).toHaveAttribute("aria-expanded", "true");

    await stream(turn, piece(LAST));

    expect(shownFrame()).toHaveTextContent("Việc hai");
    expect(closeButton()).toHaveFocus();
    expect(focusWrites(backend)).toEqual([]);
    expect(bodies(backend)).toEqual([{ text: "viết kế hoạch tuần" }]);
  });

  it("is left with Escape, which gives back the chat and puts the keyboard back on the card's button", () => {
    ask();

    fireEvent.keyDown(document.body, { key: "Escape" });

    expect(frame()).toBeNull();
    expect(overlay()).toBeNull();
    expect(main()).not.toHaveAttribute("inert");
    expect(showButton()).toHaveFocus();
    expect(writingCards()).toHaveLength(1);
  });

  it("is left by the way back to the chat and by its own close button, the keyboard going back to the card's button", () => {
    ask();

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.backToChat }));

    expect(frame()).toBeNull();
    expect(overlay()).toBeNull();
    expect(main()).not.toHaveAttribute("inert");
    expect(showButton()).toHaveFocus();

    ask();
    fireEvent.click(closeButton());

    expect(frame()).toBeNull();
    expect(showButton()).toHaveFocus();
  });

  it("is left by Escape for the canvas the dock held, which Escape then puts away", async () => {
    fireEvent.click(canvasToggle());
    await landed();
    fireEvent.click(screen.getByRole("button", { name: /Ghi chú/ }));
    await landed();
    const note = screen.getByRole("heading", { level: 2, name: "Ghi chú" });
    expect(note).toBeVisible();

    // The card is under the canvas covering the chat: a person gets here by narrowing a wide
    // window, and the test by pressing what they could not reach.
    fireEvent.click(showButton());
    expect(note).not.toBeVisible();

    fireEvent.keyDown(document.body, { key: "Escape" });

    expect(frame()).toBeNull();
    expect(note).toBeVisible();
    expect(overlay()).not.toBeNull();

    fireEvent.keyDown(document.body, { key: "Escape" });
    await landed();

    expect(overlay()).toBeNull();
  });

  it("gives way to the canvas the agent made, over the chat, when the person was watching", async () => {
    ask();
    backend.canvas.add({ id: PLAN, title: TITLE, agent_id: "master", content: WRITE.content, conversationIds: ["c1"] });

    await stream(turn, piece(LAST), answer([create]), started(create));
    expect(within(shownFrame()).getByText(text.saving)).toBeInTheDocument();
    await stream(turn, ended(create, TAGGED));

    expect(frame()).toBeNull();
    expect(overlay()).toContainElement(screen.getByRole("heading", { level: 2, name: TITLE }));
    expect(main()).toHaveAttribute("inert");
    expect(focusWrites(backend)).toEqual([]);
  });

  it("leaves the chat uncovered when the canvas is made and the person was not watching", async () => {
    backend.canvas.add({ id: PLAN, title: TITLE, agent_id: "master", content: WRITE.content, conversationIds: ["c1"] });

    await stream(turn, piece(LAST), answer([create]), started(create));
    await stream(turn, ended(create, TAGGED));

    expect(frame()).toBeNull();
    expect(overlay()).toBeNull();
    expect(main()).not.toHaveAttribute("inert");
  });
});
