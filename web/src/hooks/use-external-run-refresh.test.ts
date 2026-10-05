// A drain turn shows up as an external run's first sighting, but by the time it starts the
// queue's own confirmation (the person's message) is long since written, so a reload has to
// fire on that first sighting whatever status it carries — otherwise the chip would sit on
// screen instead of turning into the message it stands for.
import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import type { QueuedMessage, RunInfo } from "../api/types";
import { emptyActivity } from "../state/activity-reducer";
import { emptyThread, type ThreadState } from "../state/thread-reducer";
import type { ActivityController } from "./use-activity";
import { useExternalRunRefresh } from "./use-external-run-refresh";
import type { ThreadController } from "./use-thread";

function run(overrides: Partial<RunInfo> = {}): RunInfo {
  return {
    id: "r1",
    agent_id: "default",
    conversation_id: "c1",
    source: "delegate:c1",
    title: "t",
    status: "running",
    started_at: "2026-09-19T08:00:00Z",
    finished_at: null,
    spent_usd: 0,
    unknown_cost_calls: 0,
    summary: "",
    steps: [],
    ...overrides,
  };
}

const chip: QueuedMessage = { id: 1, kind: "follow_up", text: "việc đầu tiên" };

function fakeThread(
  overrides: Partial<ThreadState> = {},
  own: Partial<Pick<ThreadController, "watching" | "unowned" | "reloadWhenIdle">> = {},
): { reloadWhenIdle: ReturnType<typeof vitest.fn>; controller: ThreadController } {
  const reloadWhenIdle = vitest.fn();
  const controller: ThreadController = {
    state: { ...emptyThread, ...overrides },
    detail: null,
    send: vitest.fn(),
    decide: vitest.fn(),
    answer: vitest.fn(),
    stop: vitest.fn(),
    watch: vitest.fn(async () => true),
    watching: false,
    reload: vitest.fn(async () => undefined),
    reloadWhenIdle,
    settle: vitest.fn(),
    mutePreviews: vitest.fn(),
    unowned: 0,
    ...own,
  };
  return { reloadWhenIdle, controller };
}

function fakeActivity(runs: RunInfo[], overrides: { synced?: boolean } = {}): ActivityController {
  const byId = Object.fromEntries(runs.map((r) => [r.id, r]));
  const synced = overrides.synced ?? true;
  return {
    // The hook reads `synced` off the controller itself, not `state.synced` — the two can
    // disagree for a moment while a fresh snapshot is still landing.
    state: { ...emptyActivity, runs: byId, connected: true, synced },
    refresh: vitest.fn(async () => undefined),
    connecting: false,
    synced,
    reconnect: vitest.fn(),
  };
}

describe("a run first seen running while a drain's chip is still on screen", () => {
  it("reloads the thread right away instead of waiting for the run to change status", () => {
    const { reloadWhenIdle, controller } = fakeThread({ waiting: [chip] });
    const activity = fakeActivity([run()]);
    renderHook(() => useExternalRunRefresh("c1", controller, activity));
    expect(reloadWhenIdle).toHaveBeenCalled();
  });

  it("does not reload when there is no chip waiting: a plain external run keeps its old, quieter behaviour", () => {
    const { reloadWhenIdle, controller } = fakeThread({ waiting: [] });
    const activity = fakeActivity([run()]);
    renderHook(() => useExternalRunRefresh("c1", controller, activity));
    expect(reloadWhenIdle).not.toHaveBeenCalled();
  });

  it("reloads even when the run is first seen already finished: an echo reply or a turn halted on budget never renders as running at all", () => {
    const { reloadWhenIdle, controller } = fakeThread({ waiting: [chip] });
    const activity = fakeActivity([run({ status: "done", finished_at: "2026-09-19T08:00:01Z" })]);
    renderHook(() => useExternalRunRefresh("c1", controller, activity));
    expect(reloadWhenIdle).toHaveBeenCalled();
  });

  it("reloads when the run is first seen halted: the same instant turn can also stop on its own budget cap", () => {
    const { reloadWhenIdle, controller } = fakeThread({ waiting: [chip] });
    const activity = fakeActivity([run({ status: "halted", finished_at: "2026-09-19T08:00:01Z" })]);
    renderHook(() => useExternalRunRefresh("c1", controller, activity));
    expect(reloadWhenIdle).toHaveBeenCalled();
  });

  it("does not reload while the stream is behind: the reload on catching up already covers it", () => {
    const { reloadWhenIdle, controller } = fakeThread({ waiting: [chip] });
    // `behind` only means something once the stream has been synced at least once and
    // then drops: a stream that has never synced yet is merely "not synced yet", a
    // different state this hook does not treat as behind (see the `everSynced` ref).
    const { rerender } = renderHook(
      ({ activity }) => useExternalRunRefresh("c1", controller, activity),
      { initialProps: { activity: fakeActivity([], { synced: true }) } },
    );
    rerender({ activity: fakeActivity([], { synced: false }) });
    rerender({ activity: fakeActivity([run()], { synced: false }) });
    expect(reloadWhenIdle).not.toHaveBeenCalled();
  });
});

describe("a turn this tab reads along with", () => {
  const telegram = run({ source: "telegram" });
  const over = run({ source: "telegram", status: "done", finished_at: "2026-09-19T08:00:09Z" });

  /** The hook over a thread and runs a test moves on, keeping one `reloadWhenIdle` to count on. */
  function follow(first: { busy: boolean; watching: boolean; unowned: number; runs: RunInfo[] }) {
    const reloadWhenIdle = vitest.fn();
    const props = (p: typeof first) => ({
      thread: fakeThread({ busy: p.busy }, { watching: p.watching, unowned: p.unowned, reloadWhenIdle }).controller,
      activity: fakeActivity(p.runs),
    });
    const hook = renderHook(({ thread, activity }) => useExternalRunRefresh("c1", thread, activity), {
      initialProps: props(first),
    });
    return { reloadWhenIdle, result: hook.result, move: (next: typeof first) => hook.rerender(props(next)) };
  }

  it("goes on naming the run while the thread follows it: the thread still says whose turn it is", () => {
    const { result, move } = follow({ busy: false, watching: false, unowned: 0, runs: [telegram] });
    expect(result.current?.id).toBe("r1");
    move({ busy: true, watching: true, unowned: 1, runs: [telegram] });
    expect(result.current).toMatchObject({ id: "r1", source: "telegram" });
  });

  it("names no run while the tab reads a turn of its own", () => {
    const { result, move } = follow({ busy: false, watching: false, unowned: 0, runs: [] });
    move({ busy: true, watching: false, unowned: 0, runs: [run({ source: "chat" })] });
    expect(result.current).toBeNull();
  });

  it("does not put a watched run down to this tab: it is loaded once over, like any run elsewhere", () => {
    // The run starts while the tab is already watching — a queued message's turn begins the
    // moment the turn before it ends, before the watch on that one has let go.
    const { reloadWhenIdle, result, move } = follow({ busy: false, watching: false, unowned: 0, runs: [] });
    move({ busy: true, watching: true, unowned: 1, runs: [] });
    move({ busy: true, watching: true, unowned: 1, runs: [telegram] });
    expect(result.current?.id).toBe("r1");
    expect(reloadWhenIdle).not.toHaveBeenCalled();
    move({ busy: false, watching: false, unowned: 1, runs: [over] });
    expect(reloadWhenIdle).toHaveBeenCalledTimes(1);
  });

  it("claims the run a turn of this tab's own starts, as before, and loads nothing when it ends", () => {
    const { reloadWhenIdle, result, move } = follow({ busy: false, watching: false, unowned: 0, runs: [] });
    move({ busy: true, watching: false, unowned: 0, runs: [] });
    move({ busy: true, watching: false, unowned: 0, runs: [run({ source: "chat" })] });
    move({ busy: false, watching: false, unowned: 0, runs: [run({ source: "chat" })] });
    expect(result.current).toBeNull(); // its own stream ended a moment before the run did
    move({ busy: false, watching: false, unowned: 0, runs: [run({ source: "chat", status: "done" })] });
    expect(reloadWhenIdle).not.toHaveBeenCalled();
  });

  it("gives up a run whose stream this tab lost: the run goes on, to be watched and loaded once over", () => {
    const chat = run({ source: "chat" });
    const { reloadWhenIdle, result, move } = follow({ busy: false, watching: false, unowned: 0, runs: [] });
    move({ busy: true, watching: false, unowned: 0, runs: [] });
    move({ busy: true, watching: false, unowned: 0, runs: [chat] });
    // The stream failed: the thread is idle, and the run is no longer this tab's.
    move({ busy: false, watching: false, unowned: 1, runs: [chat] });
    expect(result.current?.id).toBe("r1");
    move({ busy: false, watching: false, unowned: 1, runs: [run({ source: "chat", status: "done" })] });
    expect(reloadWhenIdle).toHaveBeenCalledTimes(1);
  });
});
