import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { api } from "../api/client";
import type { AgentEvent, ApprovalKind, ConversationDetail, QueuedMessage } from "../api/types";
import { useThread } from "./use-thread";

/** An idle conversation with nothing pending: the base case for send-while-busy tests,
 *  which mock the state a first turn already left on screen rather than replaying it. */
function idle(overrides: Partial<ConversationDetail> = {}): ConversationDetail {
  return { ...paused("tool"), status: "idle", pending_approval: null, ...overrides };
}

/** An `api.sendMessage` implementation that emits exactly one event and ends — the shape of
 *  the busy-send POST's own response, and of the plain path once the server queues it. */
function oneShot(event: AgentEvent) {
  return async (_id: string, _text: string, onEvent: (e: AgentEvent) => void) => {
    onEvent(event);
  };
}

/** A conversation paused on its first call, with a second call queued behind it. */
function paused(kind: ApprovalKind): ConversationDetail {
  const call = (id: string, name: string) => ({ id, name, arguments: {} });
  return {
    id: "c1",
    agent_id: "default",
    channel: "",
    title: "",
    created_at: "",
    updated_at: "",
    autonomous: false,
    cost_cap_usd: 1,
    summary: "",
    skills: [],
    auto_approve: [],
    parent_call_id: "",
    spent_usd: 0,
    unknown_cost_calls: 0,
    status: "awaiting_approval",
    over_budget: false,
    messages: [
      {
        id: "m1",
        seq: 1,
        role: "assistant",
        content: "",
        tool_calls: [call("tc1", kind === "question" ? "ask_user" : "write_file"), call("tc2", "read_file")],
        tool_call_id: null,
        name: null,
        provider: "fake",
        model: "echo",
        cost_usd: 0,
        created_at: "",
      },
    ],
    pending_approval: {
      id: "ap",
      conversation_id: "c1",
      message_id: "m1",
      tool_call_id: "tc1",
      tool_name: kind === "question" ? "ask_user" : "write_file",
      arguments: {},
      status: "pending",
      created_at: "",
      expires_at: null,
      resolved_at: null,
      kind,
    },
  };
}

/** A stream that says what it is given and then hangs until its fetch is aborted, the
 *  way a real one hangs on a slow tool. */
function heldStream() {
  const held: { emit: (e: AgentEvent) => void; signal?: AbortSignal } = { emit: () => {} };
  const open = (emit: (e: AgentEvent) => void, signal?: AbortSignal) => {
    held.emit = emit;
    held.signal = signal;
    emit({ type: "tool_call", tool_call_id: "tc1", name: "write_file", arguments: {} });
    return new Promise<void>((_, reject) => {
      signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    });
  };
  return { held, open };
}

async function openPaused(kind: ApprovalKind) {
  vitest.spyOn(api, "getConversation").mockResolvedValue(paused(kind));
  const hook = renderHook(() => useThread("c1"));
  await waitFor(() => expect(hook.result.current.state.pending?.kind).toBe(kind));
  return hook;
}

const statuses = (items: { kind: string; status?: string }[]) =>
  items.filter((it) => it.kind === "tool").map((it) => it.status);

afterEach(() => {
  vitest.restoreAllMocks();
});

describe("Stop on a stream that resumed after a person answered", () => {
  it("aborts the decision's fetch, drops what it still sends and says the turn stopped", async () => {
    const { held, open } = heldStream();
    vitest
      .spyOn(api, "resolveApproval")
      .mockImplementation((_id, _ap, _ok, emit, _always, signal) => open(emit, signal));
    vitest.spyOn(api, "stopConversation").mockResolvedValue({ cleared: [], cancelled: true });
    const { result } = await openPaused("tool");

    let turn: Promise<void> = Promise.resolve();
    act(() => {
      turn = result.current.decide(true);
    });
    await waitFor(() => expect(held.signal).toBeDefined());
    expect(result.current.state.busy).toBe(true);

    await act(() => result.current.stop());
    await act(() => turn);
    expect(held.signal?.aborted).toBe(true);

    // A late event from the cut stream must not reach the thread.
    act(() => held.emit({ type: "text_delta", text: "vẫn còn" }));
    const { state } = result.current;
    expect(state.streaming).toBeNull();
    expect(state.busy).toBe(false);
    expect(state.notice).toEqual({ kind: "stopped", text: "" });
    expect(statuses(state.items)).toEqual(["stopped", "stopped"]);
  });

  it("aborts an answer's fetch the same way", async () => {
    const { held, open } = heldStream();
    vitest.spyOn(api, "answerApproval").mockImplementation((_id, _ap, _text, emit, signal) => open(emit, signal));
    vitest.spyOn(api, "stopConversation").mockResolvedValue({ cleared: [], cancelled: true });
    const { result } = await openPaused("question");

    let turn: Promise<void> = Promise.resolve();
    act(() => {
      turn = result.current.answer("thứ sáu");
    });
    await waitFor(() => expect(held.signal).toBeDefined());
    await act(() => result.current.stop());
    await act(() => turn);

    expect(held.signal?.aborted).toBe(true);
    expect(result.current.state.notice?.kind).toBe("stopped");
    expect(statuses(result.current.state.items)).not.toContain("running");
  });
});

describe("a thread another conversation has replaced", () => {
  it("is not loaded again by a caller still holding the reload it was opened with", async () => {
    const opened = (id: string): ConversationDetail => ({
      ...paused("tool"),
      id,
      title: `Hội thoại ${id}`,
      status: "idle",
      pending_approval: null,
    });
    const load = vitest.spyOn(api, "getConversation").mockImplementation(async (id) => opened(id));
    const { result, rerender } = renderHook(({ id }) => useThread(id), { initialProps: { id: "c1" } });
    await waitFor(() => expect(result.current.detail?.id).toBe("c1"));
    // A raise of the cap, say, that went out from the first one and answers now.
    const reloadLeft = result.current.reload;
    rerender({ id: "c2" });
    await waitFor(() => expect(result.current.detail?.id).toBe("c2"));

    load.mockClear();
    await act(() => reloadLeft());
    expect(load).not.toHaveBeenCalled();
    expect(result.current.detail?.title).toBe("Hội thoại c2");
  });
});

describe("send while this tab's own turn is running", () => {
  it("goes a second POST instead of runTurn, and the running turn keeps working and can still be stopped", async () => {
    vitest.spyOn(api, "getConversation").mockResolvedValue(idle());
    const { held, open } = heldStream();
    vitest.spyOn(api, "sendMessage").mockImplementationOnce((_id, _text, emit, signal) => open(emit, signal));
    const queueing = vitest.fn(oneShot({ type: "queued", item_id: 1, kind: "follow_up", position: 1 }));
    vitest.spyOn(api, "sendMessage").mockImplementationOnce(queueing);
    vitest.spyOn(api, "stopConversation").mockResolvedValue({ cleared: [], cancelled: true });
    const { result } = renderHook(() => useThread("c1"));
    await waitFor(() => expect(result.current.detail).not.toBeNull());

    let firstTurn: Promise<string | null> = Promise.resolve(null);
    act(() => {
      firstTurn = result.current.send("việc đầu tiên");
    });
    await waitFor(() => expect(held.signal).toBeDefined());
    expect(result.current.state.busy).toBe(true);
    const itemsAfterFirst = result.current.state.items.length;

    await act(() => result.current.send("chen ngang khi bận"));
    // A busy-send never runs `runTurn`, `user_sent` or `turn_started`: the thread's own
    // items are untouched but for the chip, and `busy` still reflects the first stream.
    expect(queueing).toHaveBeenCalledWith("c1", "chen ngang khi bận", expect.any(Function), expect.anything());
    expect(result.current.state.busy).toBe(true);
    expect(result.current.state.items).toHaveLength(itemsAfterFirst);
    expect(result.current.state.waiting).toEqual([{ id: 1, kind: "follow_up", text: "chen ngang khi bận" }]);

    // The first stream is still the one running: a late event from it still lands, and
    // Stop still cuts exactly that stream — proof the busy POST never touched `abortRef`.
    act(() => held.emit({ type: "tool_call", tool_call_id: "tc2", name: "read_file", arguments: {} }));
    expect(result.current.state.items.some((it) => it.kind === "tool" && it.id === "tc2")).toBe(true);

    await act(() => result.current.stop());
    await act(() => firstTurn);
    expect(held.signal?.aborted).toBe(true);
    expect(result.current.state.busy).toBe(false);
  });

  it("aborts a queueing POST still in flight when the conversation is switched", async () => {
    vitest.spyOn(api, "getConversation").mockImplementation(async (id) => idle({ id }));
    const { held: firstHeld, open: openFirst } = heldStream();
    vitest.spyOn(api, "sendMessage").mockImplementationOnce((_id, _text, emit, signal) => openFirst(emit, signal));
    const { held: queueHeld, open: openQueue } = heldStream();
    let queueSignal: AbortSignal | undefined;
    vitest.spyOn(api, "sendMessage").mockImplementationOnce((_id, _text, emit, signal) => {
      queueSignal = signal;
      return openQueue(emit, signal);
    });
    const { result, rerender } = renderHook(({ id }) => useThread(id), { initialProps: { id: "c1" } });
    await waitFor(() => expect(result.current.detail?.id).toBe("c1"));

    act(() => {
      void result.current.send("việc đầu tiên");
    });
    await waitFor(() => expect(firstHeld.signal).toBeDefined());
    act(() => {
      void result.current.send("còn treo khi đổi hội thoại");
    });
    await waitFor(() => expect(queueSignal).toBeDefined());

    rerender({ id: "c2" });
    await waitFor(() => expect(queueSignal?.aborted).toBe(true));
    expect(queueHeld.signal?.aborted).toBe(true);
  });
});

describe("send while the conversation is busy elsewhere (this tab thought it was idle)", () => {
  it("catches the queued event on the plain send path and turns the temp bubble into a chip", async () => {
    vitest.spyOn(api, "getConversation").mockResolvedValue(idle());
    vitest
      .spyOn(api, "sendMessage")
      .mockImplementation(oneShot({ type: "queued", item_id: 7, kind: "follow_up", position: 1 }));
    const { result } = renderHook(() => useThread("c1"));
    await waitFor(() => expect(result.current.detail).not.toBeNull());
    const itemsBefore = result.current.state.items.length;

    await act(() => result.current.send("tưởng rảnh mà server bận"));

    // `user_sent` added a local bubble first, as the plain path always does; the `queued`
    // event then drops it in favour of the chip, per the reducer's own dedupe rule.
    expect(result.current.state.items).toHaveLength(itemsBefore);
    expect(result.current.state.waiting).toEqual([{ id: 7, kind: "follow_up", text: "tưởng rảnh mà server bận" }]);
    expect(result.current.state.busy).toBe(false);
  });
});

describe("send while busy hits the queue's own limits", () => {
  it.each([429, 422])("a %d from the queueing POST shows the server's own text and hands the text back to restore", async (status) => {
    vitest.spyOn(api, "getConversation").mockResolvedValue(idle());
    const { held, open } = heldStream();
    vitest.spyOn(api, "sendMessage").mockImplementationOnce((_id, _text, emit, signal) => open(emit, signal));
    const { ApiError } = await import("../api/client");
    vitest.spyOn(api, "sendMessage").mockImplementationOnce(() => Promise.reject(new ApiError(status, "hàng đầy, hãy chờ hoặc bấm Stop")));
    const { result } = renderHook(() => useThread("c1"));
    await waitFor(() => expect(result.current.detail).not.toBeNull());
    act(() => {
      void result.current.send("việc đầu tiên");
    });
    await waitFor(() => expect(held.signal).toBeDefined());

    let restored: string | null = "unset";
    await act(async () => {
      restored = await result.current.send("gõ trúng lúc trần đầy");
    });

    expect(restored).toBe("gõ trúng lúc trần đầy");
    expect(result.current.state.notice).toEqual({ kind: "error", text: "hàng đầy, hãy chờ hoặc bấm Stop" });
    // The queueing POST's own error never touches `busy`: the running stream is unaffected.
    expect(result.current.state.busy).toBe(true);
  });
});

describe("Stop, redesigned: server first, then abort, chip text back in order", () => {
  beforeEach(() => {
    // `shouldAdvanceTime` keeps `waitFor`'s own polling and React's scheduler moving in
    // near-real-time while still letting the test jump the clock forward explicitly for
    // `STOP_WAIT_MS` — see the same pattern in attention-center.test.tsx.
    vitest.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vitest.useRealTimers();
  });

  it("calls the server before aborting, returns the cleared texts in queue order and clears the chips", async () => {
    vitest.spyOn(api, "getConversation").mockResolvedValue(idle());
    const { held, open } = heldStream();
    vitest.spyOn(api, "sendMessage").mockImplementation((_id, _text, emit, signal) => open(emit, signal));
    const cleared: QueuedMessage[] = [
      { id: 1, kind: "follow_up", text: "đầu tiên" },
      { id: 2, kind: "steer", text: "chèn sau" },
    ];
    const order: string[] = [];
    const stopSpy = vitest.spyOn(api, "stopConversation").mockImplementation(async () => {
      order.push("server");
      return { cleared, cancelled: true };
    });
    const { result } = renderHook(() => useThread("c1"));
    await waitFor(() => expect(result.current.detail).not.toBeNull());
    act(() => {
      void result.current.send("việc đầu tiên");
    });
    await waitFor(() => expect(held.signal).toBeDefined());

    let texts: string[] = [];
    await act(async () => {
      texts = await result.current.stop();
    });
    if (!held.signal?.aborted) order.push("abort-not-yet");
    expect(stopSpy).toHaveBeenCalledTimes(1);
    expect(order[0]).toBe("server");
    expect(held.signal?.aborted).toBe(true);
    expect(texts).toEqual(["đầu tiên", "chèn sau"]);
    expect(result.current.state.waiting).toEqual([]);
    expect(result.current.state.notice?.kind).toBe("stopped");
  });

  it("shows no notice when Stop only had chips to clear and nothing was running", async () => {
    vitest.spyOn(api, "getConversation").mockResolvedValue(idle());
    vitest.spyOn(api, "stopConversation").mockResolvedValue({
      cleared: [{ id: 1, kind: "follow_up", text: "chỉ có chip" }],
      cancelled: false,
    });
    const { result } = renderHook(() => useThread("c1"));
    await waitFor(() => expect(result.current.detail).not.toBeNull());
    expect(result.current.state.busy).toBe(false);

    let texts: string[] = [];
    await act(async () => {
      texts = await result.current.stop();
    });

    expect(texts).toEqual(["chỉ có chip"]);
    expect(result.current.state.notice).toBeNull();
  });

  it("says `elsewhere` on an external run the server could not cancel, and still clears the chips", async () => {
    vitest.spyOn(api, "getConversation").mockResolvedValue(idle());
    vitest.spyOn(api, "stopConversation").mockResolvedValue({
      cleared: [{ id: 1, kind: "follow_up", text: "chip còn đó" }],
      cancelled: false,
    });
    const { result } = renderHook(() => useThread("c1"));
    await waitFor(() => expect(result.current.detail).not.toBeNull());

    let texts: string[] = [];
    await act(async () => {
      texts = await result.current.stop(true);
    });

    expect(texts).toEqual(["chip còn đó"]);
    expect(result.current.state.waiting).toEqual([]);
    expect(result.current.state.notice).toEqual({ kind: "elsewhere", text: "" });
  });

  it("still aborts locally and keeps the chips when the server errors, and returns no text", async () => {
    vitest.spyOn(api, "getConversation").mockResolvedValue(idle({ queued: [{ id: 1, kind: "follow_up", text: "vẫn ở hàng" }] }));
    const { held, open } = heldStream();
    vitest.spyOn(api, "sendMessage").mockImplementation((_id, _text, emit, signal) => open(emit, signal));
    vitest.spyOn(api, "stopConversation").mockRejectedValue(new Error("network"));
    const { result } = renderHook(() => useThread("c1"));
    await waitFor(() => expect(result.current.detail).not.toBeNull());
    act(() => {
      void result.current.send("việc đầu tiên");
    });
    await waitFor(() => expect(held.signal).toBeDefined());

    let texts: string[] = [];
    await act(async () => {
      texts = await result.current.stop();
    });

    expect(texts).toEqual([]);
    expect(held.signal?.aborted).toBe(true);
    expect(result.current.state.busy).toBe(false);
    expect(result.current.state.notice?.kind).toBe("stopped");
    expect(result.current.state.waiting).toEqual([{ id: 1, kind: "follow_up", text: "vẫn ở hàng" }]);
  });

  it("aborts locally once STOP_WAIT_MS elapses when the server hangs, driven by fake timers", async () => {
    vitest.spyOn(api, "getConversation").mockResolvedValue(idle());
    const { held, open } = heldStream();
    vitest.spyOn(api, "sendMessage").mockImplementation((_id, _text, emit, signal) => open(emit, signal));
    // A hung server: the call never answers on its own, exactly like a real fetch whose
    // response never comes — but a real fetch does reject once its own `AbortSignal` fires,
    // which is what `STOP_WAIT_MS`'s own controller is for.
    vitest.spyOn(api, "stopConversation").mockImplementation(
      (_id, signal) =>
        new Promise((_resolve, reject) => {
          signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
    const { result } = renderHook(() => useThread("c1"));
    await waitFor(() => expect(result.current.detail).not.toBeNull());
    act(() => {
      void result.current.send("việc đầu tiên");
    });
    await waitFor(() => expect(held.signal).toBeDefined());

    let texts: string[] | null = null;
    let settled = false;
    act(() => {
      void result.current.stop().then((t) => {
        texts = t;
        settled = true;
      });
    });
    expect(settled).toBe(false);
    expect(held.signal?.aborted).toBe(false);

    await act(async () => {
      await vitest.advanceTimersByTimeAsync(3000);
    });
    expect(held.signal?.aborted).toBe(true);
    expect(settled).toBe(true);
    expect(texts).toEqual([]);
  });

  it("only calls the server once on a double press", async () => {
    vitest.spyOn(api, "getConversation").mockResolvedValue(idle());
    const { held, open } = heldStream();
    vitest.spyOn(api, "sendMessage").mockImplementation((_id, _text, emit, signal) => open(emit, signal));
    let resolveStop: (r: { cleared: QueuedMessage[]; cancelled: boolean }) => void = () => {};
    const stopSpy = vitest.spyOn(api, "stopConversation").mockImplementation(
      () => new Promise((resolve) => (resolveStop = resolve)),
    );
    const { result } = renderHook(() => useThread("c1"));
    await waitFor(() => expect(result.current.detail).not.toBeNull());
    act(() => {
      void result.current.send("việc đầu tiên");
    });
    await waitFor(() => expect(held.signal).toBeDefined());

    let first: Promise<string[]> = Promise.resolve([]);
    let second: Promise<string[]> = Promise.resolve([]);
    act(() => {
      first = result.current.stop();
      second = result.current.stop();
    });
    resolveStop({ cleared: [], cancelled: true });
    await act(async () => {
      expect(await second).toEqual([]);
      await first;
    });
    expect(stopSpy).toHaveBeenCalledTimes(1);
  });
});
