import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { api } from "../api/client";
import type { ContentHit } from "../api/types";
import { useContentSearch } from "./use-content-search";

function hit(overrides: Partial<ContentHit> = {}): ContentHit {
  return {
    conversation_id: "c1",
    agent_id: "coach",
    title: "Kế hoạch tuần",
    message_id: "m1",
    role: "user",
    snippet: "…đọc sách mỗi tối…",
    created_at: "2026-09-29T10:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  // `shouldAdvanceTime` keeps `waitFor`'s own polling and the search promise's microtasks
  // moving in near-real-time while still letting the test jump the clock forward
  // deterministically for the debounce window — see the same pattern in use-thread.test.ts.
  vitest.useFakeTimers({ shouldAdvanceTime: true });
});
afterEach(() => {
  vitest.useRealTimers();
  vitest.restoreAllMocks();
});

describe("the debounced content search behind 'Trong nội dung'", () => {
  it("waits 250ms of no typing before calling the API, and skips a call the next keystroke cancels", async () => {
    const search = vitest.spyOn(api, "searchMessages").mockResolvedValue({ hits: [hit()] });
    const { result, rerender } = renderHook(({ q }) => useContentSearch(q, true), {
      initialProps: { q: "doc" },
    });
    expect(search).not.toHaveBeenCalled();

    act(() => vitest.advanceTimersByTime(100));
    rerender({ q: "doc s" });
    // The first debounce window never fired: restarting it must not queue a stale call
    // once the newer one lands.
    act(() => vitest.advanceTimersByTime(150));
    expect(search).not.toHaveBeenCalled();

    act(() => vitest.advanceTimersByTime(100));
    expect(search).toHaveBeenCalledTimes(1);
    expect(search).toHaveBeenCalledWith("doc s", expect.any(AbortSignal));
    await waitFor(() => expect(result.current.hits).toEqual([hit()]));
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBe(false);
  });

  it("never calls the API for a query under 2 characters, and clears any earlier hits", async () => {
    const search = vitest.spyOn(api, "searchMessages").mockResolvedValue({ hits: [hit()] });
    const { result, rerender } = renderHook(({ q }) => useContentSearch(q, true), {
      initialProps: { q: "doc" },
    });
    act(() => vitest.advanceTimersByTime(250));
    await waitFor(() => expect(result.current.hits).toEqual([hit()]));

    rerender({ q: "d" });
    act(() => vitest.advanceTimersByTime(250));

    expect(search).toHaveBeenCalledTimes(1);
    expect(result.current.hits).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it("aborts the in-flight request when the query changes again before it answers", async () => {
    let releaseFirst!: () => void;
    const first = new Promise<{ hits: ContentHit[] }>((resolve) => {
      releaseFirst = () => resolve({ hits: [hit({ conversation_id: "stale" })] });
    });
    const signals: AbortSignal[] = [];
    vitest.spyOn(api, "searchMessages").mockImplementation((_q, signal) => {
      signals.push(signal as AbortSignal);
      return signals.length === 1 ? first : Promise.resolve({ hits: [hit({ conversation_id: "fresh" })] });
    });
    const { result, rerender } = renderHook(({ q }) => useContentSearch(q, true), {
      initialProps: { q: "doc" },
    });
    act(() => vitest.advanceTimersByTime(250));
    await waitFor(() => expect(signals.length).toBe(1));

    rerender({ q: "sach" });
    act(() => vitest.advanceTimersByTime(250));
    await waitFor(() => expect(signals.length).toBe(2));
    expect(signals[0].aborted).toBe(true);

    releaseFirst();
    await waitFor(() => expect(result.current.hits).toEqual([hit({ conversation_id: "fresh" })]));
    // The stale answer must never overwrite the fresh one that already landed.
    expect(result.current.hits).not.toEqual([hit({ conversation_id: "stale" })]);
  });

  it("reports a real failure as an error, but a cancelled request as no error at all", async () => {
    vitest.spyOn(api, "searchMessages").mockRejectedValue(new Error("mạng lỗi"));
    const { result } = renderHook(({ q }) => useContentSearch(q, true), {
      initialProps: { q: "doc" },
    });
    act(() => vitest.advanceTimersByTime(250));
    await waitFor(() => expect(result.current.error).toBe(true));
    expect(result.current.loading).toBe(false);
    expect(result.current.hits).toBeNull();
  });

  it("does not call the API at all while disabled, even for a long query", () => {
    const search = vitest.spyOn(api, "searchMessages").mockResolvedValue({ hits: [] });
    renderHook(({ q }) => useContentSearch(q, false), { initialProps: { q: "doc sach" } });
    act(() => vitest.advanceTimersByTime(250));
    expect(search).not.toHaveBeenCalled();
  });

  it("retries the same query immediately, without waiting out another debounce window", async () => {
    const search = vitest
      .spyOn(api, "searchMessages")
      .mockRejectedValueOnce(new Error("mạng lỗi"))
      .mockResolvedValueOnce({ hits: [hit()] });
    const { result } = renderHook(({ q }) => useContentSearch(q, true), {
      initialProps: { q: "doc" },
    });
    act(() => vitest.advanceTimersByTime(250));
    await waitFor(() => expect(result.current.error).toBe(true));

    act(() => result.current.retry());
    // No `advanceTimersByTime` at all: a retry is a direct request, not a keystroke.
    await waitFor(() => expect(result.current.hits).toEqual([hit()]));
    expect(search).toHaveBeenCalledTimes(2);
    expect(result.current.error).toBe(false);
  });
});
