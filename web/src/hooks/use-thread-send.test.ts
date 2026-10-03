import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import { api, ApiError } from "../api/client";
import type { AgentEvent } from "../api/types";
import { vi } from "../i18n/vi";
import type { ThreadAction } from "../state/thread-reducer";
import { useThreadSend } from "./use-thread-send";

/** A send made while this tab's own turn runs, so it joins the queue behind it: what it tells
 *  the thread, and the requests it still holds, are all there is to look at. */
function sendBehindATurn() {
  const dispatch = vitest.fn<(action: ThreadAction) => void>();
  const queueing = { current: new Set<AbortController>() };
  const { result } = renderHook(() =>
    useThreadSend({ conversationId: "c1", busy: true, dispatch, runTurn: vitest.fn(), queueing }),
  );
  return { send: result.current, dispatch, queueing };
}

/** A send made while this tab believes the conversation idle, so it runs a turn of its own:
 *  what the turn's stream is handed, and what the thread is told, are all there is to look at. */
function sendOnItsOwnStream() {
  const dispatch = vitest.fn<(action: ThreadAction) => void>();
  const streamed: AgentEvent[] = [];
  const runTurn = async (run: (emit: (e: AgentEvent) => void, signal: AbortSignal) => Promise<void>) => {
    await run((event) => streamed.push(event), new AbortController().signal);
  };
  const { result } = renderHook(() =>
    useThreadSend({ conversationId: "c1", busy: false, dispatch, runTurn, queueing: { current: new Set() } }),
  );
  return { send: result.current, dispatch, streamed };
}

/** A request that stays open until the test finishes it, or until its signal cuts it. */
function openRequest() {
  const request: { finish: () => void; signal?: AbortSignal } = { finish: () => {} };
  vitest.spyOn(api, "sendMessage").mockImplementation(
    (_id, _text, _emit, signal) =>
      new Promise<void>((resolve, reject) => {
        request.signal = signal;
        request.finish = resolve;
        signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      }),
  );
  return request;
}

afterEach(() => {
  vitest.restoreAllMocks();
});

describe("a message queued behind this tab's own turn", () => {
  it("is held among the queueing requests only while its request is in flight", async () => {
    const request = openRequest();
    const { send, queueing } = sendBehindATurn();

    const answer = send("chen ngang");
    expect(queueing.current.size).toBe(1);
    request.finish();

    await expect(answer).resolves.toEqual({ status: "sent" });
    expect(queueing.current.size).toBe(0);
  });

  it("answers sent when its request closes having said nothing: the server took the message", async () => {
    vitest.spyOn(api, "sendMessage").mockResolvedValue(undefined);
    const { send } = sendBehindATurn();

    await expect(send("lặng lẽ")).resolves.toEqual({ status: "sent" });
  });

  it("says nothing of a request it was cut off from: the person left, nothing was refused", async () => {
    const request = openRequest();
    const { send, dispatch, queueing } = sendBehindATurn();

    const answer = send("còn treo");
    for (const controller of queueing.current) controller.abort();

    await expect(answer).resolves.toEqual({ status: "sent" });
    expect(request.signal?.aborted).toBe(true);
    expect(dispatch).not.toHaveBeenCalled();
  });
});

describe("a message sent on this tab's own stream that the server queues instead", () => {
  it("is turned into its chip by the send itself: the turn's stream is handed no queued event", async () => {
    vitest.spyOn(api, "sendMessage").mockImplementation(async (_id, _text, onEvent) => {
      onEvent({ type: "queued", item_id: 7, kind: "follow_up", position: 1 });
    });
    const { send, dispatch, streamed } = sendOnItsOwnStream();

    await expect(send("tưởng rảnh")).resolves.toEqual({ status: "queued" });
    expect(dispatch).toHaveBeenCalledWith({ type: "queued", item: { id: 7, kind: "follow_up", text: "tưởng rảnh" } });
    // The send knows which text the chip stands for; the reducer's own `queued` case knows
    // nothing, and a second telling of the same event from the stream would make it two.
    expect(streamed).toEqual([]);
  });

  it("hands every other event on to the turn's stream", async () => {
    const done: AgentEvent = { type: "done", spent_usd: 0, unknown_cost_calls: 0 };
    vitest.spyOn(api, "sendMessage").mockImplementation(async (_id, _text, onEvent) => onEvent(done));
    const { send, streamed } = sendOnItsOwnStream();

    await expect(send("bình thường")).resolves.toEqual({ status: "sent" });
    expect(streamed).toEqual([done]);
  });
});

describe("a message queued behind this tab's own turn that the server refuses", () => {
  it("is worded as any refused message is: a validation dump never reaches the notice", async () => {
    // What the server answers for a message over its length limit is a list, not a sentence.
    const dump = JSON.stringify([
      { type: "string_too_long", loc: ["body", "text"], msg: "String should have at most 20000 characters" },
    ]);
    vitest.spyOn(api, "sendMessage").mockRejectedValue(new ApiError(422, dump));
    const { send, dispatch } = sendBehindATurn();

    await expect(send("một tin quá dài")).resolves.toEqual({ status: "failed", error: vi.sendFailed.other });
    expect(dispatch).toHaveBeenCalledWith({ type: "queue_failed", message: vi.requestErrors.invalid });
  });
});
