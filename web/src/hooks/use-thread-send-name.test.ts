import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { api } from "../api/client";
import type { AgentEvent, ConversationDetail, RunInfo } from "../api/types";
import type { SendResult } from "../lib/send-result";
import type { ActivityState } from "../state/activity-reducer";
import { FakeBackend, fakeApproval, fakeRun } from "../test/fake-backend";
import { type ThreadController, useThread } from "./use-thread";

/**
 * The name a send nothing was heard of goes out under when the same words are sent again,
 * in a thread that went on reading its conversation meanwhile: the same one while the turn
 * the message may have got is open, a new one once that turn is seen to end.
 */

const WORDS = "tiếp tục";
const DONE: AgentEvent = { type: "done", spent_usd: 0, unknown_cost_calls: 0 };
const ASKING: AgentEvent = { type: "approval_required", approval_id: "ap", tool_call_id: "tc1", name: "write_file", arguments: {}, reason: "", expires_at: "" };

const stored = (overrides: Partial<ConversationDetail> = {}) => new FakeBackend().create(overrides);
const going = (id: string) => fakeRun({ id, status: "running", finished_at: null });
const asking = (id: string) => fakeRun({ id, status: "awaiting_approval", finished_at: null });
const over = (id: string) => fakeRun({ id, status: "done" });
/** The activity as a tab in step with the server has it. */
const activity = (...runs: RunInfo[]): ActivityState => ({ runs: Object.fromEntries(runs.map((r) => [r.id, r])), connected: true, synced: true });

interface Props {
  id?: string;
  activity?: ActivityState;
}
type Thread = { current: ThreadController };

beforeEach(() => {
  vitest.spyOn(api, "getConversation").mockImplementation(async (id) => stored({ id }));
});

afterEach(() => vitest.restoreAllMocks());

/** A thread open on c1 whose send of the words failed with nothing heard. Every later send
 *  is answered. */
async function unheard(props: Props = {}) {
  let lost = false;
  const sent = vitest.spyOn(api, "sendMessage").mockImplementation(async (_id, _text, onEvent) => {
    if (lost) return onEvent(DONE);
    lost = true;
    throw new TypeError("Failed to fetch");
  });
  const hook = renderHook(({ id = "c1", activity }: Props) => useThread(id, activity), { initialProps: props });
  await waitFor(() => expect(hook.result.current.detail?.id).toBe("c1"));
  let outcome: SendResult | undefined;
  await act(async () => {
    outcome = await hook.result.current.send(WORDS);
  });
  expect(outcome?.status).toBe("failed");
  /** The names the sends went out under, in order. */
  const names = () => sent.mock.calls.map((call) => call[5]);
  return { ...hook, names };
}

async function sendAgain(thread: Thread) {
  await act(async () => {
    await thread.current.send(WORDS);
  });
}

/** The thread reading along with a turn found going, whose stream the test holds. */
async function readAlong(thread: Thread) {
  const turn: { emit: (e: AgentEvent) => void; end: () => void } = { emit: () => {}, end: () => {} };
  vitest.spyOn(api, "watchTurn").mockImplementation(
    (_id, emit) => new Promise<boolean>((resolve) => Object.assign(turn, { emit, end: () => resolve(true) })),
  );
  act(() => void thread.current.watch());
  await act(async () => turn.emit({ type: "watching", running: true, detail: stored() }));
  expect(thread.current.watching).toBe(true);
  return turn;
}

describe("the name of a send nothing was heard of, as the thread reads a turn in its conversation", () => {
  it("is kept while a turn read along with is still going", async () => {
    const { result, names } = await unheard();
    await readAlong(result);
    await sendAgain(result);
    expect(names()[1]).toBe(names()[0]);
  });

  it("is a new one once a turn read along with has said it is over", async () => {
    const { result, names } = await unheard();
    const turn = await readAlong(result);
    await act(async () => {
      turn.emit(DONE);
      turn.end();
    });
    await sendAgain(result);
    expect(names()[1]).toMatch(/^[0-9a-f]{32}$/);
    expect(names()[1]).not.toBe(names()[0]);
  });

  it("is kept when the turn read along with stops to wait on the person", async () => {
    const { result, names } = await unheard();
    const turn = await readAlong(result);
    await act(async () => {
      turn.emit(ASKING);
      turn.end();
    });
    await sendAgain(result);
    expect(names()[1]).toBe(names()[0]);
  });

  it("is kept when the stream read along with closes with nothing said of the turn's end", async () => {
    const { result, names } = await unheard();
    const turn = await readAlong(result);
    await act(async () => turn.end());
    await sendAgain(result);
    expect(names()[1]).toBe(names()[0]);
  });

  it("is a new one once the turn has ended on this tab's own stream, after the answer it waited on", async () => {
    const { result, names } = await unheard();
    // The turn the message got stopped to ask, and the thread read again shows the request.
    const request = fakeApproval({ id: "ap", status: "pending", resolved_at: null });
    vitest.spyOn(api, "getConversation").mockResolvedValue(stored({ status: "awaiting_approval", pending_approval: request }));
    await act(() => result.current.reload());
    expect(result.current.state.pending?.approvalId).toBe("ap");
    vitest.spyOn(api, "resolveApproval").mockImplementation(async (_id, _approval, _approve, onEvent) => onEvent(DONE));
    await act(() => result.current.decide(true));
    await sendAgain(result);
    expect(names()[1]).not.toBe(names()[0]);
  });

  it("is kept when the turn that says it is over was going on this tab's own stream as the name went out", async () => {
    // The message was sent behind that turn: found busy, it waits for a turn of its own.
    const own: { emit: (e: AgentEvent) => void; end: () => void } = { emit: () => {}, end: () => {} };
    let nth = 0;
    const sent = vitest.spyOn(api, "sendMessage").mockImplementation((_id, _text, onEvent) => {
      nth += 1;
      if (nth === 1) return new Promise<void>((resolve) => Object.assign(own, { emit: onEvent, end: resolve }));
      if (nth === 2) return Promise.reject(new TypeError("Failed to fetch"));
      onEvent(DONE);
      return Promise.resolve();
    });
    const { result } = renderHook(() => useThread("c1"));
    await waitFor(() => expect(result.current.detail?.id).toBe("c1"));
    act(() => void result.current.send("việc một"));
    await act(async () => own.emit({ type: "text_delta", text: "đang làm" }));
    expect(result.current.state.busy).toBe(true);
    let outcome: SendResult | undefined;
    await act(async () => {
      outcome = await result.current.send(WORDS);
    });
    expect(outcome?.status).toBe("failed");

    await act(async () => {
      own.emit(DONE);
      own.end();
    });
    expect(result.current.state.busy).toBe(false);
    await sendAgain(result);
    const names = sent.mock.calls.map((call) => call[5]);
    expect(names[2]).toBe(names[1]);
  });
});

describe("the name of a send nothing was heard of, as the runs of its conversation come and go", () => {
  it("is kept while a run that began there after it is going", async () => {
    const { result, rerender, names } = await unheard({ activity: activity() });
    rerender({ activity: activity(going("r1")) });
    await sendAgain(result);
    expect(names()[1]).toBe(names()[0]);
  });

  it("is a new one once a run that began there after it is over", async () => {
    const { result, rerender, names } = await unheard({ activity: activity() });
    rerender({ activity: activity(going("r1")) });
    rerender({ activity: activity(over("r1")) });
    await sendAgain(result);
    expect(names()[1]).toMatch(/^[0-9a-f]{32}$/);
    expect(names()[1]).not.toBe(names()[0]);
  });

  it("is kept while that run waits on the person", async () => {
    const { result, rerender, names } = await unheard({ activity: activity() });
    rerender({ activity: activity(going("r1")) });
    rerender({ activity: activity(asking("r1")) });
    await sendAgain(result);
    expect(names()[1]).toBe(names()[0]);
  });

  it("is kept when the run that ends was there as the name went out, waiting on the person and taken up since", async () => {
    const { result, rerender, names } = await unheard({ activity: activity(asking("r0")) });
    rerender({ activity: activity(going("r0")) });
    rerender({ activity: activity(over("r0")) });
    await sendAgain(result);
    expect(names()[1]).toBe(names()[0]);
  });

  it("is a new one for a run that came and went while another conversation was open", async () => {
    const { result, rerender, names } = await unheard({ activity: activity() });
    rerender({ id: "c2", activity: activity() });
    await waitFor(() => expect(result.current.detail?.id).toBe("c2"));
    rerender({ id: "c2", activity: activity(going("r1")) });
    rerender({ id: "c2", activity: activity(over("r1")) });
    rerender({ id: "c1", activity: activity(over("r1")) });
    await waitFor(() => expect(result.current.detail?.id).toBe("c1"));
    await sendAgain(result);
    expect(names()[1]).not.toBe(names()[0]);
  });
});
