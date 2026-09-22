import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { conversationFamilyRuns, emptyActivity } from "../state/activity-reducer";
import { fakeRun } from "../test/fake-backend";
import { ConversationActivity } from "./conversation-activity";

const name = (id: string) => (id === "coach" ? "HLV" : "Agent");

function show(runs = [fakeRun()], spentUsd = 0) {
  return render(
    <ConversationActivity
      runs={runs}
      conversationId="c1"
      spentUsd={spentUsd}
      agentName={name}
      onOpenConversation={() => undefined}
    />,
  );
}

/** This runner has no `localStorage` of its own, so the tests bring one. */
function useMemoryStorage() {
  const store = new Map<string, string>();
  vitest.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    clear: () => store.clear(),
  });
}

beforeEach(useMemoryStorage);
afterEach(() => vitest.unstubAllGlobals());

describe("the activity strip inside a chat", () => {
  it("shows nothing at all for a conversation that has never run", () => {
    const { container } = show([]);

    expect(container).toBeEmptyDOMElement();
  });

  it("is one line until it is opened, then shows the timeline", async () => {
    show([fakeRun({ status: "running", finished_at: null })]);
    expect(screen.queryByTestId("run-card")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: vi.conversationActivity.expand }));

    expect(screen.getByTestId("run-card")).toBeInTheDocument();
  });

  // Collapsed with nothing running, the bar is all the person sees — a label on its own
  // tells them nothing about the turn that just finished.
  it("describes the last finished run while collapsed, not just a label", () => {
    show([fakeRun({ status: "done", steps: [] })]);

    const strip = screen.getByTestId("conversation-activity");
    expect(strip).toHaveTextContent(vi.conversationActivity.lastRun);
    expect(strip).toHaveTextContent(vi.runStatus.done);
    expect(strip).toHaveTextContent(vi.runSteps(0));
  });

  it("keeps a live run's progress line visible while collapsed", () => {
    show([fakeRun({ status: "running", finished_at: null })]);

    expect(screen.getByTestId("run-progress")).toBeInTheDocument();
  });

  it("remembers being open, so the choice survives switching conversations", async () => {
    const { unmount } = show([fakeRun()]);
    await userEvent.click(screen.getByRole("button", { name: vi.conversationActivity.expand }));
    unmount();

    show([fakeRun()]);

    expect(screen.getByTestId("run-card")).toBeInTheDocument();
  });

  const step = (model: string) => ({
    kind: "model" as const,
    chars: 10,
    provider: "openrouter",
    model,
    cost_usd: 0.01,
    tool_calls: [],
    preview: "",
    duration_ms: 100,
  });

  it("counts the work and the models across the conversation's runs", async () => {
    show(
      [
        fakeRun({ id: "a", steps: [step("deepseek"), step("deepseek")] }),
        // Delegated work belongs to the conversation that asked for it.
        fakeRun({ id: "b", conversation_id: "child", source: "delegate:c1", steps: [step("sonnet")] }),
      ],
      0.05,
    );

    await userEvent.click(screen.getByRole("button", { name: vi.conversationActivity.expand }));

    const cost = screen.getByTestId("conversation-cost");
    expect(cost).toHaveTextContent(vi.conversationActivity.steps(3));
    expect(cost).toHaveTextContent(vi.conversationActivity.delegated(1));
    expect(cost).toHaveTextContent("deepseek, sonnet");
  });

  // A run's own `spent_usd` is the conversation's running total, and a delegated child's
  // spend is already inside the parent's. Adding the rows up bills the same money twice.
  it("reports the conversation's own total, not the sum of its runs", async () => {
    show(
      [
        fakeRun({ id: "parent", conversation_id: "c1", spent_usd: 0.12, steps: [step("gpt-4")] }),
        fakeRun({ id: "child", conversation_id: "work-1", source: "delegate:c1", spent_usd: 0.05, steps: [step("claude")] }),
      ],
      0.12,
    );

    await userEvent.click(screen.getByRole("button", { name: vi.conversationActivity.expand }));

    const cost = screen.getByTestId("conversation-cost");
    expect(cost).toHaveTextContent(vi.conversationActivity.spent(0.12));
    expect(cost).not.toHaveTextContent(vi.conversationActivity.spent(0.17));
  });

  it("counts multiple delegated runs separately in the cost row", async () => {
    show(
      [
        fakeRun({ id: "parent", conversation_id: "c1", steps: [step("gpt-4")] }),
        fakeRun({ id: "child1", conversation_id: "work-1", source: "delegate:c1", steps: [step("claude")] }),
        fakeRun({ id: "child2", conversation_id: "work-2", source: "delegate:c1", steps: [step("llama")] }),
        fakeRun({ id: "child3", conversation_id: "work-3", source: "delegate:c1", steps: [step("sonnet")] }),
      ],
      0.1,
    );

    await userEvent.click(screen.getByRole("button", { name: vi.conversationActivity.expand }));

    const cost = screen.getByTestId("conversation-cost");
    expect(cost).toHaveTextContent(vi.conversationActivity.spent(0.1));
    expect(cost).toHaveTextContent(vi.conversationActivity.steps(4));
    expect(cost).toHaveTextContent(vi.conversationActivity.delegated(3));
    expect(cost).toHaveTextContent("gpt-4, claude, llama, sonnet");
  });

  // A private window, or a browser with site data blocked, has no storage to read.
  it("still works where the browser refuses to remember anything", async () => {
    vitest.stubGlobal("localStorage", undefined);
    show([fakeRun()]);

    await userEvent.click(screen.getByRole("button", { name: vi.conversationActivity.expand }));

    expect(screen.getByTestId("run-card")).toBeInTheDocument();
  });
});

describe("which runs belong to a chat", () => {
  const state = (runs = [fakeRun()]) => ({
    ...emptyActivity,
    runs: Object.fromEntries(runs.map((r) => [r.id, r])),
  });

  it("leaves out another conversation's run", () => {
    const mine = fakeRun({ id: "mine", conversation_id: "c1" });
    const theirs = fakeRun({ id: "theirs", conversation_id: "c2" });

    expect(conversationFamilyRuns(state([mine, theirs]), "c1").map((r) => r.id)).toEqual(["mine"]);
  });

  // The delegate works on the parent's behalf, so the parent must not look idle meanwhile.
  it("includes the run of work this conversation delegated", () => {
    const parent = fakeRun({ id: "parent", conversation_id: "c1" });
    const child = fakeRun({ id: "child", conversation_id: "child-conv", source: "delegate:c1" });

    const ids = conversationFamilyRuns(state([parent, child]), "c1").map((r) => r.id);

    expect(ids.sort()).toEqual(["child", "parent"]);
  });
});
