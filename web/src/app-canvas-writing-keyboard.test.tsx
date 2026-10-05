import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { vi } from "./i18n/vi";
import { box, layout, openChat, openNote, startApp } from "./test/canvas-app";
import { landed, sent, stopServer } from "./test/canvas-hook";
import { canvasToggle, frame, panel, piece, shownFrame, startTurn, stream, writingCards } from "./test/canvas-writing-turn";
import type { FakeBackend } from "./test/fake-backend";
import { resize } from "./test/screen-width";

const TITLE = "Kế hoạch tuần";
const text = vi.canvas.writing;

/** The call's arguments as the model writes them, in three pieces: a canvas comes up at the second. */
const HEAD = '{"title":"Kế hoạch tuần","kind":"markdown","content":"Việc';
const MORE = " một\\n\\nViệc";
const LAST = ' hai"}';

let backend: FakeBackend;

beforeEach(() => {
  backend = startApp();
});

afterEach(stopServer);

const showButton = () => within(writingCards()[0]).getByRole("button", { name: text.showLabel(TITLE) });
const keyboardOn = (control: HTMLElement) => act(() => control.focus());

async function openList() {
  fireEvent.click(canvasToggle());
  await landed();
}

/** Where in the column the keyboard may be with nothing typed there: what the column shows, and what holds the keyboard. */
type Place = { open(): Promise<void>; control(): HTMLElement };

const places: [string, Place][] = [
  ["on a button of their open canvas", { open: openNote, control: () => screen.getByRole("button", { name: vi.canvas.history }) }],
  ["on a tab of the column", { open: openNote, control: () => screen.getByRole("tab", { name: vi.canvas.tabs.activity }) }],
  ["in the list of canvases", { open: openList, control: () => screen.getByRole("button", { name: vi.canvas.newCanvas }) }],
  ["in the activity, with no canvas open", { open: async () => {}, control: () => screen.getByText(vi.noRuns) }],
];

describe("a canvas the agent is writing while the keyboard is in the column beside the chat", () => {
  it.each(places)("does not come up by itself with the keyboard %s, though nothing is typed there", async (_, place) => {
    await openChat(1440);
    await place.open();
    const turn = await startTurn(backend);
    const control = place.control();
    keyboardOn(control);
    expect(control).toHaveFocus();

    await stream(turn, piece(HEAD));
    await stream(turn, piece(MORE));

    expect(frame()).toBeNull();
    expect(writingCards()).toHaveLength(1);
    expect(control).toHaveFocus();
    expect(sent(backend, "PUT")).toEqual([]);
  });

  it("stays down once the keyboard is back in the chat box, and its card still shows it", async () => {
    await openChat(1440);
    await openNote();
    const turn = await startTurn(backend);
    keyboardOn(screen.getByRole("button", { name: vi.canvas.history }));
    await stream(turn, piece(HEAD));
    await stream(turn, piece(MORE));
    expect(frame()).toBeNull();

    keyboardOn(box());
    await stream(turn, piece(LAST));

    expect(frame()).toBeNull();
    expect(panel()).toBeVisible();

    fireEvent.click(showButton());
    await landed();

    expect(shownFrame()).toHaveTextContent("Việc hai");
    expect(panel()).not.toBeVisible();
  });

  it("comes up over their open canvas while the keyboard is in the chat box and nothing is typed there", async () => {
    await openChat(1440);
    await openNote();
    const turn = await startTurn(backend);
    expect(box()).toHaveFocus();

    await stream(turn, piece(HEAD));
    await stream(turn, piece(MORE));

    expect(shownFrame()).toHaveTextContent("Việc một");
    expect(panel()).not.toBeVisible();
    expect(box()).toHaveFocus();
  });
});

describe("a canvas the agent is writing as a narrow screen widens", () => {
  it("does not come up by itself with the keyboard still in the canvas that covered the chat", async () => {
    await openChat(1000);
    const turn = await startTurn(backend);
    await stream(turn, piece(HEAD));
    await openNote();
    const control = screen.getByRole("button", { name: vi.canvas.history });
    keyboardOn(control);
    expect(layout()).not.toHaveClass("with-canvas");

    resize(1440);
    await landed();

    expect(layout()).toHaveClass("with-canvas");
    expect(control).toHaveFocus();

    await stream(turn, piece(MORE));

    expect(frame()).toBeNull();
    expect(writingCards()).toHaveLength(1);
    expect(control).toHaveFocus();
  });

  it("comes up at the next piece when the keyboard was in the chat box as it widened", async () => {
    await openChat(1000);
    const turn = await startTurn(backend);
    await stream(turn, piece(HEAD));
    expect(frame()).toBeNull();

    resize(1440);
    await landed();
    await stream(turn, piece(MORE));

    expect(shownFrame()).toHaveTextContent("Việc một");
    expect(box()).toHaveFocus();
  });
});
