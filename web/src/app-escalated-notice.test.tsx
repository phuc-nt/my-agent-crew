import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentEvent } from "./api/types";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource } from "./test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "";
});

afterEach(() => vitest.unstubAllGlobals());

const ANSWER: AgentEvent[] = [
  { type: "assistant_message", message_id: "m9", content: "Đã xong.", tool_calls: [], provider: "openrouter", model: "big", cost_usd: 0.01 },
  { type: "done", spent_usd: 0.01, unknown_cost_calls: 0 },
];

/** Sends one message in a conversation whose turn the server answers with `events`. */
async function turn(events: AgentEvent[]) {
  backend.create({ title: "Bị kẹt" });
  backend.nextTurn = events;
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: /Bị kẹt/ }));
  act(() => {
    const source = FakeEventSource.instances.at(-1);
    source?.open();
    source?.emit({ type: "snapshot", runs: [] });
  });
  await userEvent.type(screen.getByRole("textbox"), "tiếp{Enter}");
  return screen.findByTestId("notice");
}

describe("a turn that moved to its escalation route", () => {
  it("tells the reader the route the rest of it ran on when no route of its own answered", async () => {
    const notice = await turn([
      { type: "route_fallback", provider: "openrouter", model: "flash", error: "HTTP 502" },
      { type: "escalated", reason: "error", provider: "openrouter", model: "big", error: "every route failed" },
      ...ANSWER,
    ]);

    expect(notice).toHaveTextContent(vi.routeEscalated("error", "openrouter:big"));
    expect(notice).toHaveClass("notice", "escalated");
    expect(notice).not.toHaveTextContent(vi.errorPrefix);
    expect(notice).not.toHaveTextContent(vi.routeFallback("openrouter:flash — HTTP 502"));
    // The answer the new route gave is in the thread: the notice is not the end of the turn.
    expect(await screen.findByText("Đã xong.")).toBeInTheDocument();
  });

  it("says so in other words when the turn was repeating itself", async () => {
    const notice = await turn([
      { type: "escalated", reason: "loop", provider: "openrouter", model: "big", error: "" },
      ...ANSWER,
    ]);

    expect(notice).toHaveTextContent(vi.routeEscalated("loop", "openrouter:big"));
    expect(vi.routeEscalated("loop", "openrouter:big")).not.toBe(vi.routeEscalated("error", "openrouter:big"));
  });
});
