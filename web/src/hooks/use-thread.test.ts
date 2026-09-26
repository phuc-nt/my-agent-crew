import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import { api } from "../api/client";
import type { AgentEvent, ApprovalKind, ConversationDetail } from "../api/types";
import { useThread } from "./use-thread";

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
    const { result } = await openPaused("tool");

    let turn: Promise<void> = Promise.resolve();
    act(() => {
      turn = result.current.decide(true);
    });
    await waitFor(() => expect(held.signal).toBeDefined());
    expect(result.current.state.busy).toBe(true);

    act(() => result.current.stop());
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
    const { result } = await openPaused("question");

    let turn: Promise<void> = Promise.resolve();
    act(() => {
      turn = result.current.answer("thứ sáu");
    });
    await waitFor(() => expect(held.signal).toBeDefined());
    act(() => result.current.stop());
    await act(() => turn);

    expect(held.signal?.aborted).toBe(true);
    expect(result.current.state.notice?.kind).toBe("stopped");
    expect(statuses(result.current.state.items)).not.toContain("running");
  });
});
