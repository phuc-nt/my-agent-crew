import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { conversationFamilyRuns, emptyActivity } from "../state/activity-reducer";
import { FakeBackend, fakeRun } from "../test/fake-backend";
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

beforeEach(() => {
  useMemoryStorage();
  // The strip asks for its stored runs on mount; here there are none to find.
  vitest.stubGlobal("fetch", new FakeBackend().fetch);
});
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

describe("the activity column beside a chat on a wide screen", () => {
  function dock(runs = [fakeRun()]) {
    return render(
      <ConversationActivity
        runs={runs}
        conversationId="c1"
        spentUsd={0}
        agentName={name}
        onOpenConversation={() => undefined}
        docked
      />,
    );
  }

  it("is open from the start, with nothing to collapse", () => {
    dock([fakeRun({ status: "running", finished_at: null })]);

    const column = screen.getByTestId("conversation-activity");
    expect(column.tagName).toBe("ASIDE");
    expect(column).toHaveTextContent(vi.conversationActivity.title);
    expect(screen.getByTestId("run-card")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: vi.conversationActivity.collapse })).not.toBeInTheDocument();
  });

  // The column holds its place so the chat does not jump sideways on the first run.
  it("stays in place for a conversation that has never run, saying so", async () => {
    dock([]);

    // Once the history has answered: until then it cannot know, and says it is loading.
    await waitFor(() => expect(screen.getByTestId("conversation-activity")).toHaveTextContent(vi.noRuns));
  });

  // Open by design is not a choice the person made; the strip must not inherit it.
  it("leaves the strip's remembered open state alone", () => {
    const { unmount } = dock();
    unmount();

    show([fakeRun()]);

    expect(screen.queryByTestId("run-card")).not.toBeInTheDocument();
  });
});

describe("a conversation's runs from before the page opened", () => {
  let backend: FakeBackend;
  beforeEach(() => {
    backend = new FakeBackend();
    vitest.stubGlobal("fetch", backend.fetch);
  });

  const strip = (runs: RunInfo[]) => (
    <ConversationActivity
      runs={runs}
      conversationId="c1"
      spentUsd={0}
      agentName={name}
      onOpenConversation={() => undefined}
      docked
    />
  );
  const historyAsked = () =>
    backend.requests.filter((r) => r.path.startsWith("/activity/runs?") && r.path.includes("conversation_id=c1"))
      .length;

  // The stream only knows what happened since the page opened; reopening a chat from last
  // week must still show what it did, delegated work included.
  it("fetches its history on mount and merges it with live runs, each run once", async () => {
    const live = fakeRun({ id: "now", status: "running", finished_at: null, started_at: "2026-09-19T09:00:00Z" });
    backend.runs = [
      { ...live, title: "Bản đã lưu" },
      fakeRun({ id: "old", title: "Hôm qua", started_at: "2026-09-18T08:00:00Z" }),
      fakeRun({ id: "kid", conversation_id: "w1", source: "delegate:c1", title: "Việc giao", started_at: "2026-09-18T08:01:00Z" }),
      fakeRun({ id: "other", conversation_id: "c2", title: "Chuyện khác" }),
    ];

    render(strip([live]));

    expect(await screen.findByText(/Hôm qua/)).toBeInTheDocument();
    expect(screen.getByText(/Việc giao/)).toBeInTheDocument();
    expect(screen.getAllByTestId("run-card")).toHaveLength(3);
    // The streamed copy of a run still going is the fresher one.
    expect(screen.queryByText(/Bản đã lưu/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Chuyện khác/)).not.toBeInTheDocument();
  });

  it("appears for a conversation with no run since the page opened", async () => {
    backend.runs = [fakeRun({ id: "old", title: "Hôm qua" })];

    render(<ConversationActivity runs={[]} conversationId="c1" spentUsd={0} agentName={name} onOpenConversation={() => undefined} />);

    expect(await screen.findByTestId("conversation-activity")).toHaveTextContent(vi.conversationActivity.lastRun);
  });

  // A run that ended while the stream was down stays "running" in the page's memory.
  it("trusts the store over a streamed copy that never heard the run end", async () => {
    const stuck = fakeRun({ id: "r1", status: "running", finished_at: null });
    backend.runs = [fakeRun({ id: "r1", status: "error" })];

    render(strip([stuck]));

    await waitFor(() => expect(screen.getByTestId("run-card")).toHaveAttribute("data-status", "error"));
  });

  // "Never ran" is only true once the store has said so.
  it("says it is loading, not that the conversation never ran, while its history is on its way", () => {
    vitest.stubGlobal("fetch", () => new Promise(() => undefined));

    render(strip([]));

    const column = screen.getByTestId("conversation-activity");
    expect(column).toHaveTextContent(vi.runFilters.loading);
    expect(column).not.toHaveTextContent(vi.noRuns);
  });

  it("says when its history cannot be read, and asks again on request", async () => {
    backend.runs = [fakeRun({ id: "old", title: "Hôm qua" })];
    let down = true;
    vitest.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) =>
      down ? Promise.reject(new Error("offline")) : backend.fetch(input, init),
    );
    render(strip([]));

    const retry = await screen.findByRole("button", { name: vi.retry });
    expect(screen.getByTestId("conversation-activity")).toHaveTextContent(vi.runFilters.failed);
    expect(screen.getByTestId("conversation-activity")).not.toHaveTextContent(vi.noRuns);
    down = false;
    await userEvent.click(retry);

    expect(await screen.findByText(/Hôm qua/)).toBeInTheDocument();
    expect(screen.queryByText(vi.runFilters.failed)).not.toBeInTheDocument();
  });

  // Hidden, the strip would pass for a conversation that never ran.
  it("shows the strip on a phone when the history cannot be read", async () => {
    vitest.stubGlobal("fetch", () => Promise.reject(new Error("offline")));

    render(<ConversationActivity runs={[]} conversationId="c1" spentUsd={0} agentName={name} onOpenConversation={() => undefined} />);

    expect(await screen.findByRole("button", { name: vi.retry })).toBeInTheDocument();
    expect(screen.getByTestId("conversation-activity")).toHaveTextContent(vi.runFilters.failed);
  });

  it("asks again when one of its runs settles", async () => {
    const running = fakeRun({ id: "r1", status: "running", finished_at: null });
    const { rerender } = render(strip([running]));
    await waitFor(() => expect(historyAsked()).toBe(1));

    rerender(strip([{ ...running, status: "done" }]));

    await waitFor(() => expect(historyAsked()).toBe(2));
  });

  // Keyed on the merged list, the stored runs arriving counted as a run settling: the
  // approvals were asked for twice on every open, blinking back to "loading" in between.
  it("asks for the approvals once on open, and again only when a run settles", async () => {
    const approvalsAsked = () => backend.requests.filter((r) => r.path.startsWith("/approvals")).length;
    const running = fakeRun({ id: "now", status: "running", finished_at: null, started_at: "2026-09-19T09:00:00Z" });
    const done = fakeRun({ id: "earlier", status: "done", started_at: "2026-09-19T08:00:00Z" });
    backend.runs = [fakeRun({ id: "old", title: "Hôm qua", started_at: "2026-09-18T08:00:00Z" })];
    const { rerender } = render(strip([running, done]));

    expect(await screen.findByText(/Hôm qua/)).toBeInTheDocument();
    await waitFor(() => expect(historyAsked()).toBe(1));
    expect(approvalsAsked()).toBe(1);

    rerender(strip([{ ...running, status: "done" }, done]));

    await waitFor(() => expect(approvalsAsked()).toBe(2));
  });
});
