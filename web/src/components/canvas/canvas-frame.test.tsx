import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { artifactApi } from "../../api/artifact-client";
import { vi } from "../../i18n/vi";
import { FRAME_REPORTS_MAX, type FrameError } from "../../lib/frame-messages";
import { deliver, failure, flood, focusOn, frameIn, PRESS, setup, startFrame, stopFrame, windowOf } from "../../test/canvas-frame";
import { setVisibility, wait } from "../../test/canvas-hook";
import { CanvasFrame, RELOAD_DELAY_MS } from "./canvas-frame";

/** The page in its frame: what is put up and when, and what the page says. Who has the keyboard
 *  beside it is in `canvas-frame-keyboard.test.tsx`. */

beforeEach(startFrame);
afterEach(stopFrame);

const unreached = {
  type: "canvas-error",
  message: "failed to load https://cdn.test/a.png",
  source: "https://cdn.test/a.png",
  line: 0,
  column: 0,
};

function goOffline(offline: boolean) {
  vitest.spyOn(navigator, "onLine", "get").mockReturnValue(!offline);
  act(() => {
    window.dispatchEvent(new Event(offline ? "offline" : "online"));
  });
}

describe("the page of a canvas, in its frame", () => {
  it("runs the page in a frame that has a script and nothing of the app", () => {
    const { container } = setup();
    const frame = frameIn(container);

    expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
    expect(frame.getAttribute("allow")).toBe("fullscreen");
    expect(frame.getAttribute("referrerpolicy")).toBe("no-referrer");
    expect(frame.getAttribute("title")).toBe("Trang chủ");
  });

  it("loads the newest version from the render route, with no version in the address", () => {
    const { container } = setup({ version: 7 });

    expect(frameIn(container).getAttribute("src")).toBe(artifactApi.renderUrl("a1"));
    expect(frameIn(container).getAttribute("src")).toBe("/api/artifacts/a1/render");
  });

  it("says it is loading until the page has loaded once", () => {
    const { container } = setup();

    expect(screen.getByRole("status").textContent).toBe(vi.canvas.page.loading);
    fireEvent.load(frameIn(container));

    expect(screen.queryByRole("status")).toBeNull();
    expect(frameIn(container)).toBeTruthy();
  });

  it("tells the panel which version it put up, when it does", () => {
    const { onMount } = setup({ version: 4 });

    expect(onMount.mock.calls).toEqual([[4]]);
  });
});

describe("a newer version of the page", () => {
  it("replaces the frame with a new one a second after the version last changed", () => {
    const { container, onMount, show } = setup();
    const first = frameIn(container);
    fireEvent.load(first);

    show({ version: 2 });
    wait(RELOAD_DELAY_MS - 1);
    expect(frameIn(container)).toBe(first);
    expect(onMount.mock.calls).toEqual([[1]]);

    wait(1);
    const second = frameIn(container);
    expect(RELOAD_DELAY_MS).toBe(1000);
    expect(second).not.toBe(first);
    expect(second.getAttribute("src")).toBe(first.getAttribute("src"));
    expect(onMount.mock.calls).toEqual([[1], [2]]);
    expect(screen.getByRole("status").textContent).toBe(vi.canvas.page.loading);
  });

  it("waits for the version to stand still, then puts up the last one", () => {
    const { container, onMount, show } = setup();
    const first = frameIn(container);
    fireEvent.load(first);

    show({ version: 2 });
    wait(600);
    show({ version: 3 });
    wait(600);
    expect(frameIn(container)).toBe(first);

    wait(400);
    expect(frameIn(container)).not.toBe(first);
    expect(onMount.mock.calls).toEqual([[1], [3]]);
  });

  it("keeps the frame and offers the new version by a button while the person has its focus", () => {
    const { container, onMount, show } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    focusOn(first);

    show({ version: 2 });
    wait(RELOAD_DELAY_MS);
    expect(frameIn(container)).toBe(first);
    expect(onMount.mock.calls).toEqual([[1]]);

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.page.newer }));
    expect(frameIn(container)).not.toBe(first);
    expect(onMount.mock.calls).toEqual([[1], [2]]);
    expect(screen.queryByRole("button", { name: vi.canvas.page.newer })).toBeNull();
  });

  it("offers the version that stands by the time the button is pressed", () => {
    const { container, onMount, show } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    focusOn(first);

    show({ version: 2 });
    wait(RELOAD_DELAY_MS);
    show({ version: 3 });
    fireEvent.click(screen.getByRole("button", { name: vi.canvas.page.newer }));

    expect(onMount.mock.calls).toEqual([[1], [3]]);
  });

  it("does not interrupt a page that has no newer version with a button", () => {
    const { container, show } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    focusOn(first);

    show({ version: 1 });
    wait(RELOAD_DELAY_MS * 3);

    expect(screen.queryByRole("button", { name: vi.canvas.page.newer })).toBeNull();
    expect(frameIn(container)).toBe(first);
  });

  it("waits for the tab to come back when it is hidden, then puts the page up at once", () => {
    const { container, onMount, show } = setup();
    const first = frameIn(container);
    fireEvent.load(first);

    setVisibility("hidden");
    show({ version: 2 });
    wait(RELOAD_DELAY_MS * 5);
    expect(frameIn(container)).toBe(first);
    expect(onMount.mock.calls).toEqual([[1]]);

    setVisibility("visible");
    expect(frameIn(container)).not.toBe(first);
    expect(onMount.mock.calls).toEqual([[1], [2]]);
  });

  it("does not put a page up again when the tab comes back and the version is the same", () => {
    const { container } = setup();
    const first = frameIn(container);
    fireEvent.load(first);

    setVisibility("hidden");
    setVisibility("visible");

    expect(frameIn(container)).toBe(first);
  });
});

describe("the live stream", () => {
  it("puts the page up again each time it comes back after a drop, and not the first time it is up", () => {
    const { container, onMount, show } = setup({ connected: true });
    const first = frameIn(container);
    fireEvent.load(first);
    expect(onMount.mock.calls).toEqual([[1]]);

    show({ connected: false });
    expect(frameIn(container)).toBe(first);

    show({ connected: true });
    const second = frameIn(container);
    expect(second).not.toBe(first);
    expect(onMount.mock.calls).toEqual([[1], [1]]);

    show({ connected: false });
    show({ connected: true });
    expect(frameIn(container)).not.toBe(second);
    expect(onMount.mock.calls).toEqual([[1], [1], [1]]);
  });

  it("puts up the newest version when it comes back, not the one it showed", () => {
    const { onMount, show } = setup({ connected: true });

    show({ connected: false, version: 5 });
    show({ connected: true, version: 5 });

    expect(onMount.mock.calls).toEqual([[1], [5]]);
  });

  it("does not put the page up again for a stream that was never up", () => {
    const { container, show } = setup({ connected: false });
    const first = frameIn(container);

    show({ connected: true });

    expect(frameIn(container)).toBe(first);
  });
});

describe("a page that moves to another address", () => {
  it("is taken out when it loads a second time, and the person is told", () => {
    const { container, onMount } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    expect(onMount.mock.calls).toEqual([[1]]);

    fireEvent.load(first);

    expect(container.querySelector("iframe")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe(`${vi.canvas.page.navigated}${vi.canvas.page.reload}`);
    expect(screen.getByRole("button", { name: vi.canvas.page.reload })).toBeTruthy();
    expect(onMount.mock.calls).toEqual([[1], [1]]);
  });

  it("is not taken out for loading once, however long that takes", () => {
    const { container } = setup();

    wait(60_000);
    fireEvent.load(frameIn(container));
    wait(60_000);

    expect(frameIn(container)).toBeTruthy();
  });

  it("takes a late load of the frame it replaced for no load of its own", () => {
    const { container, show } = setup();
    // Still loading, as a page waiting for a file from elsewhere is, when a newer version comes.
    const first = frameIn(container);
    show({ version: 2 });

    // Its load arrives once the new frame is asked for and before it is in the page.
    act(() => {
      vitest.advanceTimersByTime(RELOAD_DELAY_MS);
      fireEvent.load(first);
    });
    const second = frameIn(container);
    expect(second).not.toBe(first);
    expect(screen.getByRole("status").textContent).toBe(vi.canvas.page.loading);

    fireEvent.load(second);
    expect(frameIn(container)).toBe(second);
    expect(screen.queryByRole("status")).toBeNull();

    fireEvent.load(second);
    expect(container.querySelector("iframe")).toBeNull();
    expect(screen.getByRole("button", { name: vi.canvas.page.reload })).toBeTruthy();
  });

  it("stays stopped, whatever else happens, until the person asks for it again", () => {
    const { container, onMount, show } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    fireEvent.load(first);

    show({ version: 2 });
    wait(RELOAD_DELAY_MS * 3);
    show({ version: 2, connected: false });
    show({ version: 2, connected: true });
    setVisibility("hidden");
    setVisibility("visible");

    expect(container.querySelector("iframe")).toBeNull();
    expect(onMount.mock.calls).toEqual([[1], [1]]);
  });

  it("puts the newest version up when the person asks, and runs it like any other page", () => {
    const { container, onMount, show } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    fireEvent.load(first);
    show({ version: 2 });

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.page.reload }));
    const again = frameIn(container);

    expect(again).not.toBe(first);
    expect(onMount.mock.calls).toEqual([[1], [1], [2]]);
    expect(screen.getByRole("status").textContent).toBe(vi.canvas.page.loading);
    fireEvent.load(again);
    expect(screen.queryByRole("status")).toBeNull();
    fireEvent.load(again);
    expect(container.querySelector("iframe")).toBeNull();
  });

  it("is told to the panel under the version that was up, though a newer one was waiting its second", () => {
    const { container, onMount, show } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    show({ version: 2 });

    fireEvent.load(first);

    expect(container.querySelector("iframe")).toBeNull();
    expect(onMount.mock.calls).toEqual([[1], [1]]);
  });

  it("drops the button for a newer version when the page is stopped", () => {
    const { container, show } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    focusOn(first);
    show({ version: 2 });
    wait(RELOAD_DELAY_MS);
    expect(screen.getByRole("button", { name: vi.canvas.page.newer })).toBeTruthy();

    fireEvent.load(first);

    expect(screen.queryByRole("button", { name: vi.canvas.page.newer })).toBeNull();
    expect(screen.getByRole("button", { name: vi.canvas.page.reload })).toBeTruthy();
  });
});

describe("what the page reports", () => {
  it("passes on a report from the page's own window", () => {
    const { container, onError } = setup();

    deliver(windowOf(frameIn(container)), failure);

    expect(onError.mock.calls).toEqual([[{ message: "boom", source: "page.html", line: 3, column: 7 }]]);
  });

  it("takes nothing from another window, from nowhere, or from an origin that is not null", () => {
    const { container, onError } = setup();
    const own = windowOf(frameIn(container));

    deliver(window, failure);
    deliver(null, failure);
    deliver(own, failure, window.location.origin);
    deliver(own, failure, "https://example.com");
    deliver(own, { ...failure, type: "canvas-note" });
    deliver(own, { ...failure, message: 42 });
    deliver(own, "canvas-error");

    expect(onError).not.toHaveBeenCalled();
  });

  it("takes nothing from a page that was taken out", () => {
    const { container, onError } = setup();
    const first = frameIn(container);
    const own = windowOf(first);
    fireEvent.load(first);
    fireEvent.load(first);

    deliver(own, failure);

    expect(onError).not.toHaveBeenCalled();
  });

  it("takes a report from the new frame, and none from the one it replaced", () => {
    const { container, onError, show } = setup();
    const first = frameIn(container);
    const old = windowOf(first);
    fireEvent.load(first);
    show({ version: 2 });
    wait(RELOAD_DELAY_MS);
    const second = frameIn(container);

    deliver(old, failure);
    expect(onError).not.toHaveBeenCalled();

    deliver(windowOf(second), failure);
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it("hears fifty messages of a page that sends ten thousand, and reads nothing of the rest", () => {
    const { container, onError } = setup();

    const read = flood(windowOf(frameIn(container)), 10_000);

    expect(FRAME_REPORTS_MAX).toBe(50);
    expect(onError).toHaveBeenCalledTimes(50);
    expect(read).toBe(50);
  });

  it("counts a message that is no report against the page too, and so reads fifty of those at most", () => {
    const { container, onError } = setup();
    const own = windowOf(frameIn(container));

    expect(flood(own, 10_000, "not a report")).toBe(50);
    deliver(own, failure);

    expect(onError).not.toHaveBeenCalled();
  });

  it("hears a new frame out on fifty of its own, whatever the one before it sent", () => {
    const { container, onError, show } = setup();
    flood(windowOf(frameIn(container)), 10_000);
    show({ version: 2 });
    wait(RELOAD_DELAY_MS);

    expect(flood(windowOf(frameIn(container)), 10_000)).toBe(50);
    expect(onError).toHaveBeenCalledTimes(100);
  });

  it("does not count what another window sends against the page", () => {
    const { container, onError } = setup();

    expect(flood(window, 10_000)).toBe(0);
    expect(flood(null, 10_000)).toBe(0);
    flood(windowOf(frameIn(container)), 10_000);

    expect(onError).toHaveBeenCalledTimes(50);
  });

  it("tells the panel when it has heard the last of the fifty, reports or not, and not before", () => {
    for (const said of [failure, "not a report", PRESS]) {
      const { container, onSilenced, unmount } = setup();
      const own = windowOf(frameIn(container));

      flood(own, FRAME_REPORTS_MAX - 1, said);
      expect(onSilenced).not.toHaveBeenCalled();

      deliver(own, said);
      expect(onSilenced).toHaveBeenCalledTimes(1);

      flood(own, 10_000, said);
      expect(onSilenced).toHaveBeenCalledTimes(1);
      unmount();
    }
  });

  it("tells the panel of the fiftieth report and that it was the last one heard, both", () => {
    const { container, onError, onSilenced } = setup();

    flood(windowOf(frameIn(container)), FRAME_REPORTS_MAX);

    expect(onError).toHaveBeenCalledTimes(50);
    expect(onSilenced).toHaveBeenCalledTimes(1);
  });

  it("tells the panel so for each frame, which is heard out on fifty of its own", () => {
    const { container, onSilenced, show } = setup();
    flood(windowOf(frameIn(container)), 10_000);
    show({ version: 2 });
    wait(RELOAD_DELAY_MS);
    const second = windowOf(frameIn(container));

    flood(second, FRAME_REPORTS_MAX - 1);
    expect(onSilenced).toHaveBeenCalledTimes(1);
    deliver(second, failure);
    expect(onSilenced).toHaveBeenCalledTimes(2);
  });

  it("does not tell the panel so for what another window sends", () => {
    const { onSilenced } = setup();

    flood(window, 10_000);
    flood(null, 10_000);

    expect(onSilenced).not.toHaveBeenCalled();
  });

  it("tells the panel's newest listener alone that the page is no longer heard", () => {
    const [early, late, other] = [vitest.fn(), vitest.fn(), vitest.fn()];
    const element = (onSilenced: () => void) => (
      <CanvasFrame artifactId="a1" title="Trang chủ" version={1} connected onMount={other} onError={other} onSilenced={onSilenced} />
    );
    const { container, rerender } = render(element(early));
    rerender(element(late));

    flood(windowOf(frameIn(container)), FRAME_REPORTS_MAX);

    expect(early).not.toHaveBeenCalled();
    expect(late).toHaveBeenCalledTimes(1);
  });

  it("stops listening when the frame goes", () => {
    const { container, onError, unmount } = setup();
    const own = windowOf(frameIn(container));

    unmount();
    deliver(own, failure);

    expect(onError).not.toHaveBeenCalled();
  });

  it("tells the panel's newest listener alone, once the panel has given it another", () => {
    const [early, late, onMount] = [vitest.fn(), vitest.fn(), vitest.fn()];
    const element = (onError: (error: FrameError) => void) => (
      <CanvasFrame artifactId="a1" title="Trang chủ" version={1} connected onMount={onMount} onError={onError} onSilenced={onMount} />
    );
    const { container, rerender } = render(element(early));
    rerender(element(late));

    deliver(windowOf(frameIn(container)), failure);

    expect(early).not.toHaveBeenCalled();
    expect(late).toHaveBeenCalledTimes(1);
  });

  it("leaves out a file that did not arrive when the device has no network, and keeps every other report", () => {
    const { container, onError } = setup();
    const own = windowOf(frameIn(container));

    goOffline(true);
    deliver(own, unreached);
    expect(onError).not.toHaveBeenCalled();

    deliver(own, failure);
    deliver(own, { ...unreached, line: 4, column: 2 });
    const told = onError.mock.calls.map(([error]) => error.message);
    expect(told).toEqual(["boom", "failed to load https://cdn.test/a.png"]);
  });

  it("lists a file that did not arrive once the network is back", () => {
    const { container, onError } = setup();
    const own = windowOf(frameIn(container));

    goOffline(true);
    goOffline(false);
    deliver(own, unreached);

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith({
      message: "failed to load https://cdn.test/a.png",
      source: "https://cdn.test/a.png",
      line: 0,
      column: 0,
    });
  });
});
