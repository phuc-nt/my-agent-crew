import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { ATTEST_GRACE_MS, GRABS_MAX } from "../../hooks/use-frame-focus-guard";
import { vi } from "../../i18n/vi";
import { BEHIND_LOOK_MS } from "../../lib/behind-watch";
import {
  boxOf,
  deliver,
  failure,
  flood,
  focusOn,
  frameIn,
  grab,
  hello,
  PRESS,
  setup,
  startFrame,
  stopFrame,
  tell,
  windowOf,
  writing,
} from "../../test/canvas-frame";
import { setVisibility, wait } from "../../test/canvas-hook";
import { RELOAD_DELAY_MS } from "./canvas-frame";

/** Who has the keyboard beside a page in its frame: what the guard, the reporter's port and the
 *  marker come to once they are put together (`use-frame-focus-guard.test.tsx` has the guard alone). */

beforeEach(startFrame);
afterEach(stopFrame);

describe("a page that takes the keyboard", () => {
  it("sits in a box of its own, which a script can put the focus on and Tab passes by", () => {
    const { container } = setup();
    const box = boxOf(frameIn(container));

    expect(box.className).toBe("canvas-frame-box");
    expect(box.getAttribute("tabindex")).toBe("-1");
    expect(box.getAttributeNames().sort()).toEqual(["class", "tabindex"]);
  });

  it("does not keep it: the keyboard is back where the person was writing, and the page stays", () => {
    const { container } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    const field = writing();

    grab(first);
    wait(ATTEST_GRACE_MS);

    expect(document.activeElement).toBe(field);
    expect(frameIn(container)).toBe(first);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("does not keep what it took while the window was behind: the person is back in front, and so is the keyboard", () => {
    const { container } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    const field = writing();

    // The person goes to another window, the page takes the focus, and the person comes back.
    act(() => {
      fireEvent.blur(window);
    });
    act(() => first.focus());
    wait(0);
    act(() => {
      fireEvent.focus(window);
    });
    wait(0);
    wait(ATTEST_GRACE_MS);

    expect(document.activeElement).toBe(field);
    expect(frameIn(container)).toBe(first);
  });

  it("does not keep what it took behind the window when the person comes back by the keyboard alone, and nothing tells the app's window so", () => {
    const { container } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    const field = writing();
    const front = vitest.spyOn(document, "hasFocus").mockReturnValue(false);

    // The person goes to another window, and the page takes the focus there.
    act(() => {
      fireEvent.blur(window);
    });
    act(() => first.focus());
    wait(BEHIND_LOOK_MS * 2);
    expect(document.activeElement).toBe(first);

    // Back in front, it is the page's window that is told so: no focus, no tab shown, no pointer.
    front.mockReturnValue(true);
    wait(BEHIND_LOOK_MS);
    wait(ATTEST_GRACE_MS);

    expect(document.activeElement).toBe(field);
    expect(frameIn(container)).toBe(first);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("is taken out the fifth time it does, the person is told why, and the keyboard is theirs", () => {
    const { container, onMount } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    const field = writing();

    for (let take = 1; take < GRABS_MAX; take++) {
      grab(first);
      wait(ATTEST_GRACE_MS);
    }
    expect(frameIn(container)).toBe(first);
    expect(onMount.mock.calls).toEqual([[1]]);

    grab(first);
    wait(ATTEST_GRACE_MS);
    expect(container.querySelector("iframe")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe(`${vi.canvas.page.grabbing}${vi.canvas.page.reload}`);
    expect(vi.canvas.page.grabbing).toBe("Trang liên tục giành bàn phím nên đã bị dừng.");
    expect(onMount.mock.calls).toEqual([[1], [1]]);
    expect(document.activeElement).toBe(field);
  });

  it("stays stopped for it, whatever else happens, until the person asks for the page again", () => {
    const { container, onMount, show } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    for (let take = 0; take < GRABS_MAX; take++) {
      grab(first);
      wait(ATTEST_GRACE_MS);
    }

    show({ version: 2 });
    wait(RELOAD_DELAY_MS * 3);
    show({ version: 2, connected: false });
    show({ version: 2, connected: true });
    setVisibility("hidden");
    setVisibility("visible");

    expect(container.querySelector("iframe")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe(`${vi.canvas.page.grabbing}${vi.canvas.page.reload}`);
    expect(onMount.mock.calls).toEqual([[1], [1]]);
  });

  it("is put up again when the person asks, with nothing held against the new frame", () => {
    const { container, onMount } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    for (let take = 0; take < GRABS_MAX; take++) {
      grab(first);
      wait(ATTEST_GRACE_MS);
    }

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.page.reload }));
    const again = frameIn(container);
    expect(again).not.toBe(first);
    expect(onMount.mock.calls).toEqual([[1], [1], [1]]);
    expect(screen.getByRole("status").textContent).toBe(vi.canvas.page.loading);
    fireEvent.load(again);

    for (let take = 1; take < GRABS_MAX; take++) {
      grab(again);
      wait(ATTEST_GRACE_MS);
    }
    expect(frameIn(container)).toBe(again);

    grab(again);
    wait(ATTEST_GRACE_MS);
    expect(container.querySelector("iframe")).toBeNull();
  });

  it("keeps the keyboard the person gave it with a press inside it, however often, and a newer version waits for them", () => {
    const { container, show } = setup();
    const first = frameIn(container);
    const told = hello(first);
    fireEvent.load(first);

    for (let round = 0; round <= GRABS_MAX; round++) {
      writing();
      grab(first);
      tell(told);
      wait(ATTEST_GRACE_MS);
      expect(document.activeElement).toBe(first);
    }
    show({ version: 2 });
    wait(RELOAD_DELAY_MS);

    expect(frameIn(container)).toBe(first);
    expect(screen.queryByText(vi.canvas.page.grabbing)).toBeNull();
    expect(screen.queryByText(vi.canvas.page.navigated)).toBeNull();
    expect(screen.getByRole("button", { name: vi.canvas.page.newer })).toBeTruthy();
  });

  it("is not a page the person is using: a newer version replaces it without a button", () => {
    const { container, onMount, show } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    const field = writing();

    show({ version: 2 });
    wait(RELOAD_DELAY_MS - ATTEST_GRACE_MS - 1);
    grab(first);
    wait(ATTEST_GRACE_MS + 1);

    expect(frameIn(container)).not.toBe(first);
    expect(onMount.mock.calls).toEqual([[1], [2]]);
    expect(screen.queryByRole("button", { name: vi.canvas.page.newer })).toBeNull();
    expect(document.activeElement).toBe(field);
  });

  it("drops the button for a newer version when the page is stopped for it", () => {
    const { container, show } = setup();
    const first = frameIn(container);
    const told = hello(first);
    fireEvent.load(first);
    grab(first);
    tell(told);
    show({ version: 2 });
    wait(RELOAD_DELAY_MS);
    expect(screen.getByRole("button", { name: vi.canvas.page.newer })).toBeTruthy();

    // The person goes back to writing, and the page takes the keyboard from them time after time.
    writing();
    for (let take = 0; take < GRABS_MAX; take++) {
      grab(first);
      wait(ATTEST_GRACE_MS);
    }

    expect(screen.queryByRole("button", { name: vi.canvas.page.newer })).toBeNull();
    expect(screen.getByRole("button", { name: vi.canvas.page.reload })).toBeTruthy();
  });
});

describe("the press a page's reporter tells of", () => {
  /** Whether the page that just took the keyboard from `field` is left with it once it was waited on. */
  function keeps(frame: HTMLIFrameElement, field: HTMLElement): boolean {
    wait(ATTEST_GRACE_MS);
    if (document.activeElement === frame) return true;
    expect(document.activeElement).toBe(field);
    return false;
  }

  it("is listened for on the port of the hello that is the first thing a frame says", () => {
    const { container, onError } = setup();
    const first = frameIn(container);
    const field = writing();

    const told = hello(first);
    expect(told.onmessage).toBeTypeOf("function");
    expect(told.close).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();

    grab(first);
    tell(told);
    expect(keeps(first, field)).toBe(true);
  });

  it("is not listened for on a port that comes after the frame said anything, a report or not", () => {
    for (const before of [failure, "anything", { type: "canvas-hello" }]) {
      const { container, unmount } = setup();
      const first = frameIn(container);
      const field = writing();
      deliver(windowOf(first), before);

      const late = hello(first);
      expect(late.onmessage).toBeNull();

      grab(first);
      tell(late);
      expect(keeps(first, field)).toBe(false);
      unmount();
    }
  });

  it("goes on being heard over the first port when a later message carries another", () => {
    const { container } = setup();
    const first = frameIn(container);
    const field = writing();
    const told = hello(first);

    const other = hello(first);
    expect(other.onmessage).toBeNull();
    expect(told.onmessage).toBeTypeOf("function");
    expect(told.close).not.toHaveBeenCalled();

    grab(first);
    tell(told);
    expect(keeps(first, field)).toBe(true);
  });

  it("is not listened for on the port of another window's hello, or of one from nowhere", () => {
    const { container } = setup();
    const first = frameIn(container);
    const field = writing();

    for (const stranger of [hello(first, window), hello(first, null)]) {
      expect(stranger.onmessage).toBeNull();
      grab(first);
      tell(stranger);
      expect(keeps(first, field)).toBe(false);
    }

    // Neither was the frame's first word: the hello of its own still hands the port over.
    const told = hello(first);
    grab(first);
    tell(told);
    expect(keeps(first, field)).toBe(true);
  });

  it("is not listened for on the port of a hello that came under an origin that is not null", () => {
    for (const origin of [window.location.origin, "https://example.com"]) {
      const { container, unmount } = setup();
      const first = frameIn(container);

      expect(hello(first, windowOf(first), origin).onmessage).toBeNull();
      // It came from the frame's own window all the same, and was the first thing it said.
      expect(hello(first).onmessage).toBeNull();
      unmount();
    }
  });

  it("is nothing the page can say to the window: only the port tells of it", () => {
    const { container, onError } = setup();
    const first = frameIn(container);
    const field = writing();
    const told = hello(first);

    grab(first);
    deliver(windowOf(first), PRESS);
    expect(keeps(first, field)).toBe(false);

    // The same words over the port are the reporter's.
    grab(first);
    tell(told);
    expect(keeps(first, field)).toBe(true);
    expect(onError).not.toHaveBeenCalled();
  });

  it("is told by a press alone, whatever else comes over the port", () => {
    const { container, onError } = setup();
    const first = frameIn(container);
    const field = writing();
    const told = hello(first);

    grab(first);
    for (const said of [failure, { type: "canvas-hello" }, "press", null, { press: true }]) tell(told, said);

    expect(keeps(first, field)).toBe(false);
    expect(onError).not.toHaveBeenCalled();
  });

  it("is not one of the fifty messages a frame is heard out on, however often it is told", () => {
    const { container, onError, onSilenced } = setup();
    const first = frameIn(container);
    const told = hello(first);

    for (let press = 0; press < 1000; press++) tell(told);
    expect(onSilenced).not.toHaveBeenCalled();

    // The hello was one of the fifty.
    expect(flood(windowOf(first), 10_000)).toBe(49);
    expect(onError).toHaveBeenCalledTimes(49);
    expect(onSilenced).toHaveBeenCalledTimes(1);
  });

  it("is no longer heard from the port of a frame that was replaced, and that port is closed", () => {
    const { container, show } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    const old = hello(first);
    const heard = old.onmessage;
    show({ version: 2 });
    expect(old.close).not.toHaveBeenCalled();
    wait(RELOAD_DELAY_MS);
    const second = frameIn(container);
    expect(second).not.toBe(first);

    expect(old.close).toHaveBeenCalledTimes(1);
    expect(old.onmessage).toBeNull();

    // What was listening on it says nothing for the new frame either.
    const field = writing();
    grab(second);
    act(() => heard?.({ data: PRESS }));
    expect(keeps(second, field)).toBe(false);

    const told = hello(second);
    grab(second);
    tell(told);
    expect(keeps(second, field)).toBe(true);
    expect(told.close).not.toHaveBeenCalled();
  });

  it("has its port closed when the page is stopped, for another address or for the keyboard", () => {
    const moved = setup();
    const first = frameIn(moved.container);
    const told = hello(first);
    fireEvent.load(first);
    expect(told.close).not.toHaveBeenCalled();
    fireEvent.load(first);

    expect(told.close).toHaveBeenCalledTimes(1);
    expect(told.onmessage).toBeNull();
    moved.unmount();
    expect(told.close).toHaveBeenCalledTimes(1);

    const grabbing = setup();
    const taker = frameIn(grabbing.container);
    const other = hello(taker);
    fireEvent.load(taker);
    writing();
    for (let take = 0; take < GRABS_MAX; take++) {
      expect(other.close).not.toHaveBeenCalled();
      grab(taker);
      wait(ATTEST_GRACE_MS);
    }

    expect(other.close).toHaveBeenCalledTimes(1);
    expect(other.onmessage).toBeNull();
  });

  it("has its port closed when the frame goes, and not while it is only drawn again", () => {
    const { container, show, unmount } = setup();
    const told = hello(frameIn(container));

    show({ version: 1, connected: false });
    show({ version: 2, connected: false });
    expect(told.close).not.toHaveBeenCalled();
    expect(told.onmessage).toBeTypeOf("function");

    unmount();
    expect(told.close).toHaveBeenCalledTimes(1);
    expect(told.onmessage).toBeNull();
  });
});

describe("the page that has the keyboard", () => {
  const marker = () => screen.queryByText(vi.canvas.page.keyboard);

  it("is marked as having it, in words and on its box, and no longer once the keyboard is back in the app", () => {
    const { container } = setup();
    const first = frameIn(container);
    const told = hello(first);
    fireEvent.load(first);
    const field = writing();
    expect(marker()).toBeNull();
    expect(boxOf(first).hasAttribute("data-keyboard")).toBe(false);

    grab(first);
    tell(told);

    expect(vi.canvas.page.keyboard).toBe("Bàn phím đang ở trang");
    expect(screen.getByRole("status")).toBe(marker());
    expect(marker()?.parentElement).toBe(boxOf(first));
    expect(boxOf(first).getAttribute("data-keyboard")).toBe("");
    // The words are put beside the page, which is the frame it was: a new one would start it over.
    expect(frameIn(container)).toBe(first);
    expect(boxOf(first).firstElementChild).toBe(first);

    act(() => field.focus());
    expect(screen.queryByRole("status")).toBeNull();
    expect(boxOf(first).hasAttribute("data-keyboard")).toBe(false);
    expect(frameIn(container)).toBe(first);
  });

  it.each([
    ["the app's window losing the focus", () => fireEvent.blur(window)],
    ["the app's window getting the focus", () => fireEvent.focus(window)],
    ["the focus arriving on an element", () => fireEvent.focusIn(document.body)],
    ["the focus leaving an element", () => fireEvent.focusOut(document.body)],
  ])("is looked for at %s", (_, moves) => {
    const { container } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    const active = vitest.spyOn(document, "activeElement", "get");

    active.mockReturnValue(first);
    expect(marker()).toBeNull();
    moves();
    expect(marker()).not.toBeNull();

    active.mockReturnValue(document.body);
    expect(marker()).not.toBeNull();
    moves();
    expect(marker()).toBeNull();
  });

  describe("behind the app's window, which is told nothing of the focus a page takes there", () => {
    /** The person goes to another window. `front` is what the browser says of where the keys go. */
    function leave() {
      const front = vitest.spyOn(document, "hasFocus").mockReturnValue(false);
      fireEvent.blur(window);
      return front;
    }

    it("is marked within a beat of taking it, and no longer within a beat of letting it go", () => {
      const { container } = setup();
      const first = frameIn(container);
      fireEvent.load(first);
      const active = vitest.spyOn(document, "activeElement", "get");
      leave();

      active.mockReturnValue(first);
      wait(BEHIND_LOOK_MS - 1);
      expect(marker()).toBeNull();
      wait(1);
      expect(marker()).not.toBeNull();
      expect(boxOf(first).getAttribute("data-keyboard")).toBe("");

      active.mockReturnValue(document.body);
      wait(BEHIND_LOOK_MS - 1);
      expect(marker()).not.toBeNull();
      wait(1);
      expect(marker()).toBeNull();
    });

    it("is marked within a beat of the person coming back to it by the keyboard alone", () => {
      const { container } = setup();
      const first = frameIn(container);
      fireEvent.load(first);
      const active = vitest.spyOn(document, "activeElement", "get");
      const front = leave();
      wait(BEHIND_LOOK_MS * 3);

      // The page takes the focus as the person comes back: its window is the one told so.
      active.mockReturnValue(first);
      front.mockReturnValue(true);
      wait(BEHIND_LOOK_MS);

      expect(marker()).not.toBeNull();
    });

    it("is looked for on the beat for the frame that replaced the one on show meanwhile", () => {
      const { container, show } = setup();
      const first = frameIn(container);
      fireEvent.load(first);
      leave();

      show({ version: 2 });
      wait(RELOAD_DELAY_MS);
      const second = frameIn(container);
      expect(second).not.toBe(first);
      // The new page takes the focus as it loads.
      vitest.spyOn(document, "activeElement", "get").mockReturnValue(second);
      wait(BEHIND_LOOK_MS);

      expect(marker()).not.toBeNull();
      expect(marker()?.parentElement).toBe(boxOf(second));
    });

    it("is looked for on the beat only until the window is in front again, and on no beat once the frame is gone", () => {
      const { unmount } = setup();
      expect(vitest.getTimerCount()).toBe(0);

      // One beat for the marker and one for the guard, however often the window says it went behind.
      const front = leave();
      fireEvent.blur(window);
      expect(vitest.getTimerCount()).toBe(2);
      wait(BEHIND_LOOK_MS * 3);
      expect(vitest.getTimerCount()).toBe(2);

      // In front with nothing of the page's holding the focus: the marker has no more to look for.
      front.mockReturnValue(true);
      wait(BEHIND_LOOK_MS);
      expect(vitest.getTimerCount()).toBe(1);

      front.mockReturnValue(false);
      fireEvent.blur(window);
      expect(vitest.getTimerCount()).toBe(2);
      unmount();
      expect(vitest.getTimerCount()).toBe(0);
    });

    it("is marked within a beat of taking it where the frame was put up behind the window, which no blur told of", () => {
      vitest.spyOn(document, "hasFocus").mockReturnValue(false);
      const { container } = setup();
      const first = frameIn(container);
      fireEvent.load(first);

      vitest.spyOn(document, "activeElement", "get").mockReturnValue(first);
      wait(BEHIND_LOOK_MS - 1);
      expect(marker()).toBeNull();
      wait(1);

      expect(marker()).not.toBeNull();
      expect(boxOf(first).getAttribute("data-keyboard")).toBe("");
    });

    it("is looked for on the beat from the time the frame is put up behind the window, until the window is in front again", () => {
      const front = vitest.spyOn(document, "hasFocus").mockReturnValue(false);
      const { unmount } = setup();
      // One beat for the marker and one for the guard.
      expect(vitest.getTimerCount()).toBe(2);
      wait(BEHIND_LOOK_MS * 3);
      expect(vitest.getTimerCount()).toBe(2);

      // In front with nothing of the page's holding the focus: the marker has no more to look for.
      front.mockReturnValue(true);
      wait(BEHIND_LOOK_MS);
      expect(vitest.getTimerCount()).toBe(1);

      unmount();
      expect(vitest.getTimerCount()).toBe(0);
    });
  });

  it("is not marked for a frame that came after the one that had it", () => {
    const { container, show } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    focusOn(first);
    fireEvent.blur(window);
    expect(marker()).not.toBeNull();

    show({ version: 2 });
    wait(RELOAD_DELAY_MS);
    fireEvent.click(screen.getByRole("button", { name: vi.canvas.page.newer }));

    expect(frameIn(container)).not.toBe(first);
    expect(marker()).toBeNull();
    expect(boxOf(frameIn(container)).hasAttribute("data-keyboard")).toBe(false);
  });

  it("leaves none of the listeners the frame put up behind when the frame goes", () => {
    const WATCHED = ["blur", "focus", "focusin", "focusout", "message", "visibilitychange", "pointerdown", "keydown", "online", "offline"];
    const captures = (options: unknown) => options === true || (options as AddEventListenerOptions | undefined)?.capture === true;
    const targets = [window, document];
    const added = targets.map((target) => vitest.spyOn(target, "addEventListener"));
    const removed = targets.map((target) => vitest.spyOn(target, "removeEventListener"));
    const { unmount } = setup();
    const up = added.map((spy) => spy.mock.calls.filter(([type]) => WATCHED.includes(type)));
    expect(up[0].map(([type]) => type)).toEqual(expect.arrayContaining(["blur", "focus", "message"]));
    expect(up[1].map(([type]) => type)).toEqual(expect.arrayContaining(["focusin", "focusout", "visibilitychange"]));

    unmount();

    targets.forEach((_, at) => {
      const left = up[at].filter(
        ([type, listener, options]) =>
          !removed[at].mock.calls.some(([gone, same, how]) => gone === type && same === listener && captures(how) === captures(options)),
      );
      expect(left.map(([type]) => type)).toEqual([]);
    });
  });
});

describe("a stopped page the person asks for again", () => {
  /** A page stopped for moving to another address, and the button that asks for it again. */
  function stopped() {
    const view = setup();
    const first = frameIn(view.container);
    const box = boxOf(first);
    fireEvent.load(first);
    fireEvent.load(first);
    return { ...view, box, button: screen.getByRole("button", { name: vi.canvas.page.reload }) };
  }

  it("is told of in a notice that is no part of the box the frame was in, nor of the next", () => {
    const { container, box, button } = stopped();
    const notice = screen.getByRole("status");

    expect(notice).not.toBe(box);
    expect(box.isConnected).toBe(false);
    expect(notice.className).toBe("notice canvas-frame-note");
    expect(notice.hasAttribute("tabindex")).toBe(false);

    fireEvent.click(button);
    const again = boxOf(frameIn(container));
    expect(notice.isConnected).toBe(false);
    expect(again).not.toBe(notice);
    expect(again).not.toBe(box);
    expect(again.hasAttribute("role")).toBe(false);
  });

  it("has the focus put on the box of the new frame, where the button that was pressed is gone", () => {
    const { container, button } = stopped();
    button.focus();
    const focus = vitest.spyOn(HTMLElement.prototype, "focus");

    fireEvent.click(button);

    const box = boxOf(frameIn(container));
    expect(button.isConnected).toBe(false);
    expect(document.activeElement).toBe(box);
    expect(focus.mock.contexts).toEqual([box]);
    expect(focus.mock.calls).toEqual([[{ preventScroll: true }]]);
  });

  it("leaves the focus with what has it, in a browser whose buttons take none when they are pressed", () => {
    const { container, button } = stopped();
    const field = writing();

    fireEvent.click(button);

    expect(frameIn(container)).toBeTruthy();
    expect(document.activeElement).toBe(field);
  });

  it("has the focus put there once: the frames that follow leave it where the person took it", () => {
    const { container, button, show } = stopped();
    fireEvent.click(button);
    const again = frameIn(container);
    fireEvent.load(again);
    const field = writing();

    show({ version: 2 });
    wait(RELOAD_DELAY_MS);
    expect(frameIn(container)).not.toBe(again);
    expect(document.activeElement).toBe(field);

    show({ version: 2, connected: false });
    show({ version: 2, connected: true });
    expect(document.activeElement).toBe(field);
  });

  it("does not have the focus moved for a frame nobody asked for", () => {
    const { container, show } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    const field = writing();
    const focus = vitest.spyOn(HTMLElement.prototype, "focus");

    show({ version: 2 });
    wait(RELOAD_DELAY_MS);
    show({ version: 2, connected: false });
    show({ version: 2, connected: true });

    expect(frameIn(container)).not.toBe(first);
    expect(focus).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(field);
  });

  it("does not have the focus put on the box of a frame nobody asked for, though nothing else has it", () => {
    const focus = vitest.spyOn(HTMLElement.prototype, "focus");
    const { container, show } = setup();
    const first = frameIn(container);
    fireEvent.load(first);
    expect(document.activeElement).toBe(document.body);

    show({ version: 2 });
    wait(RELOAD_DELAY_MS);

    expect(frameIn(container)).not.toBe(first);
    expect(focus).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(document.body);
  });

  it("has the focus put there once, though nothing has it when the frame that follows comes", () => {
    const { container, button, show } = stopped();
    fireEvent.click(button);
    const again = frameIn(container);
    fireEvent.load(again);
    const box = boxOf(again);
    expect(document.activeElement).toBe(box);
    // The person lets the focus go: nothing in the app holds it.
    act(() => box.blur());
    expect(document.activeElement).toBe(document.body);

    show({ version: 2 });
    wait(RELOAD_DELAY_MS);

    expect(frameIn(container)).not.toBe(again);
    expect(document.activeElement).toBe(document.body);
  });
});
