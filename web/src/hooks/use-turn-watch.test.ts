import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import type { RunInfo } from "../api/types";
import { emptyActivity } from "../state/activity-reducer";
import { emptyThread } from "../state/thread-reducer";
import type { ActivityController } from "./use-activity";
import type { ThreadController } from "./use-thread";
import { useTurnWatch } from "./use-turn-watch";

const RUN = { id: "r1", conversation_id: "c1", status: "running" } as RunInfo;
const OTHER = { ...RUN, id: "r2" } as RunInfo;

interface Scene {
  conversationId?: string;
  busy?: boolean;
  synced?: boolean;
  run?: RunInfo | null;
}

/** The hook over a thread whose `watch` answers what the test says each time it is asked. */
function scene(first: Scene, found: boolean[] = []) {
  const answers = [...found];
  const watch = vitest.fn(async () => answers.shift() ?? true);
  const props = ({ conversationId = "c1", busy = false, synced = true, run = RUN }: Scene) => ({
    conversationId,
    thread: { state: { ...emptyThread, busy }, watch } as unknown as ThreadController,
    activity: { state: emptyActivity, synced } as unknown as ActivityController,
    run,
  });
  const hook = renderHook((p) => useTurnWatch(p.conversationId, p.thread, p.activity, p.run), {
    initialProps: props(first),
  });
  /** Renders again and lets the answer to the watch it may have started land. */
  const move = async (next: Scene) => {
    hook.rerender(props(next));
    await act(async () => {});
  };
  return { watch, move };
}

describe("reading along with a turn this tab did not start", () => {
  it("joins a run found going here, once", async () => {
    const { watch, move } = scene({});
    expect(watch).toHaveBeenCalledTimes(1);
    await move({});
    await move({ synced: true });
    expect(watch).toHaveBeenCalledTimes(1);
  });

  it("asks for nothing with no run going, and nothing while the tab reads a turn already", async () => {
    const { watch, move } = scene({ run: null });
    await move({ busy: true, run: null });
    await move({ busy: true });
    expect(watch).not.toHaveBeenCalled();
    // The stream ended and the run is still going: now there is something to join.
    await move({ busy: false });
    expect(watch).toHaveBeenCalledTimes(1);
  });

  it("asks again when a watch that joined has ended and the run is still going", async () => {
    // The watch was cut — a stop that never reached the server, a connection dropped.
    const { watch, move } = scene({});
    await move({ busy: true });
    await move({ busy: false });
    expect(watch).toHaveBeenCalledTimes(2);
  });

  it("does not ask twice about a run the server had nothing to read of", async () => {
    // The run ended a moment before the activity stream said so.
    const { watch, move } = scene({}, [false]);
    await move({});
    await move({ busy: true });
    await move({ busy: false });
    expect(watch).toHaveBeenCalledTimes(1);
  });

  it("asks again once that run is seen going after it was not: someone answered its pause", async () => {
    const { watch, move } = scene({}, [false]);
    await move({ run: null });
    await move({});
    expect(watch).toHaveBeenCalledTimes(2);
  });

  it("asks again when the activity stream comes back, as after a restart", async () => {
    const { watch, move } = scene({}, [false, false]);
    await move({ synced: false });
    expect(watch).toHaveBeenCalledTimes(2); // asked while it is down too: the answer is no
    await move({ synced: true });
    expect(watch).toHaveBeenCalledTimes(3);
  });

  it("asks about another run, and about the same run in another conversation", async () => {
    const { watch, move } = scene({}, [false, false, false]);
    await move({ run: OTHER });
    expect(watch).toHaveBeenCalledTimes(2);
    await move({ run: OTHER, conversationId: "c2" });
    expect(watch).toHaveBeenCalledTimes(3);
  });

  it("does not hold an answer that came for a run it has moved on from against the next one", async () => {
    let answer: (found: boolean) => void = () => {};
    const watch = vitest
      .fn<() => Promise<boolean>>()
      .mockImplementationOnce(() => new Promise((resolve) => (answer = resolve)))
      .mockResolvedValue(true);
    const props = (run: RunInfo | null, busy = false) => ({
      thread: { state: { ...emptyThread, busy }, watch } as unknown as ThreadController,
      activity: { state: emptyActivity, synced: true } as unknown as ActivityController,
      run,
    });
    const hook = renderHook((p) => useTurnWatch("c1", p.thread, p.activity, p.run), { initialProps: props(RUN) });
    hook.rerender(props(null)); // the run paused before the server answered
    await act(async () => answer(false));
    hook.rerender(props(RUN)); // and went on: that old "nothing" was not about this
    expect(watch).toHaveBeenCalledTimes(2);
  });
});
