import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { RunInfo, RunStep } from "../api/types";
import { vi } from "../i18n/vi";
import { activityReducer, conversationFamilyRuns, emptyActivity } from "../state/activity-reducer";
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

  // Each run starts a second after the one before, as delegated work does after the turn that
  // asked for it: the models then read newest first, not in whichever order ties happen to fall.
  const at = (second: number) => ({
    started_at: `2026-09-19T08:00:0${second}Z`,
    finished_at: `2026-09-19T08:00:1${second}Z`,
  });

  it("counts the work and the models across the conversation's runs", async () => {
    show(
      [
        fakeRun({ id: "a", ...at(0), steps: [step("deepseek"), step("deepseek")] }),
        // Delegated work belongs to the conversation that asked for it.
        fakeRun({ id: "b", ...at(1), conversation_id: "child", source: "delegate:c1", steps: [step("sonnet")] }),
      ],
      0.05,
    );

    await userEvent.click(screen.getByRole("button", { name: vi.conversationActivity.expand }));

    const cost = screen.getByTestId("conversation-cost");
    expect(cost).toHaveTextContent(vi.conversationActivity.steps(3));
    expect(cost).toHaveTextContent(vi.conversationActivity.delegated(1));
    expect(cost).toHaveTextContent("sonnet, deepseek");
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
        fakeRun({ id: "parent", ...at(0), conversation_id: "c1", steps: [step("gpt-4")] }),
        fakeRun({ id: "child1", ...at(1), conversation_id: "work-1", source: "delegate:c1", steps: [step("claude")] }),
        fakeRun({ id: "child2", ...at(2), conversation_id: "work-2", source: "delegate:c1", steps: [step("llama")] }),
        fakeRun({ id: "child3", ...at(3), conversation_id: "work-3", source: "delegate:c1", steps: [step("sonnet")] }),
      ],
      0.1,
    );

    await userEvent.click(screen.getByRole("button", { name: vi.conversationActivity.expand }));

    const cost = screen.getByTestId("conversation-cost");
    expect(cost).toHaveTextContent(vi.conversationActivity.spent(0.1));
    expect(cost).toHaveTextContent(vi.conversationActivity.steps(4));
    expect(cost).toHaveTextContent(vi.conversationActivity.delegated(3));
    expect(cost).toHaveTextContent("sonnet, llama, claude, gpt-4");
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

  // Start times are whole seconds. Two runs that shared their start and their end were
  // ordered by chance: the line named one as the last run, the card under it the other,
  // and the two swapped places once the history landed.
  it("names the same run on its line and its first card when two ran in the same second", async () => {
    const tool = (id: string): RunStep => ({ kind: "tool", name: "read_file", tool_call_id: id, arguments: {}, ok: true, output: "", duration_ms: 5 });
    const three = fakeRun({ id: "three", title: "Ba bước", steps: [tool("1"), tool("2"), tool("3")] });
    const one = fakeRun({ id: "one", title: "Một bước", steps: [tool("4")] });
    backend.runs = [three, one, fakeRun({ id: "old", title: "Hôm qua", started_at: "2026-09-18T08:00:00Z" })];
    let release = () => undefined as void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      await gate;
      return backend.fetch(input, init);
    });
    const listed = activityReducer(emptyActivity, { type: "recent", runs: [three, one] });
    const agree = () => {
      expect(screen.getByText(new RegExp(vi.conversationActivity.lastRun))).toHaveTextContent(vi.runSteps(3));
      expect(screen.getAllByTestId("run-card")[0]).toHaveTextContent("Ba bước");
    };

    render(strip(conversationFamilyRuns(listed, "c1")));
    agree();

    release();
    expect(await screen.findByText(/Hôm qua/)).toBeInTheDocument();
    agree();
  });

  // Work handed out in one batch starts in one second. The store lists such runs last saved
  // first, not in the order the page heard them start, and the strip took the store's order
  // once the history landed while the activity page kept the page's: its cards changed places
  // and its bar moved on to another run.
  it.each([
    ["still going", { status: "running" as const, finished_at: null }, () => screen.getAllByTestId("run-progress")[0]],
    ["ended in one second", { status: "error" as const, finished_at: "2026-09-19T08:00:06Z" }, () => screen.getByText(new RegExp(vi.conversationActivity.lastRun))],
  ])("keeps the order the page heard runs of the same second in once the history lands, %s", async (_, state, bar) => {
    const tool = (id: string): RunStep => ({ kind: "tool", name: "read_file", tool_call_id: id, arguments: {}, ok: true, output: "", duration_ms: 5 });
    const turn = fakeRun({ id: "p", title: "Cha", started_at: "2026-09-19T07:59:50Z", ...state });
    const kid = (id: string, title: string, steps: RunStep[]) =>
      fakeRun({ id, conversation_id: `w-${id}`, source: "delegate:c1", title, steps, ...state });
    const [a, b] = [kid("a", "Con A", [tool("1")]), kid("b", "Con B", [tool("2"), tool("3")])];
    // `a` was saved last, so the store lists it first.
    backend.runs = [a, b, turn, fakeRun({ id: "old", title: "Hôm qua", started_at: "2026-09-18T08:00:00Z" })];
    let release = () => undefined as void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      await gate;
      return backend.fetch(input, init);
    });
    let heard = activityReducer(emptyActivity, { type: "payload", payload: { type: "snapshot", runs: [] } });
    for (const run of [turn, a, b]) heard = activityReducer(heard, { type: "payload", payload: { type: "run", run } });
    const cards = () =>
      screen.getAllByTestId("run-card").map((card) => /Cha|Con A|Con B|Hôm qua/.exec(card.textContent ?? "")?.[0]);

    render(strip(conversationFamilyRuns(heard, "c1")));
    expect(cards()).toEqual(["Cha", "Con B", "Con A"]);
    expect(bar()).toHaveTextContent(vi.runSteps(2));

    release();
    expect(await screen.findByText(/Hôm qua/)).toBeInTheDocument();
    expect(cards()).toEqual(["Cha", "Con B", "Con A", "Hôm qua"]);
    expect(bar()).toHaveTextContent(vi.runSteps(2));
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

  describe("the focus of whoever pressed the retry", () => {
    // Pressing the retry takes it off the page while the history loads again, and the focus
    // fell to the top of the page, whatever the answer turned out to be.
    let online: boolean;
    let asked: number;
    let release = () => undefined as void;
    beforeEach(() => {
      online = false;
      asked = 0;
      const gate = new Promise<void>((resolve) => (release = resolve));
      vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
        asked += 1;
        if (!online) throw new Error("offline");
        await gate;
        return backend.fetch(input, init);
      });
    });
    const phone = (conversationId = "c1") => (
      <ConversationActivity runs={[]} conversationId={conversationId} spentUsd={0} agentName={name} onOpenConversation={() => undefined} />
    );
    const pressRetry = async () => {
      const retry = await screen.findByRole("button", { name: vi.retry });
      retry.focus();
      await userEvent.keyboard("{Enter}");
    };
    // Lets the answer in inside act, so the render it brings and that render's effects have
    // run when this returns. Checked with waitFor instead, a focus that should not move reads
    // as unmoved while the effect that would move it is still to come.
    const answerAtOnce = async () => {
      await act(async () => {
        release();
        await new Promise((resolve) => setTimeout(resolve, 0));
      });
      expect(screen.getByRole("status")).toHaveTextContent(vi.noRuns);
    };

    it("goes back to the retry when the history still cannot be read", async () => {
      render(strip([]));

      await pressRetry();

      await waitFor(() => expect(asked).toBe(2));
      await waitFor(() => expect(screen.getByRole("button", { name: vi.retry })).toHaveFocus());
    });

    it("goes to the first run the answer brought", async () => {
      backend.runs = [
        fakeRun({ id: "new", title: "Sáng nay", started_at: "2026-09-19T08:00:00Z" }),
        fakeRun({ id: "old", title: "Hôm qua", started_at: "2026-09-18T08:00:00Z" }),
      ];
      render(strip([]));

      online = true;
      await pressRetry();
      release();

      await waitFor(() => expect(screen.getAllByTestId("run-card")).toHaveLength(2));
      const first = screen.getAllByTestId("run-card")[0];
      expect(first).toHaveTextContent("Sáng nay");
      await waitFor(() => expect(within(first).getByRole("button")).toHaveFocus());
    });

    // On a phone the strip went away the moment its retry was pressed, as if the
    // conversation had never run, and came back once the answer was in.
    it("keeps a phone's strip up while it loads, then goes to the strip's toggle", async () => {
      backend.runs = [fakeRun({ id: "old", title: "Hôm qua" })];
      render(phone());

      online = true;
      await pressRetry();

      expect(screen.getByTestId("conversation-activity")).toHaveTextContent(vi.runFilters.loading);
      release();
      await waitFor(() =>
        expect(screen.getByRole("button", { name: vi.conversationActivity.expand })).toHaveFocus(),
      );
    });

    it("goes to the line saying so when the conversation turns out never to have run", async () => {
      render(strip([]));

      online = true;
      await pressRetry();
      release();

      await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(vi.noRuns));
      // The line is on the page as soon as the answer renders; the focus follows once the
      // effects of that render have run, which a busy machine does a moment later.
      await waitFor(() => expect(screen.getByRole("status")).toHaveFocus());
    });

    // Below the column the strip hid itself once the answer said the conversation never
    // ran, taking the line with the focus in it down with it.
    it("keeps a phone's strip up with that line when the conversation never ran", async () => {
      render(phone());

      online = true;
      await pressRetry();
      release();

      await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(vi.noRuns));
      await waitFor(() => expect(screen.getByRole("status")).toHaveFocus());
      expect(screen.getByTestId("conversation-activity")).toBeInTheDocument();
    });

    it("stays wherever the person has put it since", async () => {
      render(
        <>
          {strip([])}
          <button type="button">elsewhere</button>
        </>,
      );

      online = true;
      await pressRetry();
      screen.getByRole("button", { name: "elsewhere" }).focus();
      await answerAtOnce();

      expect(screen.getByRole("button", { name: "elsewhere" })).toHaveFocus();
    });

    it("is not pulled into another conversation opened while the answer was on its way", async () => {
      const view = render(strip([]));

      online = true;
      await pressRetry();
      view.rerender(
        <ConversationActivity runs={[]} conversationId="c2" spentUsd={0} agentName={name} onOpenConversation={() => undefined} docked />,
      );
      await answerAtOnce();

      expect(document.body).toHaveFocus();
    });
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

  // Approved in the chat, the turn went on and stopped at its next tool: no run settled, so
  // the request just decided stayed out of the strip's history until the turn was over.
  it("asks for the approvals again when a decided turn waits on its next tool", async () => {
    const approvalsAsked = () => backend.requests.filter((r) => r.path.startsWith("/approvals")).length;
    const open: RunInfo["steps"][number] = { kind: "tool", name: "write_file", tool_call_id: "tc", arguments: {}, ok: null, output: null, duration_ms: null };
    const paused = fakeRun({ id: "now", status: "awaiting_approval", finished_at: null, steps: [open] });
    const { rerender } = render(strip([paused]));
    await waitFor(() => expect(approvalsAsked()).toBe(1));

    // The resume and the next stop reach the page in one update.
    rerender(
      strip([
        {
          ...paused,
          steps: [
            { ...open, ok: true } as typeof open,
            { kind: "model", chars: 10, tool_calls: ["shell_run"], duration_ms: 90 },
            { kind: "tool", name: "shell_run", tool_call_id: "tc2", arguments: {}, ok: null, output: null, duration_ms: null },
          ],
        },
      ]),
    );

    await waitFor(() => expect(approvalsAsked()).toBe(2));
  });
});
