import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { liveRuns } from "../state/activity-reducer";
import { FakeBackend, FakeEventSource, fakeRun } from "../test/fake-backend";
import { useActivity } from "./use-activity";

const LIST = "/api/activity/runs?limit=50";
let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  FakeEventSource.instances = [];
  vitest.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => vitest.unstubAllGlobals());

function stream(): FakeEventSource {
  const source = FakeEventSource.instances.at(-1);
  if (!source) throw new Error("the hook has not subscribed to the activity stream");
  return source;
}

/** Each read of the crew's runs is answered with what the backend held when it was asked;
 *  the reads named in `hold` reach the page only once released, so an answer read before a
 *  run ended can land after one read later. */
function network(hold: number[] = []) {
  const releases = new Map<number, () => void>();
  let reads = 0;
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input) !== LIST) return backend.fetch(input, init);
    const n = ++reads;
    const gate = hold.includes(n) ? new Promise<void>((resolve) => releases.set(n, resolve)) : null;
    const response = await backend.fetch(input, init);
    if (gate) await gate;
    return response;
  });
  return { release: (n: number) => releases.get(n)?.(), reads: () => reads };
}

const job = { id: "job1", agent_id: "coach", conversation_id: null, source: "job:coach/brief" };
const running = () => fakeRun({ ...job, status: "running", finished_at: null });
const done = () => fakeRun({ ...job, status: "done" });
// A finished run riding along in an answer, so the test can tell when it has been taken in.
const marker = (id = "earlier") => fakeRun({ ...job, id, started_at: "2026-09-19T07:00:00Z" });

describe("useActivity and list answers that land late", () => {
  it("keeps a finished run finished when a list read before it ended lands last", async () => {
    backend.runs = [running(), marker()];
    const net = network([1]);
    const { result } = renderHook(() => useActivity(true));
    await waitFor(() => expect(net.reads()).toBe(1));
    act(() => {
      stream().open();
      stream().emit({ type: "snapshot", runs: [running()] });
    });

    backend.runs = [done(), marker("later")];
    act(() => stream().emit({ type: "run", run: done() }));
    await waitFor(() => expect(result.current.state.runs.later).toBeDefined());
    expect(net.reads()).toBe(2);

    await act(async () => net.release(1));
    await waitFor(() => expect(result.current.state.runs.earlier).toBeDefined());
    expect(result.current.state.runs.job1.status).toBe("done");
    expect(liveRuns(result.current.state)).toEqual([]);
  });

  it("does not bring back as running a run that ended before the first snapshot", async () => {
    // Read while the job ran; the job ends before the stream opens, so the snapshot leaves
    // it out and no event about it will ever reach this page.
    backend.runs = [running(), marker()];
    const net = network([1]);
    const { result } = renderHook(() => useActivity(true));
    await waitFor(() => expect(net.reads()).toBe(1));
    backend.runs = [done(), marker()];
    act(() => {
      stream().open();
      stream().emit({ type: "snapshot", runs: [] });
    });

    await act(async () => net.release(1));
    await waitFor(() => expect(result.current.state.runs.earlier).toBeDefined());
    expect(liveRuns(result.current.state)).toEqual([]);
  });

  it("reads the list once for a reconnect, after the fresh stream says what is live", async () => {
    const net = network();
    const { result } = renderHook(() => useActivity(true));
    act(() => {
      stream().open();
      stream().emit({ type: "snapshot", runs: [] });
    });
    await waitFor(() => expect(net.reads()).toBe(1));

    act(() => stream().onerror?.());
    act(() => result.current.reconnect());
    await act(async () => {});
    expect(net.reads()).toBe(1);

    backend.runs = [done()];
    act(() => {
      stream().open();
      stream().emit({ type: "snapshot", runs: [] });
    });
    await waitFor(() => expect(result.current.state.runs.job1?.status).toBe("done"));
    expect(net.reads()).toBe(2);
  });
});
