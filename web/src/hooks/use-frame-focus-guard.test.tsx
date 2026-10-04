import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useRef, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { wait } from "../test/canvas-hook";
import { GRABS_MAX, OFFERED, useFrameFocusGuard } from "./use-frame-focus-guard";

beforeEach(() => {
  vitest.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});

afterEach(() => {
  cleanup();
  vitest.useRealTimers();
  vitest.restoreAllMocks();
});

type Shown = {
  /** Tells one frame from the next. */
  n?: number;
  /** The field the person writes in: there, there and not to be written in, or not there. */
  field?: "there" | "locked" | "gone";
  /** The app takes the page out when it is told the page goes on taking the keyboard. */
  stops?: boolean;
  onGrabbing?: () => void;
};

/** An app with a field to write in and a button, beside a page in a frame the guard watches. */
function App({ n = 0, field = "there", stops = false, onGrabbing }: Shown) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [stopped, setStopped] = useState(false);
  const box = useFrameFocusGuard(frame, () => {
    onGrabbing?.();
    if (stops) setStopped(true);
  });
  return (
    <>
      {field !== "gone" && <textarea aria-label="message" disabled={field === "locked"} />}
      <button type="button">knob</button>
      {!stopped && (
        <div ref={box} data-testid="box">
          <iframe key={n} ref={frame} title="page" />
        </div>
      )}
    </>
  );
}

function setup(first: Shown = {}) {
  const onGrabbing = vitest.fn();
  const view = render(<App onGrabbing={onGrabbing} {...first} />);
  const show = (now: Shown) => view.rerender(<App onGrabbing={onGrabbing} {...first} {...now} />);
  return { ...view, onGrabbing, show };
}

const message = () => screen.getByRole<HTMLTextAreaElement>("textbox");
const knob = () => screen.getByRole<HTMLButtonElement>("button");
const box = () => screen.getByTestId("box");
const page = () => screen.getByTitle<HTMLIFrameElement>("page");
const holder = () => document.activeElement;

/** The page takes the keyboard: its frame has the focus, and the app's window is told it lost it. */
function grab() {
  act(() => {
    page().focus();
    fireEvent.blur(window);
  });
}

describe("the keyboard a page took unasked", () => {
  it("goes back to the element it was taken from, in the next task and without a scroll", () => {
    setup();
    message().focus();
    const focused = vitest.spyOn(message(), "focus");

    grab();
    // A browser ignores a focus set while it still tells of the blur.
    expect(holder()).toBe(page());
    expect(focused).not.toHaveBeenCalled();

    wait(0);
    expect(holder()).toBe(message());
    expect(focused.mock.calls).toEqual([[{ preventScroll: true }]]);
  });

  it("is taken off the frame when nothing held it", () => {
    setup();

    grab();
    wait(0);

    expect(holder()).toBe(document.body);
  });

  it("is taken off the frame when what held it is gone by then", () => {
    const { show } = setup();
    message().focus();

    grab();
    show({ field: "gone" });
    wait(0);

    expect(holder()).toBe(document.body);
  });

  it("is taken off the frame when what held it can no longer have it", () => {
    const { show } = setup();
    message().focus();

    grab();
    show({ field: "locked" });
    wait(0);

    expect(holder()).toBe(document.body);
  });

  it("does not go to an element the focus had left before the page took it", () => {
    setup();
    message().focus();
    message().blur();
    wait(0);
    const focused = vitest.spyOn(message(), "focus");

    grab();
    wait(0);

    expect(holder()).toBe(document.body);
    expect(focused).not.toHaveBeenCalled();
  });

  it("is not handed to the frame it is being taken from", () => {
    setup();
    // The person had the page, and the page let the keyboard go.
    fireEvent.pointerMove(box());
    grab();
    page().blur();
    fireEvent.pointerMove(message());
    const handed = vitest.spyOn(page(), "focus");

    // It takes the keyboard again before the task is over.
    grab();
    wait(0);

    expect(handed).not.toHaveBeenCalledWith({ preventScroll: true });
    expect(holder()).toBe(document.body);
  });

  it("is given back once the page is out, where the app took it out for this", () => {
    setup({ stops: true });
    message().focus();

    for (let take = 0; take < GRABS_MAX; take++) {
      grab();
      wait(0);
    }

    expect(screen.queryByTitle("page")).toBeNull();
    expect(holder()).toBe(message());
  });

  it("is none of the guard's business when the window loses the focus to something else", () => {
    const { onGrabbing } = setup();
    message().focus();
    const focused = vitest.spyOn(message(), "focus");

    // The person goes to another window and comes back, more often than a page may take the keyboard.
    for (let away = 0; away < GRABS_MAX * 2; away++) {
      fireEvent.blur(window);
      wait(0);
    }

    expect(onGrabbing).not.toHaveBeenCalled();
    expect(focused).not.toHaveBeenCalled();
    expect(holder()).toBe(message());
  });
});

describe("the keyboard the person offers the page", () => {
  it.each(["pointerMove", "pointerDown", "wheel"] as const)("stays with the page after a %s over the frame's box", (over) => {
    const { onGrabbing } = setup();
    message().focus();

    fireEvent[over](box());
    grab();
    wait(0);

    expect(holder()).toBe(page());
    expect(onGrabbing).not.toHaveBeenCalled();
  });

  it("stays with the page after a pointer over the frame itself, as a drag begun in the app sends it", () => {
    setup();
    message().focus();

    fireEvent.pointerMove(page());
    grab();
    wait(0);

    expect(holder()).toBe(page());
  });

  it("stays with the page after Tab", () => {
    const { onGrabbing } = setup();
    message().focus();

    fireEvent.keyDown(message(), { key: "Tab" });
    grab();
    wait(0);

    expect(holder()).toBe(page());
    expect(onGrabbing).not.toHaveBeenCalled();
  });

  it("is marked on the box, which is what lets the pointer through to the page, while the offer stands", () => {
    setup();
    expect(box().hasAttribute(OFFERED)).toBe(false);

    fireEvent.pointerMove(box());
    expect(box().hasAttribute(OFFERED)).toBe(true);
    expect(OFFERED).toBe("data-offered");

    fireEvent.pointerMove(knob());
    expect(box().hasAttribute(OFFERED)).toBe(false);

    fireEvent.keyDown(knob(), { key: "Tab" });
    expect(box().hasAttribute(OFFERED)).toBe(true);
  });

  it.each(["pointerMove", "pointerDown", "wheel"] as const)("is taken back by a %s anywhere else", (elsewhere) => {
    setup();
    message().focus();
    fireEvent.pointerMove(box());

    fireEvent[elsewhere](knob());
    expect(box().hasAttribute(OFFERED)).toBe(false);
    grab();
    wait(0);

    expect(holder()).toBe(message());
  });

  it.each(["a", "Enter", "ArrowRight", "Shift"])("is taken back by the key %s pressed in the app", (key) => {
    setup();
    message().focus();
    fireEvent.pointerMove(box());

    fireEvent.keyDown(message(), { key });
    expect(box().hasAttribute(OFFERED)).toBe(false);
    grab();
    wait(0);

    expect(holder()).toBe(message());
  });

  it("is taken back when Tab brings the focus to one of the app's controls, not to the page", () => {
    setup();
    message().focus();

    fireEvent.keyDown(message(), { key: "Tab" });
    knob().focus();
    expect(box().hasAttribute(OFFERED)).toBe(false);
    grab();
    wait(0);

    expect(holder()).toBe(knob());
  });
});

describe("what the app's own handlers keep to themselves", () => {
  /** A handler of the app's that lets nothing of `type` on `element` go further up. */
  const keep = (element: Element, type: string) => element.addEventListener(type, (event) => event.stopPropagation());

  it("is seen all the same: a pointer over the box", () => {
    setup();
    keep(box(), "pointermove");

    fireEvent.pointerMove(box());

    expect(box().hasAttribute(OFFERED)).toBe(true);
  });

  it("is seen all the same: a key pressed in the app", () => {
    setup();
    keep(message(), "keydown");
    fireEvent.pointerMove(box());

    fireEvent.keyDown(message(), { key: "a" });

    expect(box().hasAttribute(OFFERED)).toBe(false);
  });

  it("is seen all the same: the focus arriving on a control", () => {
    setup();
    keep(knob(), "focusin");
    fireEvent.keyDown(message(), { key: "Tab" });

    knob().focus();

    expect(box().hasAttribute(OFFERED)).toBe(false);
  });

  it("is seen all the same: the focus leaving the element the page took it from", () => {
    setup();
    keep(message(), "focusout");
    message().focus();

    grab();
    wait(0);

    expect(holder()).toBe(message());
  });
});

describe("a page that goes on taking the keyboard", () => {
  it("is reported the fifth time it does, and not before", () => {
    const { onGrabbing } = setup();
    message().focus();
    expect(GRABS_MAX).toBe(5);

    for (let take = 1; take < GRABS_MAX; take++) {
      grab();
      wait(0);
      expect(holder()).toBe(message());
    }
    expect(onGrabbing).not.toHaveBeenCalled();

    grab();
    expect(onGrabbing).toHaveBeenCalledTimes(1);
  });

  it("is reported again each time it does after that, where the app left the page up", () => {
    const { onGrabbing } = setup();
    message().focus();
    for (let take = 0; take < GRABS_MAX; take++) {
      grab();
      wait(0);
    }
    expect(onGrabbing).toHaveBeenCalledTimes(1);

    grab();
    wait(0);
    grab();

    expect(onGrabbing).toHaveBeenCalledTimes(3);
    wait(0);
    expect(holder()).toBe(message());
  });

  it("took it once when the app is told of it more than once before the keyboard is back", () => {
    const { onGrabbing } = setup();
    message().focus();

    for (let take = 1; take < GRABS_MAX; take++) {
      grab();
      fireEvent.blur(window);
      fireEvent.blur(window);
      wait(0);
    }
    expect(onGrabbing).not.toHaveBeenCalled();
    expect(holder()).toBe(message());

    grab();
    expect(onGrabbing).toHaveBeenCalledTimes(1);
  });

  it("is never reported for the keyboard the person gave it, however often", () => {
    const { onGrabbing } = setup();

    for (let round = 0; round < GRABS_MAX * 2; round++) {
      message().focus();
      fireEvent.pointerMove(box());
      grab();
      wait(0);
      expect(holder()).toBe(page());
    }
    expect(onGrabbing).not.toHaveBeenCalled();

    // What it was given does not count against it afterwards either.
    message().focus();
    fireEvent.pointerMove(message());
    for (let take = 1; take < GRABS_MAX; take++) {
      grab();
      wait(0);
    }
    expect(onGrabbing).not.toHaveBeenCalled();
  });

  it("has nothing against it in the frame that replaces it", () => {
    const { onGrabbing, show } = setup();
    message().focus();
    for (let take = 1; take < GRABS_MAX; take++) {
      grab();
      wait(0);
    }

    show({ n: 1 });
    for (let take = 1; take < GRABS_MAX; take++) {
      grab();
      wait(0);
    }
    expect(onGrabbing).not.toHaveBeenCalled();

    grab();
    expect(onGrabbing).toHaveBeenCalledTimes(1);
  });

  it("is reported to whoever asks now, not to whoever asked when the guard was put up", () => {
    const { onGrabbing, show } = setup();
    const asksNow = vitest.fn();
    show({ onGrabbing: asksNow });

    for (let take = 0; take < GRABS_MAX; take++) {
      grab();
      wait(0);
    }

    expect(asksNow).toHaveBeenCalledTimes(1);
    expect(onGrabbing).not.toHaveBeenCalled();
  });
});

describe("a guard that is put up", () => {
  it("holds no scroll back: it tells the browser it only listens to the pointer", () => {
    const put = vitest.spyOn(document, "addEventListener");

    setup();

    const passive = (type: string) =>
      put.mock.calls
        .filter(([told]) => told === type)
        .map(([, , options]) => typeof options === "object" && options.passive === true);
    expect(["pointermove", "pointerdown", "wheel"].map(passive)).toEqual([[true], [true], [true]]);
  });
});

describe("a guard that is taken down", () => {
  it("leaves no timer running, whatever it was in the middle of", () => {
    const { unmount } = setup();
    // The focus left two elements in one task, and the page took it from the second. The events
    // alone are given: jsdom sets a timer of its own for each focus it really moves.
    fireEvent.focusOut(message());
    fireEvent.focusOut(knob());
    vitest.spyOn(document, "activeElement", "get").mockReturnValue(page());
    fireEvent.blur(window);
    // One to forget what the focus left, one to give the keyboard back.
    expect(vitest.getTimerCount()).toBe(2);

    unmount();

    expect(vitest.getTimerCount()).toBe(0);
  });

  it("takes every listener it put up away again", () => {
    const WATCHED = ["pointermove", "pointerdown", "wheel", "keydown", "focusin", "focusout", "blur"];
    type Call = [type: string, listener: unknown, options?: boolean | { capture?: boolean }];
    const told = (calls: unknown[][]) =>
      (calls as Call[])
        .filter(([type]) => WATCHED.includes(type))
        .map(([type, listener, options]) => ({
          type,
          listener,
          capture: typeof options === "boolean" ? options : options?.capture === true,
        }));
    const put = { document: vitest.spyOn(document, "addEventListener"), window: vitest.spyOn(window, "addEventListener") };
    const taken = {
      document: vitest.spyOn(document, "removeEventListener"),
      window: vitest.spyOn(window, "removeEventListener"),
    };

    const { unmount } = setup();
    const onDocument = told(put.document.mock.calls);
    const onWindow = told(put.window.mock.calls);
    expect(onDocument.map((one) => `${one.type} ${one.capture}`)).toEqual([
      "pointermove true",
      "pointerdown true",
      "wheel true",
      "keydown true",
      "focusin true",
      "focusout true",
    ]);
    expect(onWindow.map((one) => `${one.type} ${one.capture}`)).toEqual(["blur false"]);
    expect(told(taken.document.mock.calls)).toEqual([]);

    unmount();

    expect(told(taken.document.mock.calls)).toEqual(onDocument);
    expect(told(taken.window.mock.calls)).toEqual(onWindow);
  });
});
