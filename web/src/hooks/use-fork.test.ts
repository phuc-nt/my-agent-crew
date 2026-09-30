import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { Conversation, ConversationDetail, ForkResult } from "../api/types";
import { memoryStorage } from "../test/memory-storage";
import type { ThreadItem } from "../state/thread-reducer";
import { storedMessage } from "../test/fake-backend";
import { useDraft } from "./use-draft";
import { useFork } from "./use-fork";

function conversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: "c1",
    agent_id: "default",
    channel: "",
    title: "Việc",
    created_at: "",
    updated_at: "",
    autonomous: false,
    cost_cap_usd: 1,
    spent_usd: 0,
    unknown_cost_calls: 0,
    status: "idle",
    over_budget: false,
    summary: "",
    skills: [],
    auto_approve: [],
    ...overrides,
  } as Conversation;
}

/** Answers GET /conversations/c1 with `detail`, and POST …/fork with `fork` (or 500 when
 *  `fork` is null, the way a server error would). Every other path 404s. */
function stubApi(detail: ConversationDetail, fork: ForkResult | null) {
  const calls: { path: string; body: unknown }[] = [];
  vitest.stubGlobal(
    "fetch",
    vitest.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const path = new URL(String(input), "http://fake").pathname.replace(/^\/api/, "");
      const body = init.body ? JSON.parse(String(init.body)) : null;
      calls.push({ path, body });
      if (path === "/conversations/c1" && (init.method ?? "GET") === "GET") {
        return json(detail);
      }
      if (path === "/conversations/c1/fork" && init.method === "POST") {
        return fork ? json(fork, 201) : json({ detail: "lỗi" }, 500);
      }
      return json({ detail: "no route" }, 404);
    }),
  );
  return calls;
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function forkResult(overrides: Partial<ForkResult> = {}): ForkResult {
  return { ...conversation({ id: "c2", title: "Việc (nhánh)", forked_from: "c1" }), draft: "hỏi lại", ...overrides };
}

beforeEach(() => {
  vitest.unstubAllGlobals();
});

describe("resolving which message the fork button was actually pressed under", () => {
  it("uses a numeric id straight away, with no extra read of the conversation", async () => {
    const calls = stubApi({ ...conversation(), messages: [], pending_approval: null }, forkResult());
    const refresh = vitest.fn(async () => {});
    const onSelect = vitest.fn();
    const { result } = renderHook(() => useFork({ activeId: "c1", refresh, onSelectConversation: onSelect }));

    const item: ThreadItem = { id: "42", kind: "user", text: "hỏi lại" };
    let ok = false;
    await act(async () => {
      ok = await result.current.fork("c1", item, [item]);
    });

    expect(ok).toBe(true);
    expect(calls.map((c) => c.path)).toEqual(["/conversations/c1/fork"]);
    expect(calls[0].body).toEqual({ before_message_id: 42 });
    expect(refresh).toHaveBeenCalled();
    expect(onSelect).toHaveBeenCalledWith("c2");
  });

  it("resolves a local-N id by reading the conversation once and counting from the end", async () => {
    const detail: ConversationDetail = {
      ...conversation(),
      pending_approval: null,
      messages: [
        storedMessage("user", "một", { id: "10" }),
        storedMessage("assistant", "trả lời", { id: "11" }),
        storedMessage("user", "hỏi lại", { id: "12" }),
      ],
    };
    const calls = stubApi(detail, forkResult());
    const { result } = renderHook(() =>
      useFork({ activeId: "c1", refresh: vitest.fn(async () => {}), onSelectConversation: vitest.fn() }),
    );

    // Two user bubbles rendered so far; the fresh one clicked is the last (1st from the end).
    const items: ThreadItem[] = [
      { id: "10", kind: "user", text: "một" },
      { id: "11", kind: "assistant", text: "trả lời", model: null },
      { id: "local-2", kind: "user", text: "hỏi lại" },
    ];
    let ok = false;
    await act(async () => {
      ok = await result.current.fork("c1", items[2], items);
    });

    expect(ok).toBe(true);
    expect(calls.map((c) => c.path)).toEqual(["/conversations/c1", "/conversations/c1/fork"]);
    expect(calls[1].body).toEqual({ before_message_id: 12 });
  });

  it("gives up without ever calling the fork API when the text at that position no longer matches", async () => {
    const detail: ConversationDetail = {
      ...conversation(),
      pending_approval: null,
      messages: [storedMessage("user", "đã đổi ý", { id: "10" })],
    };
    const calls = stubApi(detail, forkResult());
    const { result } = renderHook(() =>
      useFork({ activeId: "c1", refresh: vitest.fn(async () => {}), onSelectConversation: vitest.fn() }),
    );

    const items: ThreadItem[] = [{ id: "local-0", kind: "user", text: "chữ đã gõ" }];
    let ok = true;
    await act(async () => {
      ok = await result.current.fork("c1", items[0], items);
    });

    expect(ok).toBe(false);
    expect(calls).toHaveLength(1); // only the one GET; no POST /fork
    expect(result.current.error).toBe("Không rẽ nhánh được: không tìm thấy đúng tin nhắn.");
  });
});

describe("what a click does once the real message id is known", () => {
  it("saves the fork's draft, refreshes the list, and selects the fork", async () => {
    memoryStorage();
    stubApi({ ...conversation(), messages: [], pending_approval: null }, forkResult({ id: "c9", draft: "sửa câu này" }));
    const refresh = vitest.fn(async () => {});
    const onSelect = vitest.fn();
    const { result } = renderHook(() => useFork({ activeId: "c1", refresh, onSelectConversation: onSelect }));
    // Mounted on the conversation open before the fork, the way the real composer is: only
    // a later switch onto the fork's own key should ever show what `fork` saved for it.
    const draftHook = renderHook(({ key }) => useDraft(key), { initialProps: { key: "c1" } });

    await act(async () => {
      await result.current.fork("c1", { id: "5", kind: "user", text: "sửa câu này" }, []);
    });

    draftHook.rerender({ key: "c9" });
    expect(draftHook.result.current[0]).toBe("sửa câu này");
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith("c9");
    expect(result.current.error).toBeNull();
  });

  it("shows forkFailed and stays put when the server refuses the fork", async () => {
    stubApi({ ...conversation(), messages: [], pending_approval: null }, null);
    const refresh = vitest.fn(async () => {});
    const onSelect = vitest.fn();
    const { result } = renderHook(() => useFork({ activeId: "c1", refresh, onSelectConversation: onSelect }));

    let ok = true;
    await act(async () => {
      ok = await result.current.fork("c1", { id: "5", kind: "user", text: "hỏi" }, []);
    });

    expect(ok).toBe(false);
    expect(refresh).not.toHaveBeenCalled();
    expect(onSelect).not.toHaveBeenCalled();
    await waitFor(() => expect(result.current.error).toBe("Không rẽ nhánh được: không tìm thấy đúng tin nhắn."));
  });
});

describe("where a failed fork is reported", () => {
  const failed = "Không rẽ nhánh được: không tìm thấy đúng tin nhắn.";
  const options = (activeId: string) => ({
    activeId,
    refresh: vitest.fn(async () => {}),
    onSelectConversation: vitest.fn(),
  });

  it("only on the conversation it failed in, and not again on the way back to it", async () => {
    stubApi({ ...conversation(), messages: [], pending_approval: null }, null);
    const { result, rerender } = renderHook(({ activeId }) => useFork(options(activeId)), {
      initialProps: { activeId: "c1" },
    });

    await act(async () => {
      await result.current.fork("c1", { id: "5", kind: "user", text: "hỏi" }, []);
    });
    expect(result.current.error).toBe(failed);

    rerender({ activeId: "c2" });
    expect(result.current.error).toBeNull();

    rerender({ activeId: "c1" });
    expect(result.current.error).toBeNull();
  });

  it("never, when it fails after the person has already moved to another conversation", async () => {
    let answer: (response: Response) => void = () => {};
    const fetch = vitest.fn(() => new Promise<Response>((resolve) => (answer = resolve)));
    vitest.stubGlobal("fetch", fetch);
    const { result, rerender } = renderHook(({ activeId }) => useFork(options(activeId)), {
      initialProps: { activeId: "c1" },
    });

    let attempt: Promise<boolean> = Promise.resolve(true);
    act(() => {
      attempt = result.current.fork("c1", { id: "5", kind: "user", text: "hỏi" }, []);
    });
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    rerender({ activeId: "c2" });
    let ok = true;
    await act(async () => {
      answer(json({ detail: "lỗi" }, 500));
      ok = await attempt;
    });

    expect(ok).toBe(false);
    expect(result.current.error).toBeNull();
    rerender({ activeId: "c1" });
    expect(result.current.error).toBeNull();
  });
});
