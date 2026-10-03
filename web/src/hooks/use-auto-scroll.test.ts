import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAutoScroll } from "./use-auto-scroll";

/** The size observer jsdom lacks: it keeps the callback so a case can say the content grew. */
class FakeResizeObserver {
  static latest: FakeResizeObserver | null = null;
  constructor(readonly callback: () => void) {
    FakeResizeObserver.latest = this;
  }
  observe() {}
  disconnect() {}
}

type Geometry = { scrollHeight: number; clientHeight: number; scrollTop: number };

/** jsdom lays nothing out, so the element reports the geometry each case is about; a case
 *  moves the element by assigning to the same fields. */
function element(geometry: Geometry) {
  return { ...geometry } as unknown as HTMLElement & Geometry;
}

describe("useAutoScroll", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    FakeResizeObserver.latest = null;
  });

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

  it("stays pinned when its own scroll is reported after the content grew again, and lets go once the reader moves up", () => {
    const { result } = renderHook(() => useAutoScroll<HTMLElement>());
    const el = element({ scrollHeight: 1000, clientHeight: 400, scrollTop: 560 });
    result.current.ref.current = el;
    act(() => result.current.onScroll());
    expect(result.current.atBottom).toBe(true);

    // A reply that arrives in a burst: the browser reports the jump the hook made a frame later,
    // against a taller element, so the gap reads 300 although the reader never touched anything.
    el.scrollHeight = 1300;
    el.scrollTop = 600;
    act(() => result.current.onScroll());
    expect(result.current.atBottom).toBe(true);

    // The same far-off reading with the position going up is the reader leaving.
    el.scrollTop = 500;
    act(() => result.current.onScroll());
    expect(result.current.atBottom).toBe(false);
  });

  it("stays pinned when the report of its own jump finds the element exactly where it left it", () => {
    const { result } = renderHook(() => useAutoScroll<HTMLElement>());
    const el = element({ scrollHeight: 1000, clientHeight: 400, scrollTop: 0 });
    result.current.ref.current = el;
    act(() => result.current.scrollToBottom());

    // The reply grew again before the browser reported the jump: the same position, a far-off bottom.
    el.scrollHeight = 2000;
    act(() => result.current.onScroll());

    expect(result.current.atBottom).toBe(true);
  });

  it("counts the jump its size observer makes as where the element was left", () => {
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    const { result, rerender } = renderHook(() => useAutoScroll<HTMLElement>());
    const el = Object.assign(element({ scrollHeight: 1000, clientHeight: 400, scrollTop: 0 }), { children: [] });
    result.current.ref.current = el;
    // The effect only finds the element on the render after the ref was filled.
    rerender();

    // The content grew: the observer follows it, then more arrives before the browser reports that.
    FakeResizeObserver.latest?.callback();
    expect(el.scrollTop).toBe(1000);
    el.scrollHeight = 2000;
    act(() => result.current.onScroll());

    expect(result.current.atBottom).toBe(true);
  });

  it("does not take hold again on a scroll down that stops short of the bottom", () => {
    const { result } = renderHook(() => useAutoScroll<HTMLElement>());
    const el = element({ scrollHeight: 1000, clientHeight: 400, scrollTop: 0 });
    result.current.ref.current = el;
    act(() => result.current.onScroll());
    expect(result.current.atBottom).toBe(false);

    // Down, but still 300px from the last line: someone reading their way down is not following.
    el.scrollTop = 300;
    act(() => result.current.onScroll());
    expect(result.current.atBottom).toBe(false);
  });

  it("lets go when the reader scrolls up straight after a jump to the newest", () => {
    const { result } = renderHook(() => useAutoScroll<HTMLElement>());
    const el = element({ scrollHeight: 1000, clientHeight: 400, scrollTop: 0 });
    result.current.ref.current = el;
    act(() => result.current.onScroll());
    act(() => result.current.scrollToBottom());
    expect(result.current.atBottom).toBe(true);

    // Before the jump's own scroll event arrives, the position the reader leaves is the bottom
    // the hook just scrolled to, not wherever the last event happened to see the element.
    el.scrollTop = 400;
    act(() => result.current.onScroll());
    expect(result.current.atBottom).toBe(false);
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
