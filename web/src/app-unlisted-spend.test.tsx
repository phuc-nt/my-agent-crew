import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, coachAgent, fakeAgent, fakeRun } from "./test/fake-backend";
import { forgetScreenListeners, screenAt } from "./test/screen-width";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  backend.agents = [fakeAgent, coachAgent];
  FakeEventSource.instances = [];
  forgetScreenListeners();
  // Wide, so the activity column is open beside the chat without a press.
  screenAt(1440);
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vitest.unstubAllGlobals();
  window.location.hash = "";
});

function stream(): FakeEventSource {
  const source = FakeEventSource.instances.at(-1);
  if (!source) throw new Error("the app has not subscribed to the activity stream");
  return source;
}

/** Opens `id` by its address, the only way into a conversation the list does not hold. */
async function open(id: string, title: string) {
  window.location.hash = `#/chat/${id}`;
  render(<App />);
  await screen.findByRole("heading", { level: 1, name: title });
  act(() => {
    stream().open();
    stream().emit({ type: "snapshot", runs: [] });
  });
}

const cost = () => screen.findByTestId("conversation-cost");
const chip = () => screen.getByTestId("budget");
const spent = vi.conversationActivity.spent;

describe("what a conversation has spent, in the header and in the overview", () => {
  // The sidebar lists the master's conversations only. Another agent's is opened by its
  // address, and nothing reads its row again when its run ends.
  it("is one figure for a conversation outside the list once its turn ends", async () => {
    const c = backend.create({ title: "Việc của HLV", agent_id: "coach" });
    await open(c.id, "Việc của HLV");
    expect(within(screen.getByRole("navigation")).queryByRole("button", { name: /Việc của HLV/ })).not.toBeInTheDocument();

    backend.nextTurn = [
      { type: "assistant_message", message_id: "m1", content: "Đã làm rồi.", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0.0123 },
      { type: "done", spent_usd: 0.0123, unknown_cost_calls: 0 },
    ];
    await userEvent.type(screen.getByRole("textbox"), "làm đi{Enter}");
    await screen.findByText("Đã làm rồi.");
    // What the server keeps, and the run's end as the stream tells every tab.
    c.spent_usd = 0.0123;
    act(() => stream().emit({ type: "run", run: fakeRun({ id: "t1", agent_id: "coach", conversation_id: c.id, spent_usd: 0.0123 }) }));

    await waitFor(() => expect(chip()).toHaveTextContent("$0.01"));
    expect(await cost()).toHaveTextContent(spent(0.0123));
    expect(await cost()).not.toHaveTextContent(spent(0));
  });

  it("is one figure for a listed conversation before its row is read again", async () => {
    const c = backend.create({ title: "Chung", spent_usd: 0.1 });
    backend.runs = [fakeRun({ id: "before", conversation_id: c.id, spent_usd: 0.1 })];
    await open(c.id, "Chung");
    expect(await cost()).toHaveTextContent(spent(0.1));

    backend.nextTurn = [
      { type: "assistant_message", message_id: "m1", content: "Đã làm rồi.", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0.15 },
      { type: "done", spent_usd: 0.25, unknown_cost_calls: 0 },
    ];
    await userEvent.type(screen.getByRole("textbox"), "làm đi{Enter}");
    await screen.findByText("Đã làm rồi.");

    // No run has ended on the stream, so the list still holds the row it first read.
    await waitFor(() => expect(chip()).toHaveTextContent("$0.25"));
    expect(await cost()).toHaveTextContent(spent(0.25));
  });
});

describe("a spent budget in a conversation outside the list", () => {
  it("holds the composer and offers one raise once the turn halts, and a raise lifts it", async () => {
    const c = backend.create({ title: "Việc của HLV", agent_id: "coach", cost_cap_usd: 1 });
    await open(c.id, "Việc của HLV");

    backend.nextTurn = [{ type: "halted", reason: "budget", spent_usd: 1 }];
    await userEvent.type(screen.getByRole("textbox"), "tiếp{Enter}");
    expect(await screen.findByTestId("notice")).toHaveTextContent(vi.haltedBudget);
    // What the server keeps once the turn halts; no list row will ever bring it here.
    c.spent_usd = 1;
    c.over_budget = true;
    act(() => stream().emit({ type: "run", run: fakeRun({ id: "t1", agent_id: "coach", conversation_id: c.id, status: "halted", spent_usd: 1 }) }));

    const over = await screen.findByTestId("over-budget");
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getAllByRole("button", { name: vi.budgetCard.raise })).toEqual([
      within(over).getByRole("button", { name: vi.budgetCard.raise }),
    ]);
    expect(await cost()).toHaveTextContent(spent(1));
    expect(await cost()).toHaveTextContent(vi.conversationActivity.capShare("$1.00", 100));

    await userEvent.click(within(over).getByRole("button", { name: vi.budgetCard.raise }));
    await userEvent.click(within(over).getByRole("button", { name: "+$1.00" }));
    await waitFor(() => expect(screen.queryByTestId("over-budget")).not.toBeInTheDocument());
    expect(screen.getByRole("textbox")).toBeEnabled();
    expect(await cost()).toHaveTextContent(vi.conversationActivity.capShare("$2.00", 50));
  });
});
