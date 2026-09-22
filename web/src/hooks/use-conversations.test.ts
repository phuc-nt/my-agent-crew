import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { Conversation } from "../api/types";
import { useConversations } from "./use-conversations";

function conversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: "c1",
    agent_id: "default",
    channel: "",
    title: "Giúp tôi lập kế hoạch",
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

/** Holds the conversation list until the test lets it answer. */
function pendingList(body: Conversation[]) {
  let release = () => {};
  const done = new Promise<void>((resolve) => {
    release = () => resolve();
  });
  const fetch = vitest.fn(async () => {
    await done;
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  });
  return { fetch, release };
}

beforeEach(() => {
  vitest.unstubAllGlobals();
});

describe("a title the server pushes while the list is still loading", () => {
  it("is kept, not lost to the answer the fetch was already carrying", async () => {
    const { fetch, release } = pendingList([conversation()]);
    vitest.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useConversations());

    act(() => result.current.applyUpdate(conversation({ title: "Kế hoạch ôn thi" })));
    await act(async () => {
      release();
    });

    await waitFor(() => expect(result.current.conversations).toHaveLength(1));
    expect(result.current.conversations[0].title).toBe("Kế hoạch ôn thi");
  });

  it("leaves one row, not a copy beside the original", async () => {
    const { fetch, release } = pendingList([conversation()]);
    vitest.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useConversations());

    act(() => result.current.applyUpdate(conversation({ title: "Kế hoạch ôn thi" })));
    await act(async () => {
      release();
    });

    await waitFor(() => expect(result.current.conversations).toHaveLength(1));
  });

  // Two list fetches overlap on any ordinary load: the mount effect runs twice under
  // StrictMode, and a finished run refreshes the list too. The second must not answer
  // with the row the first had already reconciled the pushed title into.
  it("survives a second list fetch that was in flight alongside the first", async () => {
    const first = pendingList([conversation()]);
    const second = pendingList([conversation()]);
    const fetches = [first, second];
    let call = 0;
    vitest.stubGlobal("fetch", (...args: unknown[]) => fetches[call++ % 2].fetch(...(args as [])));
    const { result } = renderHook(() => useConversations());
    // The mount fetch is in flight; this is the second one overlapping it.
    let later: Promise<void>;
    act(() => {
      later = result.current.refresh();
    });

    act(() => result.current.applyUpdate(conversation({ title: "Kế hoạch ôn thi" })));
    await act(async () => {
      first.release();
      second.release();
      await later;
    });

    await waitFor(() => expect(result.current.conversations).toHaveLength(1));
    expect(result.current.conversations[0].title).toBe("Kế hoạch ôn thi");
  });

  it("lets a later fetch win, so a name typed elsewhere is not overwritten forever", async () => {
    const first = pendingList([conversation()]);
    vitest.stubGlobal("fetch", first.fetch);
    const { result } = renderHook(() => useConversations());

    act(() => result.current.applyUpdate(conversation({ title: "Kế hoạch ôn thi" })));
    await act(async () => {
      first.release();
    });
    await waitFor(() => expect(result.current.conversations[0].title).toBe("Kế hoạch ôn thi"));

    const second = pendingList([conversation({ title: "Tên tôi tự đặt" })]);
    vitest.stubGlobal("fetch", second.fetch);
    second.release();
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.conversations[0].title).toBe("Tên tôi tự đặt");
  });

  // Renaming says what the conversation is called; a title pushed earlier is then stale,
  // and a refresh that still held it would put the old name back after the run finished.
  it("is forgotten once the person renames the conversation themselves", async () => {
    const first = pendingList([conversation()]);
    vitest.stubGlobal("fetch", first.fetch);
    const { result } = renderHook(() => useConversations());
    first.release();
    await waitFor(() => expect(result.current.conversations).toHaveLength(1));

    act(() => result.current.applyUpdate(conversation({ title: "Kế hoạch ôn thi" })));

    const renamed = conversation({ title: "Tên tôi tự đặt" });
    const patch = pendingList([renamed]);
    vitest.stubGlobal("fetch", patch.fetch);
    patch.release();
    await act(async () => {
      await result.current.patch("c1", { title: "Tên tôi tự đặt" });
    });

    // The server has the new name now; a refresh must not resurrect the pushed one.
    const later = pendingList([renamed]);
    vitest.stubGlobal("fetch", later.fetch);
    later.release();
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.conversations[0].title).toBe("Tên tôi tự đặt");
  });

  it("ignores a delegate's conversation, which this list never shows", async () => {
    const { fetch, release } = pendingList([conversation()]);
    vitest.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useConversations());
    release();
    await waitFor(() => expect(result.current.conversations).toHaveLength(1));

    act(() =>
      result.current.applyUpdate(conversation({ id: "c2", agent_id: "coach", title: "Việc của HLV" })),
    );
    expect(result.current.conversations).toHaveLength(1);
    expect(result.current.conversations[0].title).toBe("Giúp tôi lập kế hoạch");
  });
});
