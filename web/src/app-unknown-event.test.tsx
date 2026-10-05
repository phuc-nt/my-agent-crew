import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentEvent } from "./api/types";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, storedMessage } from "./test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  vitest.stubGlobal("fetch", backend.fetch);
  window.location.hash = "";
});

afterEach(() => vitest.unstubAllGlobals());

// A server newer than the bundle sends kinds of event added since. The name is made up so that
// no later build comes to know it.
const UNKNOWN = { type: "kind_added_since", index: 0, chunk: '{"ti' } as unknown as AgentEvent;

const box = () => screen.getByRole("textbox");

/** Opens a stored conversation and holds its next turn open, so what the turn has streamed so
 *  far stays on screen to be read. */
async function openHeld(title: string, events: AgentEvent[]) {
  const c = backend.create({ title, messages: [storedMessage("user", "chào")] });
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: new RegExp(title) }));
  await screen.findByRole("heading", { level: 1, name: title });
  const held = backend.holdTurn(c.id);
  backend.nextTurn = events;
  return held;
}

/** Everything the stream had ready has been read and drawn by the time this returns: the reads
 *  are promises all the way, and a timer runs only after them. */
const drained = () => act(() => new Promise<void>((resolve) => setTimeout(resolve, 0)));

function nothingBroke() {
  expect(screen.queryByTestId("notice")).toBeNull();
  // The boundary around the thread, which is what a reducer that lost its state ends in.
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.queryByText(vi.crashed)).toBeNull();
}

describe("a turn that carries an event of a kind this build does not know", () => {
  it("ends with the whole reply shown and nothing said to have gone wrong", async () => {
    backend.nextTurn = [
      { type: "text_delta", text: "Xin " },
      UNKNOWN,
      { type: "text_delta", text: "chào" },
      { type: "assistant_message", message_id: "a1", content: "Xin chào", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
      { type: "done", spent_usd: 0.02, unknown_cost_calls: 0 },
    ];
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));
    await userEvent.type(box(), "hello{Enter}");

    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Xin chào");
    expect(screen.getByTestId("message-user")).toHaveTextContent("hello");
    expect(screen.getByTestId("budget")).toHaveTextContent("$0.02 / $1.00");
    nothingBroke();
    // The turn is over and the composer is the person's again.
    expect(box()).toBeEnabled();
    expect(screen.getByTestId("status-line")).toHaveTextContent(vi.statusIdle);
  });

  it("goes on drawing the reply as it arrives, with the words from both sides of the event", async () => {
    const held = await openHeld("Đang viết", [{ type: "text_delta", text: "Xin " }, UNKNOWN, { type: "text_delta", text: "chào" }]);
    await userEvent.type(box(), "viết tiếp{Enter}");

    await waitFor(() => expect(screen.getByTestId("streaming")).toHaveTextContent("Xin chào"));
    await drained();
    expect(screen.getByTestId("streaming")).toHaveTextContent("Xin chào");
    nothingBroke();
    held.release();
    await waitFor(() => expect(screen.queryByTestId("streaming")).toBeNull());
  });

  it("leaves a model that is thinking said to be thinking", async () => {
    const held = await openHeld("Đang nghĩ", [{ type: "thinking" }, UNKNOWN]);
    await userEvent.type(box(), "nghĩ giúp{Enter}");

    const line = screen.getByTestId("status-line");
    await waitFor(() => expect(line).toHaveTextContent(vi.statusThinking));
    await drained();
    // An event nothing here understands is no sign that the model moved on to its answer.
    expect(line).toHaveTextContent(vi.statusThinking);
    nothingBroke();
    held.release();
    await waitFor(() => expect(line).not.toHaveTextContent(vi.statusThinking));
  });
});
