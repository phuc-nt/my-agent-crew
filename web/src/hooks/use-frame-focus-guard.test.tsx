import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useRef, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { BEHIND_LOOK_MS } from "../lib/behind-watch";
import { setVisibility, wait } from "../test/canvas-hook";
import { ATTEST_GRACE_MS, GRABS_MAX, LATE_MS, useFrameFocusGuard } from "./use-frame-focus-guard";

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

/** What the guard on show is told with when the page's reporter says a person pressed inside the page. */
let attest: () => void = () => {};

/** An app with a field to write in and a button, beside a page in a frame the guard watches. */
function App({ n = 0, field = "there", stops = false, onGrabbing }: Shown) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [stopped, setStopped] = useState(false);
  const guard = useFrameFocusGuard(frame, () => {
    onGrabbing?.();
    if (stops) setStopped(true);
  });
  attest = guard.attest;
  return (
    <>
      {field !== "gone" && <textarea aria-label="message" disabled={field === "locked"} />}
      <button type="button">knob</button>
      {!stopped && (
        <div ref={guard.box} data-testid="box">
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

/** The page's reporter tells of a pointer the person pressed inside the page. */
function press() {
  act(() => attest());
}

/** The page takes the keyboard `times` over, and each time is waited on for as long as a page is. */
function takes(times: number) {
  for (let take = 0; take < times; take++) {
    grab();
    wait(ATTEST_GRACE_MS);
  }
}

describe("the keyboard a page took unasked", () => {
  it("goes back to the element it was taken from, once the page was given its time to tell of a press", () => {
    setup();
    message().focus();
    const focused = vitest.spyOn(message(), "focus");

    grab();
    wait(ATTEST_GRACE_MS - 1);
    expect(holder()).toBe(page());
    expect(focused).not.toHaveBeenCalled();

    wait(1);
    expect(holder()).toBe(message());
    // Without a scroll: the field may be out of sight, and the person did not ask to be taken to it.
    expect(focused.mock.calls).toEqual([[{ preventScroll: true }]]);
  });

  it("is waited on for no longer than a tenth of a second, in which the keys go to the page", () => {
    expect(ATTEST_GRACE_MS).toBeLessThanOrEqual(100);
  });

  it("is taken off the frame when nothing held it", () => {
    setup();

    takes(1);

    expect(holder()).toBe(document.body);
  });

  it("is taken off the frame when what held it is gone by then", () => {
    const { show } = setup();
    message().focus();

    grab();
    show({ field: "gone" });
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(document.body);
  });

  it("is taken off the frame when what held it can no longer have it", () => {
    const { show } = setup();
    message().focus();

    grab();
    show({ field: "locked" });
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(document.body);
  });

  it("does not go to an element the focus had left before the page took it", () => {
    setup();
    message().focus();
    message().blur();
    wait(0);
    const focused = vitest.spyOn(message(), "focus");

    takes(1);

    expect(holder()).toBe(document.body);
    expect(focused).not.toHaveBeenCalled();
  });

  it("is not handed to the frame it is being taken from", () => {
    setup();
    // The person had the page, and the page let the keyboard go.
    press();
    grab();
    page().blur();
    fireEvent.pointerDown(message());
    const handed = vitest.spyOn(page(), "focus");

    // It takes the keyboard again before the task is over.
    takes(1);

    expect(handed).not.toHaveBeenCalledWith({ preventScroll: true });
    expect(holder()).toBe(document.body);
  });

  it("stays where the person moved it while the page was waited on, and the page still took it", () => {
    const { onGrabbing } = setup();
    message().focus();
    const focused = vitest.spyOn(message(), "focus");

    grab();
    knob().focus();
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(knob());
    expect(focused).not.toHaveBeenCalled();
    // One grab is against it: three more go unreported, and the one after is the fifth.
    takes(GRABS_MAX - 2);
    expect(onGrabbing).not.toHaveBeenCalled();
    takes(1);
    expect(onGrabbing).toHaveBeenCalledTimes(1);
  });

  it("counts against a page that let it go again before its time was up", () => {
    const { onGrabbing } = setup();

    for (let take = 0; take < GRABS_MAX; take++) {
      grab();
      act(() => page().blur());
      wait(ATTEST_GRACE_MS);
    }

    expect(onGrabbing).toHaveBeenCalledTimes(1);
  });

  it("is given back once the page is out, where the app took it out for this", () => {
    setup({ stops: true });
    message().focus();

    takes(GRABS_MAX);

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
      wait(ATTEST_GRACE_MS);
    }

    expect(onGrabbing).not.toHaveBeenCalled();
    expect(focused).not.toHaveBeenCalled();
    expect(holder()).toBe(message());
  });
});

describe("the keyboard the person offers the page", () => {
  it("stays with the page whose reporter told of a press before the page took it", () => {
    const { onGrabbing } = setup();
    message().focus();

    press();
    takes(1);

    expect(holder()).toBe(page());
    expect(onGrabbing).not.toHaveBeenCalled();
    // Nothing is waited on: the offer stood when the page took the keyboard.
    expect(vitest.getTimerCount()).toBe(0);
  });

  it("stays with the page whose reporter tells of the press while the page is waited on", () => {
    const { onGrabbing } = setup();
    message().focus();
    const focused = vitest.spyOn(message(), "focus");

    grab();
    wait(ATTEST_GRACE_MS - 1);
    press();
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(page());
    expect(focused).not.toHaveBeenCalled();
    expect(onGrabbing).not.toHaveBeenCalled();
  });

  it("is never held against the page, however often the press is told while the page is waited on", () => {
    const { onGrabbing } = setup();

    for (let round = 0; round < GRABS_MAX * 2; round++) {
      message().focus();
      grab();
      press();
      wait(ATTEST_GRACE_MS);
      expect(holder()).toBe(page());
    }

    expect(onGrabbing).not.toHaveBeenCalled();
  });

  it("comes too late once the keyboard is back: a press told after the wait does not undo the grab", () => {
    const { onGrabbing } = setup();
    message().focus();

    takes(1);
    press();

    expect(holder()).toBe(message());
    fireEvent.pointerDown(message());
    takes(GRABS_MAX - 2);
    expect(onGrabbing).not.toHaveBeenCalled();
    takes(1);
    expect(onGrabbing).toHaveBeenCalledTimes(1);
  });

  it("stays with the page after Tab", () => {
    const { onGrabbing } = setup();
    message().focus();

    fireEvent.keyDown(message(), { key: "Tab" });
    takes(1);

    expect(holder()).toBe(page());
    expect(onGrabbing).not.toHaveBeenCalled();
  });

  it.each(["pointerMove", "pointerOver", "pointerEnter", "wheel", "scroll", "mouseMove"] as const)(
    "is not made by a %s over the frame's box: the page that takes the keyboard then has a grab against it",
    (over) => {
      const { onGrabbing } = setup();
      message().focus();

      fireEvent[over](box());
      fireEvent[over](page());
      takes(1);

      expect(holder()).toBe(message());
      takes(GRABS_MAX - 2);
      expect(onGrabbing).not.toHaveBeenCalled();
      takes(1);
      expect(onGrabbing).toHaveBeenCalledTimes(1);
    },
  );

  it("is not made by a pointer pressed on the frame's box in the app, which the page's reporter did not tell of", () => {
    const { onGrabbing } = setup();
    message().focus();

    fireEvent.pointerDown(box());
    fireEvent.pointerDown(page());
    fireEvent.mouseDown(page());
    takes(1);

    expect(holder()).toBe(message());
    takes(GRABS_MAX - 1);
    expect(onGrabbing).toHaveBeenCalledTimes(1);
  });

  it.each(["pointerMove", "pointerOut", "pointerLeave", "wheel"] as const)("stands when a %s follows anywhere else", (elsewhere) => {
    const { onGrabbing } = setup();
    message().focus();
    press();

    fireEvent[elsewhere](knob());
    fireEvent[elsewhere](document.body);
    takes(1);

    expect(holder()).toBe(page());
    expect(onGrabbing).not.toHaveBeenCalled();
  });

  it("stands when a pointer is pressed on the frame's box", () => {
    setup();
    message().focus();
    press();

    fireEvent.pointerDown(box());
    fireEvent.pointerDown(page());
    takes(1);

    expect(holder()).toBe(page());
  });

  it("is taken back by a pointer pressed anywhere else in the app", () => {
    const { onGrabbing } = setup();
    message().focus();
    press();

    fireEvent.pointerDown(knob());
    takes(1);

    expect(holder()).toBe(message());
    takes(GRABS_MAX - 1);
    expect(onGrabbing).toHaveBeenCalledTimes(1);
  });

  it.each(["a", "Enter", "ArrowRight", "Shift"])("is taken back by the key %s pressed in the app", (key) => {
    const { onGrabbing } = setup();
    message().focus();
    press();

    fireEvent.keyDown(message(), { key });
    takes(1);

    expect(holder()).toBe(message());
    takes(GRABS_MAX - 1);
    expect(onGrabbing).toHaveBeenCalledTimes(1);
  });

  it("is taken back when Tab brings the focus to one of the app's controls, not to the page", () => {
    setup();
    message().focus();

    fireEvent.keyDown(message(), { key: "Tab" });
    knob().focus();
    takes(1);

    expect(holder()).toBe(knob());
  });

  it("is taken back when the focus arrives on one of the app's elements", () => {
    setup();
    press();

    knob().focus();
    takes(1);

    expect(holder()).toBe(knob());
  });

  it("stands when the focus arrives on the frame", () => {
    setup();
    message().focus();
    press();

    act(() => page().focus());
    act(() => fireEvent.blur(window));
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(page());
  });
});

describe("what the app's own handlers keep to themselves", () => {
  /** A handler of the app's that lets nothing of `type` on `element` go further up. */
  const keep = (element: Element, type: string) => element.addEventListener(type, (event) => event.stopPropagation());

  it("is seen all the same: a pointer pressed in the app", () => {
    setup();
    keep(knob(), "pointerdown");
    message().focus();
    press();

    fireEvent.pointerDown(knob());
    takes(1);

    expect(holder()).toBe(message());
  });

  it("is seen all the same: a key pressed in the app", () => {
    setup();
    keep(message(), "keydown");
    message().focus();
    press();

    fireEvent.keyDown(message(), { key: "a" });
    takes(1);

    expect(holder()).toBe(message());
  });

  it("is seen all the same: the focus arriving on a control", () => {
    setup();
    keep(knob(), "focusin");
    press();

    knob().focus();
    takes(1);

    expect(holder()).toBe(knob());
  });

  it("is seen all the same: the focus leaving the element the page took it from", () => {
    setup();
    keep(message(), "focusout");
    message().focus();

    takes(1);

    expect(holder()).toBe(message());
  });
});

describe("a page that goes on taking the keyboard", () => {
  it("is reported the fifth time it does, once it was waited on, and not before", () => {
    const { onGrabbing } = setup();
    message().focus();
    expect(GRABS_MAX).toBe(5);

    for (let take = 1; take < GRABS_MAX; take++) {
      takes(1);
      expect(holder()).toBe(message());
    }
    expect(onGrabbing).not.toHaveBeenCalled();

    grab();
    expect(onGrabbing).not.toHaveBeenCalled();
    wait(ATTEST_GRACE_MS);
    expect(onGrabbing).toHaveBeenCalledTimes(1);
    expect(holder()).toBe(message());
  });

  it("is reported again each time it does after that, where the app left the page up", () => {
    const { onGrabbing } = setup();
    message().focus();
    takes(GRABS_MAX);
    expect(onGrabbing).toHaveBeenCalledTimes(1);

    takes(2);

    expect(onGrabbing).toHaveBeenCalledTimes(3);
    expect(holder()).toBe(message());
  });

  it("took it once when the app is told of it more than once before the keyboard is back", () => {
    const { onGrabbing } = setup();
    message().focus();

    for (let take = 1; take < GRABS_MAX; take++) {
      grab();
      fireEvent.blur(window);
      wait(ATTEST_GRACE_MS - 1);
      fireEvent.blur(window);
      wait(1);
      expect(holder()).toBe(message());
      // A wait of its own that a later blur had started would end here, and count once more.
      wait(ATTEST_GRACE_MS);
    }
    expect(onGrabbing).not.toHaveBeenCalled();

    takes(1);
    expect(onGrabbing).toHaveBeenCalledTimes(1);
  });

  it("is never reported for the keyboard the person gave it, however often", () => {
    const { onGrabbing } = setup();

    for (let round = 0; round < GRABS_MAX * 2; round++) {
      message().focus();
      press();
      takes(1);
      expect(holder()).toBe(page());
    }
    expect(onGrabbing).not.toHaveBeenCalled();

    // What it was given does not count against it afterwards either.
    message().focus();
    takes(GRABS_MAX - 1);
    expect(onGrabbing).not.toHaveBeenCalled();
  });

  it("has nothing against it in the frame that replaces it", () => {
    const { onGrabbing, show } = setup();
    message().focus();
    takes(GRABS_MAX - 1);

    show({ n: 1 });
    takes(GRABS_MAX - 1);
    expect(onGrabbing).not.toHaveBeenCalled();

    takes(1);
    expect(onGrabbing).toHaveBeenCalledTimes(1);
  });

  it("is not answered for by the frame that replaces it while it is waited on", () => {
    const { onGrabbing, show } = setup();
    message().focus();
    takes(GRABS_MAX - 1);
    const focused = vitest.spyOn(message(), "focus");

    grab();
    show({ n: 1 });
    wait(ATTEST_GRACE_MS);

    expect(onGrabbing).not.toHaveBeenCalled();
    expect(focused).not.toHaveBeenCalled();
    takes(GRABS_MAX - 1);
    expect(onGrabbing).not.toHaveBeenCalled();
  });

  it("is reported to whoever asks now, not to whoever asked when the guard was put up", () => {
    const { onGrabbing, show } = setup();
    const asksNow = vitest.fn();
    show({ onGrabbing: asksNow });

    takes(GRABS_MAX);

    expect(asksNow).toHaveBeenCalledTimes(1);
    expect(onGrabbing).not.toHaveBeenCalled();
  });
});

describe("a page that held the app up while it had the keyboard", () => {
  /** The page takes the keyboard, and the wait on it ends `late` ms after it was due. */
  function takesAndHolds(late: number) {
    const clock = vitest.spyOn(performance, "now").mockReturnValue(1000);
    grab();
    clock.mockReturnValue(1000 + ATTEST_GRACE_MS + late);
    wait(ATTEST_GRACE_MS);
  }

  it("is reported the first time, when the keyboard goes back three seconds late", () => {
    const { onGrabbing } = setup();
    message().focus();

    takesAndHolds(3000);

    expect(onGrabbing).toHaveBeenCalledTimes(1);
    expect(holder()).toBe(message());
  });

  it("is reported from the first millisecond past what a busy app may be late by, and not at it", () => {
    const { onGrabbing } = setup();
    message().focus();

    takesAndHolds(LATE_MS);
    expect(onGrabbing).not.toHaveBeenCalled();

    takesAndHolds(LATE_MS + 1);
    expect(onGrabbing).toHaveBeenCalledTimes(1);
  });

  it("is not reported for a wait that a press ended, however late the press was told", () => {
    const { onGrabbing } = setup();
    message().focus();
    const clock = vitest.spyOn(performance, "now").mockReturnValue(1000);

    grab();
    clock.mockReturnValue(1000 + 3000);
    press();
    wait(ATTEST_GRACE_MS);

    expect(onGrabbing).not.toHaveBeenCalled();
    expect(holder()).toBe(page());
  });
});

describe("the keyboard a page took while the window was behind", () => {
  /** The person goes to another window: the app's is told it lost the focus, which stays where it was. */
  function leave() {
    act(() => {
      fireEvent.blur(window);
    });
  }

  /** The page takes the focus meanwhile. A window that is not in front is told nothing of it. */
  function takesBehind() {
    act(() => page().focus());
    // The task the focus left its element in is long over by the time the person is back.
    wait(0);
  }

  /** The window says it is in front again, and the task it said so in is over. */
  function comeBack() {
    act(() => {
      fireEvent.focus(window);
    });
    wait(0);
  }

  /** What the browser says of where the keys go: to the app's window or a frame in it, or elsewhere. */
  function inFront(front: boolean) {
    vitest.spyOn(document, "hasFocus").mockReturnValue(front);
  }

  /** The person is back by the keyboard alone, and the beat that finds the page with it has come. */
  function comeBackUnheard() {
    inFront(true);
    wait(BEHIND_LOOK_MS);
  }

  /** One grab is against the page: three more go unreported, and the one after is the fifth. */
  function expectOneGrab(onGrabbing: () => void) {
    takes(GRABS_MAX - 2);
    expect(onGrabbing).not.toHaveBeenCalled();
    takes(1);
    expect(onGrabbing).toHaveBeenCalledTimes(1);
  }

  /** No grab is against the page: once the offer is taken back, the fifth it takes is the first reported. */
  function expectNoGrab(onGrabbing: () => void) {
    fireEvent.pointerDown(message());
    takes(GRABS_MAX - 1);
    expect(onGrabbing).not.toHaveBeenCalled();
    takes(1);
    expect(onGrabbing).toHaveBeenCalledTimes(1);
  }

  it("goes back to what had it when the window went behind, though the focus left nothing as the page took it", () => {
    const { onGrabbing } = setup();
    message().focus();
    leave();
    takesBehind();

    // In front again, the window is told it lost the focus to the page.
    act(() => {
      fireEvent.blur(window);
    });
    wait(ATTEST_GRACE_MS - 1);
    expect(holder()).toBe(page());
    wait(1);

    expect(holder()).toBe(message());
    expectOneGrab(onGrabbing);
  });

  it("is taken once when the window says it is in front and that it lost the focus to the page, one after the other", () => {
    const { onGrabbing } = setup();
    message().focus();
    leave();
    takesBehind();

    act(() => {
      fireEvent.focus(window);
      fireEvent.blur(window);
    });
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(message());
    expectOneGrab(onGrabbing);
  });

  it("goes back once the window is in front again, and is held against the page", () => {
    const { onGrabbing } = setup();
    message().focus();
    leave();
    takesBehind();

    comeBack();
    wait(ATTEST_GRACE_MS - 1);
    expect(holder()).toBe(page());
    wait(1);

    expect(holder()).toBe(message());
    expectOneGrab(onGrabbing);
  });

  it("is looked for a task after the window says it is in front, when the browser has put the focus back", () => {
    setup();
    message().focus();
    leave();

    act(() => {
      fireEvent.focus(window);
      // Only now is the focus where the page took it, and the window is told nothing more.
      page().focus();
    });
    wait(0);
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(message());
  });

  it("does not go to what had it before the person came back and let it go", () => {
    setup();
    message().focus();
    leave();
    comeBack();
    message().blur();
    wait(0);
    const focused = vitest.spyOn(message(), "focus");

    takes(1);

    expect(holder()).toBe(document.body);
    expect(focused).not.toHaveBeenCalled();
  });

  it("goes back when the tab is shown again, and is left with the page while the tab is hidden", () => {
    const { onGrabbing } = setup();
    message().focus();
    leave();
    takesBehind();

    // A hidden tab's timers run late, and a wait that ends late stops the page for it.
    setVisibility("hidden");
    wait(ATTEST_GRACE_MS);
    expect(holder()).toBe(page());

    setVisibility("visible");
    wait(ATTEST_GRACE_MS - 1);
    expect(holder()).toBe(page());
    wait(1);

    expect(holder()).toBe(message());
    expectOneGrab(onGrabbing);
  });

  it.each(["pointerMove", "pointerDown"] as const)(
    "goes back at a %s in the app, where the window has not said it is in front",
    (pointer) => {
      const { onGrabbing } = setup();
      message().focus();
      leave();
      takesBehind();

      fireEvent[pointer](knob());
      wait(ATTEST_GRACE_MS - 1);
      expect(holder()).toBe(page());
      wait(1);

      expect(holder()).toBe(message());
      expectOneGrab(onGrabbing);
    },
  );

  it("is not looked for at a pointer in the app while the window never went behind", () => {
    const { onGrabbing } = setup();
    // The person gave the page the keyboard, then pressed something in the app that left the focus there.
    press();
    act(() => page().focus());
    fireEvent.pointerDown(knob());

    fireEvent.pointerMove(knob());
    fireEvent.pointerDown(knob());
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(page());
    expectNoGrab(onGrabbing);
  });

  it("is no longer looked for at a pointer in the app once the person is back", () => {
    const { onGrabbing } = setup();
    message().focus();
    leave();
    comeBack();
    press();
    act(() => page().focus());
    fireEvent.pointerDown(knob());

    fireEvent.pointerMove(knob());
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(page());
    expectNoGrab(onGrabbing);
  });

  it("stays with the page the person pressed in to come back", () => {
    const { onGrabbing } = setup();
    message().focus();
    leave();
    press();
    act(() => page().focus());

    comeBack();
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(page());
    expectNoGrab(onGrabbing);
  });

  it("stays with the page whose reporter tells of that press only after the window says it is in front", () => {
    const { onGrabbing } = setup();
    message().focus();
    leave();
    act(() => page().focus());

    comeBack();
    wait(ATTEST_GRACE_MS - 1);
    press();
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(page());
    expectNoGrab(onGrabbing);
  });

  it("goes back within a beat of the person coming back by the keyboard alone, which the app's window is told nothing of", () => {
    const { onGrabbing } = setup();
    message().focus();
    inFront(false);
    leave();
    takesBehind();

    // Behind, the keys go to neither: the page is left with the focus, however long.
    wait(BEHIND_LOOK_MS * 3);
    expect(holder()).toBe(page());

    // In front again with the page holding the focus, it is the page's window that is told so:
    // the app's hears of no focus, no tab shown again and no pointer.
    inFront(true);
    wait(BEHIND_LOOK_MS - 1);
    expect(holder()).toBe(page());
    wait(1);
    // Found on the beat, the page is waited on like any other.
    wait(ATTEST_GRACE_MS - 1);
    expect(holder()).toBe(page());
    wait(1);

    expect(holder()).toBe(message());
    expectOneGrab(onGrabbing);
  });

  it("is looked for on a beat no slower than a fifth of a second", () => {
    expect(BEHIND_LOOK_MS).toBeLessThanOrEqual(200);
  });

  it("stays with the page the person pressed in to come back, when the beat finds it there", () => {
    const { onGrabbing } = setup();
    message().focus();
    inFront(false);
    leave();
    press();
    act(() => page().focus());

    comeBackUnheard();
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(page());
    expectNoGrab(onGrabbing);
  });

  it("goes on being looked for on the beat until the page is found with it, whatever else has the focus meanwhile", () => {
    const { onGrabbing } = setup();
    message().focus();
    leave();
    // A browser that says the keys go to the app while one of the app's own elements has the focus.
    comeBackUnheard();
    takesBehind();

    // The window has still not said it is in front: a pointer in the app is looked at.
    fireEvent.pointerMove(knob());
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(message());
    expectOneGrab(onGrabbing);
  });

  it("is no longer looked for at a pointer in the app once the beat found the page with it", () => {
    const { onGrabbing } = setup();
    message().focus();
    inFront(false);
    leave();
    takesBehind();
    comeBackUnheard();
    wait(ATTEST_GRACE_MS);
    expect(holder()).toBe(message());
    // The person gives the page the keyboard, then presses something in the app that leaves the focus there.
    press();
    act(() => page().focus());
    fireEvent.pointerDown(knob());

    fireEvent.pointerMove(knob());
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(page());
    // The one grab the beat found is against the page, and no other.
    fireEvent.pointerDown(message());
    takes(GRABS_MAX - 2);
    expect(onGrabbing).not.toHaveBeenCalled();
    takes(1);
    expect(onGrabbing).toHaveBeenCalledTimes(1);
  });

  it("does not go to what had it before the beat found the page, once the person let that go", () => {
    setup();
    message().focus();
    inFront(false);
    leave();
    takesBehind();
    comeBackUnheard();
    wait(ATTEST_GRACE_MS);
    expect(holder()).toBe(message());
    message().blur();
    wait(0);
    const focused = vitest.spyOn(message(), "focus");

    takes(1);

    expect(holder()).toBe(document.body);
    expect(focused).not.toHaveBeenCalled();
  });

  it("is looked for on the beat only while the window is behind, and on one beat however often it says so", () => {
    setup();
    inFront(false);
    expect(vitest.getTimerCount()).toBe(0);

    leave();
    leave();
    expect(vitest.getTimerCount()).toBe(1);
    wait(BEHIND_LOOK_MS * 3);
    expect(vitest.getTimerCount()).toBe(1);

    comeBack();
    expect(vitest.getTimerCount()).toBe(0);
    wait(BEHIND_LOOK_MS * 3);
    expect(vitest.getTimerCount()).toBe(0);
  });

  it("is looked for on no beat after the one that found the page with it", () => {
    setup();
    inFront(false);
    leave();
    // The focus is not really moved: jsdom sets a timer of its own for each focus it moves.
    vitest.spyOn(document, "activeElement", "get").mockReturnValue(page());

    comeBackUnheard();
    // The page is waited on, and nothing else.
    expect(vitest.getTimerCount()).toBe(1);
    wait(ATTEST_GRACE_MS);
    expect(vitest.getTimerCount()).toBe(0);
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
    expect(passive("pointerdown")).toEqual([true]);
    expect(passive("pointermove")).toEqual([true]);
    expect(passive("wheel")).toEqual([]);
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
    // The window says twice that it is in front.
    fireEvent.focus(window);
    fireEvent.focus(window);
    // One to forget what the focus left, one to wait on the page, one to look once the window is in front.
    expect(vitest.getTimerCount()).toBe(3);

    unmount();

    expect(vitest.getTimerCount()).toBe(0);
  });

  it("leaves no beat running behind a window that went behind", () => {
    const { unmount } = setup();
    fireEvent.blur(window);
    expect(vitest.getTimerCount()).toBe(1);

    unmount();

    expect(vitest.getTimerCount()).toBe(0);
  });

  it("hears of no press any more", () => {
    const { unmount, onGrabbing } = setup();
    const told = attest;
    unmount();

    expect(() => told()).not.toThrow();
    expect(onGrabbing).not.toHaveBeenCalled();
  });

  it("takes every listener it put up away again", () => {
    const WATCHED = ["pointermove", "pointerdown", "wheel", "keydown", "focusin", "focusout", "blur", "focus", "visibilitychange"];
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
      "keydown true",
      "focusin true",
      "focusout true",
      "visibilitychange false",
    ]);
    expect(onWindow.map((one) => `${one.type} ${one.capture}`)).toEqual(["blur false", "focus false"]);
    expect(told(taken.document.mock.calls)).toEqual([]);

    unmount();

    expect(told(taken.document.mock.calls)).toEqual(onDocument);
    expect(told(taken.window.mock.calls)).toEqual(onWindow);
  });
});
