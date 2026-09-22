import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import { useShortcuts } from "./use-shortcuts";

function press(key: string, init: KeyboardEventInit = {}, target?: HTMLElement) {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, ...init });
  (target ?? window).dispatchEvent(event);
  return event;
}

describe("useShortcuts", () => {
  it("opens the search and the new conversation on the modifier keys", () => {
    const onSearch = vitest.fn();
    const onNew = vitest.fn();
    renderHook(() => useShortcuts({ onSearch, onNew }));

    press("k", { metaKey: true });
    press("n", { ctrlKey: true });

    // Either modifier, because the same person uses both platforms.
    expect(onSearch).toHaveBeenCalledOnce();
    expect(onNew).toHaveBeenCalledOnce();
  });

  it("leaves the key alone when the caller has nothing to do with it", () => {
    renderHook(() => useShortcuts({}));

    // Unhandled means the browser still gets it: ⌘N opens a window, and claiming the
    // key only to drop it would break that for nothing.
    expect(press("k", { metaKey: true }).defaultPrevented).toBe(false);
  });

  it("ignores the letter without a modifier, which is someone typing", () => {
    const onNew = vitest.fn();
    renderHook(() => useShortcuts({ onNew }));

    press("n");

    expect(onNew).not.toHaveBeenCalled();
  });

  it("closes on Escape", () => {
    const onEscape = vitest.fn();
    renderHook(() => useShortcuts({ onEscape }));

    press("Escape");

    expect(onEscape).toHaveBeenCalledOnce();
  });

  it("leaves Escape to the field when one has the cursor", () => {
    const onEscape = vitest.fn();
    renderHook(() => useShortcuts({ onEscape }));
    const input = document.createElement("input");
    document.body.append(input);

    press("Escape", {}, input);

    // A rename in progress cancels in the field. Closing the panel around it would throw
    // away the edit as a side effect of trying to abandon it.
    expect(onEscape).not.toHaveBeenCalled();
    input.remove();
  });

  it("stops listening once the screen is gone", () => {
    const onSearch = vitest.fn();
    const { unmount } = renderHook(() => useShortcuts({ onSearch }));

    unmount();
    press("k", { metaKey: true });

    expect(onSearch).not.toHaveBeenCalled();
  });
});
