import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import { api, ApiError } from "../api/client";
import type { AgentEvent, ConversationDetail } from "../api/types";
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
  // As the thread's own does, it puts a turn that failed on screen and throws nothing on.
  const runTurn = async (run: (emit: (e: AgentEvent) => void, signal: AbortSignal) => Promise<void>) => {
    await run((event) => streamed.push(event), new AbortController().signal).catch(() => {});
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

/** The name each send went under, in the order the requests were made. */
const names = (sent: { mock: { calls: unknown[][] } }) => sent.mock.calls.map((call) => call[5]);
const lost = () => new TypeError("Failed to fetch");
const HEX = /^[0-9a-f]{32}$/;

describe("the name a message is sent under", () => {
  it("is a new one for each send, the same words or not", async () => {
    const sent = vitest.spyOn(api, "sendMessage").mockResolvedValue(undefined);
    const { send } = sendOnItsOwnStream();

    await send("một câu");
    await send("một câu");
    await send("câu khác");

    expect(names(sent)).toEqual([expect.stringMatching(HEX), expect.stringMatching(HEX), expect.stringMatching(HEX)]);
    expect(new Set(names(sent)).size).toBe(3);
  });

  it("is kept for the same words sent again after a send nothing was heard of", async () => {
    const sent = vitest.spyOn(api, "sendMessage").mockRejectedValueOnce(lost()).mockResolvedValue(undefined);
    const { send } = sendOnItsOwnStream();

    await expect(send("có tới không?")).resolves.toMatchObject({ status: "failed" });
    await expect(send("có tới không?")).resolves.toEqual({ status: "sent" });

    expect(names(sent)[0]).toMatch(HEX);
    expect(names(sent)[1]).toBe(names(sent)[0]);
    // Heard this time: the words sent a third time are a new message.
    await send("có tới không?");
    expect(names(sent)[2]).not.toBe(names(sent)[0]);
  });

  it("is a new one once the words were changed, and the old one is not kept for later", async () => {
    const sent = vitest.spyOn(api, "sendMessage").mockRejectedValueOnce(lost()).mockResolvedValue(undefined);
    const { send } = sendOnItsOwnStream();

    await send("câu đầu");
    await send("câu đầu, sửa lại");
    await send("câu đầu");

    expect(new Set(names(sent)).size).toBe(3);
  });

  it("is a new one in another conversation, whatever failed in the one before", async () => {
    const sent = vitest.spyOn(api, "sendMessage").mockRejectedValueOnce(lost()).mockResolvedValue(undefined);
    const runTurn = async (run: (emit: (e: AgentEvent) => void, signal: AbortSignal) => Promise<void>) => {
      await run(() => {}, new AbortController().signal).catch(() => {});
    };
    const { result, rerender } = renderHook(
      ({ id }) => useThreadSend({ conversationId: id, busy: false, dispatch: vitest.fn(), runTurn, queueing: { current: new Set() } }),
      { initialProps: { id: "c1" } },
    );

    await result.current("chào");
    rerender({ id: "c2" });
    await result.current("chào");

    expect(sent.mock.calls.map((call) => call[0])).toEqual(["c1", "c2"]);
    expect(names(sent)[1]).not.toBe(names(sent)[0]);
  });

  it("is not kept when the send failed after the server had answered: that message arrived", async () => {
    const sent = vitest.spyOn(api, "sendMessage").mockResolvedValue(undefined);
    sent.mockImplementationOnce(async (_id, _text, onEvent) => {
      onEvent({ type: "text_delta", text: "nửa câu" });
      throw lost();
    });
    const { send } = sendOnItsOwnStream();

    await expect(send("kể tiếp đi")).resolves.toEqual({ status: "sent" });
    await send("kể tiếp đi");

    expect(names(sent)[1]).not.toBe(names(sent)[0]);
  });

  it("is not kept when a queueing send failed after the server had said it waits", async () => {
    const sent = vitest.spyOn(api, "sendMessage").mockResolvedValue(undefined);
    sent.mockImplementationOnce(async (_id, _text, onEvent) => {
      onEvent({ type: "queued", item_id: 3, kind: "follow_up", position: 1 });
      throw lost();
    });
    const { send } = sendBehindATurn();

    await expect(send("nhắc lại nhé")).resolves.toEqual({ status: "queued" });
    await send("nhắc lại nhé");

    expect(names(sent)[1]).not.toBe(names(sent)[0]);
  });

  it("is kept across a send that failed while queueing behind this tab's own turn", async () => {
    const sent = vitest.spyOn(api, "sendMessage").mockRejectedValueOnce(lost()).mockResolvedValue(undefined);
    const { send, dispatch } = sendBehindATurn();

    await expect(send("chen vào")).resolves.toMatchObject({ status: "failed" });
    await send("chen vào");

    expect(dispatch).toHaveBeenCalledWith({ type: "queue_failed", message: vi.requestErrors.network });
    expect(names(sent)[0]).toMatch(HEX);
    expect(names(sent)[1]).toBe(names(sent)[0]);
  });
});

describe("a send made again behind this tab's own turn, which the server had taken the first time", () => {
  it("is answered with the turn as it stands: the words are spent, and the request is let go", async () => {
    const request: { signal?: AbortSignal } = {};
    vitest.spyOn(api, "sendMessage").mockImplementation(async (_id, _text, onEvent, signal) => {
      request.signal = signal;
      onEvent({ type: "watching", running: true, detail: {} as ConversationDetail });
      // The server goes on to relay the turn, which this tab already reads on its own stream.
      await new Promise<void>((_, reject) =>
        signal?.aborted ? reject(new DOMException("aborted", "AbortError")) : signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))),
      );
    });
    const { send, dispatch, queueing } = sendBehindATurn();

    await expect(send("đã tới rồi")).resolves.toEqual({ status: "sent" });
    await vitest.waitFor(() => expect(queueing.current.size).toBe(0));

    expect(request.signal?.aborted).toBe(true);
    // No chip, no notice, and nothing of that stream put into the thread a second time.
    expect(dispatch).not.toHaveBeenCalled();
  });

  it("keeps reading for the one event of a message that still waits", async () => {
    const request: { signal?: AbortSignal } = {};
    vitest.spyOn(api, "sendMessage").mockImplementation(async (_id, _text, onEvent, signal) => {
      request.signal = signal;
      onEvent({ type: "queued", item_id: 4, kind: "follow_up", position: 2 });
    });
    const { send, dispatch } = sendBehindATurn();

    await expect(send("vẫn đang chờ")).resolves.toEqual({ status: "queued" });

    expect(request.signal?.aborted).toBe(false);
    expect(dispatch).toHaveBeenCalledWith({ type: "queued", item: { id: 4, kind: "follow_up", text: "vẫn đang chờ" } });
  });
});
