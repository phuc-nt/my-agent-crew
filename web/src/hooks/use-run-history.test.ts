import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { api } from "../api/client";
import type { RunInfo } from "../api/types";
import { fakeRun } from "../test/fake-backend";
import { useRunHistory, type RunHistory, type RunHistoryQuery } from "./use-run-history";

/** One request for stored runs, held until the test answers it. */
interface Asked {
  params: Parameters<typeof api.listRuns>[0];
  answer: (runs: RunInfo[]) => Promise<void>;
  fail: () => Promise<void>;
}

let asked: Asked[];

/** Settles `outcome` and everything it sets off before the test looks again. */
const land = (outcome: () => void) =>
  act(async () => {
    outcome();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

beforeEach(() => {
  asked = [];
  vitest.spyOn(api, "listRuns").mockImplementation(
    (params) =>
      new Promise<RunInfo[]>((resolve, reject) => {
        asked.push({
          params,
          answer: (runs) => land(() => resolve(runs)),
          fail: () => land(() => reject(new Error("502"))),
        });
      }),
  );
});

afterEach(() => vitest.restoreAllMocks());

/** Mounts the hook and keeps what it returned on every render, so one wrong frame shows. */
function mount(initialProps: RunHistoryQuery) {
  const frames: RunHistory[] = [];
  const hook = renderHook(
    (query: RunHistoryQuery) => {
      const history = useRunHistory(query);
      frames.push(history);
      return history;
    },
    { initialProps },
  );
  return { ...hook, frames };
}

const ids = (history: RunHistory) => history.runs.map((run) => run.id);

describe("a history whose query changes while a request is out", () => {
  it("keeps a slower answer for the agent it left off the one now shown", async () => {
    const { result, rerender } = mount({ agentId: "coach", limit: 50 });
    rerender({ agentId: "ledger", limit: 50 });
    expect(asked.map((a) => a.params?.agent_id)).toEqual(["coach", "ledger"]);

    await asked[1].answer([fakeRun({ id: "ledger-run", agent_id: "ledger" })]);
    await asked[0].answer([fakeRun({ id: "coach-run", agent_id: "coach" })]);
    expect(ids(result.current)).toEqual(["ledger-run"]);
    expect(result.current.loading).toBe(false);
  });

  it("keeps a slower failure for the agent it left off the one now shown", async () => {
    const { result, rerender } = mount({ agentId: "coach", limit: 50 });
    rerender({ agentId: "ledger", limit: 50 });

    await asked[1].answer([fakeRun({ id: "ledger-run", agent_id: "ledger" })]);
    await asked[0].fail();
    expect(ids(result.current)).toEqual(["ledger-run"]);
    expect(result.current).toMatchObject({ loading: false, failed: false });
  });

  it("shows nothing of one conversation's runs, not for a frame, while the next one's load", async () => {
    const { result, rerender, frames } = mount({ conversationId: "c1", limit: 20 });
    await asked[0].answer([fakeRun({ id: "r1", conversation_id: "c1" })]);
    expect(ids(result.current)).toEqual(["r1"]);
    expect(result.current.pageLimit).toBe(20);

    const from = frames.length;
    rerender({ conversationId: "c2", limit: 20 });
    expect(asked[1].params?.conversation_id).toBe("c2");
    expect(frames.length).toBeGreaterThan(from);
    for (const frame of frames.slice(from)) {
      expect(frame).toMatchObject({ runs: [], loading: true, failed: false, pageLimit: 0 });
    }

    await asked[1].answer([fakeRun({ id: "r2", conversation_id: "c2" })]);
    expect(ids(result.current)).toEqual(["r2"]);
    expect(result.current).toMatchObject({ loading: false, pageLimit: 20 });
  });

  it("does not carry one conversation's failure over to the next", async () => {
    const { result, rerender, frames } = mount({ conversationId: "c1", limit: 20 });
    await asked[0].fail();
    expect(result.current.failed).toBe(true);

    const from = frames.length;
    rerender({ conversationId: "c2", limit: 20 });
    for (const frame of frames.slice(from)) expect(frame.failed).toBe(false);
  });

  // Left under the previous query's answer, the failure would read as a load still
  // waiting, with no retry to offer.
  it("files a failure under the query that failed, which a reload then asks again", async () => {
    const { result, rerender } = mount({ conversationId: "c1", limit: 20 });
    await asked[0].answer([fakeRun({ id: "r1", conversation_id: "c1" })]);
    rerender({ conversationId: "c2", limit: 20 });
    await asked[1].fail();
    expect(result.current).toMatchObject({ runs: [], loading: false, failed: true });

    act(() => result.current.reload());
    expect(asked[2].params?.conversation_id).toBe("c2");
    await asked[2].answer([fakeRun({ id: "r2", conversation_id: "c2" })]);
    expect(ids(result.current)).toEqual(["r2"]);
    expect(result.current.failed).toBe(false);
  });
});

describe("a reload after a failure", () => {
  // One render on, the old failure read as the retried page having settled already, and
  // a view that moves the focus once that page settles moved it too early.
  it("lets the failure go in the render the reload asks in, until the answer lands", async () => {
    const { result, frames } = mount({ agentId: "coach", limit: 200 });
    await asked[0].fail();
    expect(result.current).toMatchObject({ loading: false, failed: true });

    const from = frames.length;
    act(() => result.current.reload());
    expect(asked).toHaveLength(2);
    expect(frames.length).toBeGreaterThan(from);
    for (const frame of frames.slice(from)) expect(frame).toMatchObject({ loading: true, failed: false });

    await asked[1].answer([fakeRun({ id: "r1", agent_id: "coach" })]);
    expect(ids(result.current)).toEqual(["r1"]);
    expect(result.current).toMatchObject({ loading: false, failed: false, pageLimit: 200 });
  });
});
