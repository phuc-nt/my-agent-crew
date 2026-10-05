import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { AgentEvent, ToolCall } from "./api/types";
import { vi } from "./i18n/vi";
import { box, layout, openChat, startApp } from "./test/canvas-app";
import { landed, stopServer } from "./test/canvas-hook";
import {
  answer,
  done,
  ended,
  frame,
  type HeldTurn,
  piece,
  shownFrame,
  startOver,
  startTurn,
  stream,
  writingCards,
} from "./test/canvas-writing-turn";
import type { FakeBackend } from "./test/fake-backend";

const text = vi.canvas.writing;

/** A canvas as the model writes it, in two pieces: enough for it to come up by itself. */
const HEAD = '{"title":"Kế hoạch tuần","kind":"markdown","content":"Việc';
const MORE = " một";
/** The canvas the same turn goes on to write afterwards. */
const NEXT = '{"title":"Danh sách chợ","kind":"markdown","content":"Rau';
const NEXT_MORE = " cải";

/** A call that waits for the person's word before it runs. */
const write: ToolCall = { id: "f1", name: "write_file", arguments: { path: "ghi.md", content: "x" } };
const asks: AgentEvent = {
  type: "approval_required",
  approval_id: "ap1",
  tool_call_id: write.id,
  name: write.name,
  arguments: write.arguments,
  reason: "",
  expires_at: "2099-01-01T00:00:00Z",
};

let backend: FakeBackend;

beforeEach(() => {
  backend = startApp();
});

afterEach(stopServer);

/** A wide screen on which the agent has written enough of a canvas for it to come up. */
async function watching(): Promise<HeldTurn> {
  await openChat(1440);
  const turn = await startTurn(backend);
  await stream(turn, piece(HEAD));
  await stream(turn, piece(MORE));
  expect(shownFrame()).toHaveTextContent("Việc một");
  return turn;
}

/** The person puts the canvas being written away with its own close button. */
async function putAway() {
  fireEvent.click(within(shownFrame()).getByRole("button", { name: text.close }));
  await landed();
  expect(frame()).toBeNull();
}

/** The model starts its answer over and asks to write a file instead: the turn stops there, for the person. */
async function pauseForThePerson(turn: HeldTurn) {
  await stream(turn, ...startOver(1), answer([write]), asks);
  await act(async () => turn.release());
  await landed();
  expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  expect(writingCards()).toEqual([]);
  expect(frame()).toBeNull();
}

/** The person allows the call, and the turn goes on in a stream that stays open to be fed. */
async function approve(): Promise<HeldTurn> {
  const resumed = backend.holdTurn("c1");
  fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: vi.approve }));
  await landed();
  await landed();
  await landed();
  await stream(resumed, ended(write, "Đã ghi ghi.md."));
  expect(screen.queryByRole("alertdialog")).toBeNull();
  return resumed;
}

/** The agent writes the first two pieces of its next canvas. */
async function writeNext(turn: HeldTurn) {
  await stream(turn, piece(NEXT));
  await stream(turn, piece(NEXT_MORE));
  expect(writingCards()).toHaveLength(1);
  expect(within(writingCards()[0]).getByText("Danh sách chợ")).toBeInTheDocument();
}

async function leaveForManageAndComeBack() {
  fireEvent.click(screen.getByRole("button", { name: /Quản lý/ }));
  await landed();
  expect(screen.queryByRole("textbox", { name: vi.composerPlaceholder })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: vi.manage.backToChat }));
  await landed();
  await landed();
  expect(box()).toBeInTheDocument();
}

describe("a canvas being written that the person put away, when the turn stops to ask them something", () => {
  it("leaves the next canvas of that turn to its card once they have answered", async () => {
    const turn = await watching();
    await putAway();
    await pauseForThePerson(turn);

    const resumed = await approve();
    await writeNext(resumed);

    expect(frame()).toBeNull();
    expect(layout()).toHaveClass("with-activity");

    // The card still shows it, and putting that away is as it was.
    fireEvent.click(within(writingCards()[0]).getByRole("button", { name: text.showLabel("Danh sách chợ") }));
    await landed();
    expect(shownFrame()).toHaveTextContent("Rau cải");
  });

  it("brings the next canvas up as before when they had put nothing away", async () => {
    const turn = await watching();
    await pauseForThePerson(turn);

    const resumed = await approve();
    await writeNext(resumed);

    expect(shownFrame()).toHaveTextContent("Rau cải");
    expect(layout()).toHaveClass("with-canvas");
  });
});

describe("a canvas being written that the person put away, when they leave the chat and come back mid-turn", () => {
  it("stays a card, at their return and at every later piece", async () => {
    const turn = await watching();
    await putAway();

    await leaveForManageAndComeBack();

    expect(frame()).toBeNull();
    expect(writingCards()).toHaveLength(1);
    expect(layout()).toHaveClass("with-activity");

    await stream(turn, piece("\\n\\nViệc hai"));

    expect(frame()).toBeNull();
    expect(writingCards()).toHaveLength(1);
  });

  it("comes up again at their return when they had not put it away", async () => {
    await watching();

    await leaveForManageAndComeBack();

    expect(shownFrame()).toHaveTextContent("Việc một");
  });
});

describe("a canvas being written that the person put away, once that turn is over", () => {
  it("does not keep the next turn's canvas from coming up by itself", async () => {
    const turn = await watching();
    await putAway();
    await stream(turn, ...startOver(1), answer([], "Thôi, để sau."), done);
    await act(async () => turn.release());
    await landed();

    const next = await startTurn(backend, "viết danh sách chợ");
    await writeNext(next);

    expect(shownFrame()).toHaveTextContent("Rau cải");
  });

  it("does not keep the next turn's canvas down after the person stopped the turn", async () => {
    const turn = await watching();
    await putAway();
    fireEvent.click(screen.getByRole("button", { name: vi.stop }));
    await landed();
    await landed();
    // The server gives the turn up with the stream the page cut.
    turn.release();
    expect(writingCards()).toEqual([]);

    const next = await startTurn(backend, "viết danh sách chợ");
    await writeNext(next);

    expect(shownFrame()).toHaveTextContent("Rau cải");
  });
});
