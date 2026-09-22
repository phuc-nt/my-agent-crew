import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useAutoScroll } from "./use-auto-scroll";

/** jsdom lays nothing out, so the element reports the geometry each case is about. */
function element(geometry: { scrollHeight: number; clientHeight: number; scrollTop: number }) {
  return { ...geometry } as unknown as HTMLElement;
}

describe("useAutoScroll", () => {
  it("starts pinned to the bottom", () => {
    const { result } = renderHook(() => useAutoScroll<HTMLElement>());
    expect(result.current.atBottom).toBe(true);
  });

  it("lets go when the reader scrolls up and takes hold again at the bottom", () => {
    const { result } = renderHook(() => useAutoScroll<HTMLElement>());
    const el = element({ scrollHeight: 1000, clientHeight: 400, scrollTop: 600 });
    result.current.ref.current = el;

    // Still at the very bottom: 1000 - 600 - 400 = 0.
    act(() => result.current.onScroll());
    expect(result.current.atBottom).toBe(true);

    el.scrollTop = 100;
    act(() => result.current.onScroll());
    expect(result.current.atBottom).toBe(false);

    el.scrollTop = 600;
    act(() => result.current.onScroll());
    expect(result.current.atBottom).toBe(true);
  });

  it("treats a few pixels off the bottom as still being at the bottom", () => {
    const { result } = renderHook(() => useAutoScroll<HTMLElement>());
    // Rounding in a zoomed browser leaves a gap of a pixel or two that nobody chose.
    result.current.ref.current = element({ scrollHeight: 1000, clientHeight: 400, scrollTop: 598 });

    act(() => result.current.onScroll());

    expect(result.current.atBottom).toBe(true);
  });

  it("jumping to the newest scrolls all the way down and re-pins", () => {
    const { result } = renderHook(() => useAutoScroll<HTMLElement>());
    const el = element({ scrollHeight: 1000, clientHeight: 400, scrollTop: 0 });
    result.current.ref.current = el;
    act(() => result.current.onScroll());
    expect(result.current.atBottom).toBe(false);

    act(() => result.current.scrollToBottom());

    expect(el.scrollTop).toBe(1000);
    expect(result.current.atBottom).toBe(true);
  });

  it("does nothing at all without an element to scroll", () => {
    const { result } = renderHook(() => useAutoScroll<HTMLElement>());

    // Both run before the first render attaches the ref; neither may throw.
    act(() => result.current.onScroll());
    act(() => result.current.scrollToBottom());

    expect(result.current.atBottom).toBe(true);
  });
});
