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

/** How long a person holds the button of a mouse down in a click: several times what a page is waited on. */
const HELD_MS = 150;

/** The page takes the keyboard `times` over, and each time is waited on for as long as a page is. */
function takes(times: number) {
  for (let take = 0; take < times; take++) {
    grab();
    wait(ATTEST_GRACE_MS);
  }
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

  it("stays with the page after Tab pressed with shift, which goes back through the app's controls", () => {
    const { onGrabbing } = setup();
    message().focus();

    fireEvent.keyDown(message(), { key: "Tab", shiftKey: true });
    takes(1);

    expect(holder()).toBe(page());
    expectNoGrab(onGrabbing);
  });

  it.each(["ctrlKey", "metaKey", "altKey"] as const)(
    "is not made by Tab pressed with %s, which goes to the browser or the system and not through the app's controls",
    (held) => {
      const { onGrabbing } = setup();
      message().focus();

      fireEvent.keyDown(message(), { key: "Tab", [held]: true });
      takes(1);

      expect(holder()).toBe(message());
      expectOneGrab(onGrabbing);
    },
  );

  it.each(["ctrlKey", "metaKey", "altKey"] as const)("is taken back by Tab pressed with %s, as by any other key", (held) => {
    const { onGrabbing } = setup();
    message().focus();
    press();

    fireEvent.keyDown(message(), { key: "Tab", [held]: true });
    takes(1);

    expect(holder()).toBe(message());
    expectOneGrab(onGrabbing);
  });

  it("is over a task after Tab that did not bring the focus to the page: a page that takes the keyboard then took it", () => {
    const { onGrabbing } = setup();
    message().focus();

    // The app kept the key for itself, as the list of commands over the message does.
    fireEvent.keyDown(message(), { key: "Tab" });
    wait(0);
    takes(1);

    expect(holder()).toBe(message());
    expectOneGrab(onGrabbing);
  });

  it("is over once a press was told and the frame did not take the focus in the time a page is given: a page that takes the keyboard then took it", () => {
    const { onGrabbing } = setup();
    message().focus();

    press();
    wait(ATTEST_GRACE_MS);
    takes(1);

    expect(holder()).toBe(message());
    expectOneGrab(onGrabbing);
  });

  it("stands for the focus that comes thirty milliseconds after the press was told, as a busy browser brings it", () => {
    const { onGrabbing } = setup();
    message().focus();

    press();
    wait(30);
    takes(1);

    expect(holder()).toBe(page());
    expectNoGrab(onGrabbing);
  });

  it("is made by a press told thirty milliseconds after the page took the keyboard, as a busy browser tells it", () => {
    const { onGrabbing } = setup();
    message().focus();

    grab();
    wait(30);
    press();
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(page());
    expectNoGrab(onGrabbing);
  });

  it("is made anew by the second telling of one tap, long after the first was over", () => {
    const { onGrabbing } = setup();
    message().focus();

    // A finger on a phone: the pointer is told of when it goes down, the mouse press the browser
    // makes of it when it is lifted, and only then does the focus move.
    press();
    wait(ATTEST_GRACE_MS + 250);
    press();
    takes(1);

    expect(holder()).toBe(page());
    expectNoGrab(onGrabbing);
  });

  it("is made anew when the press is told to be over, for the page that takes the keyboard at the click of a button a person held", () => {
    const { onGrabbing } = setup();
    message().focus();

    // A mouse: the button goes down on something that keeps the focus from moving, stays down for
    // as long as a person holds it, and the page focuses its field when the button comes up.
    press();
    wait(HELD_MS);
    expect(holder()).toBe(message());
    press();
    takes(1);

    expect(holder()).toBe(page());
    expectNoGrab(onGrabbing);
  });

  it("is not made by a button that is still held: a page that takes the keyboard then, with nothing told since the press, took it", () => {
    const { onGrabbing } = setup();
    message().focus();

    press();
    wait(HELD_MS);
    takes(1);

    expect(holder()).toBe(message());
    expectOneGrab(onGrabbing);
  });

  it("stands for as long as the page has the keyboard, however long ago the press was told and however often the page is looked at again", () => {
    const { onGrabbing } = setup();
    message().focus();

    press();
    takes(1);
    // One time more than a page may take the keyboard unasked: the person reads in another tab
    // and comes back, and each time the tab is shown the frame is looked at again.
    for (let round = 0; round <= GRABS_MAX; round++) {
      setVisibility("hidden");
      wait(1000);
      setVisibility("visible");
      wait(ATTEST_GRACE_MS);
      expect(holder()).toBe(page());
    }

    expectNoGrab(onGrabbing);
  });

  it("lasts from the press told last, not from the one before it", () => {
    const { onGrabbing } = setup();
    message().focus();

    press();
    wait(30);
    press();
    wait(30);
    takes(1);

    expect(holder()).toBe(page());
    expectNoGrab(onGrabbing);
  });

  it.each([
    ["a press told", () => press()],
    ["Tab", () => fireEvent.keyDown(message(), { key: "Tab" })],
  ])("is made to the frame on show and to no other: %s does not give the keyboard to the frame that replaces it", (_, offer) => {
    const { onGrabbing, show } = setup();
    message().focus();

    offer();
    show({ n: 1 });
    takes(1);

    expect(holder()).toBe(message());
    expectOneGrab(onGrabbing);
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
  /** The page takes the keyboard, and the wait on it comes due `late` ms after its time. */
  function takesAndComesDue(late: number) {
    const clock = vitest.spyOn(performance, "now").mockReturnValue(1000);
    grab();
    clock.mockReturnValue(1000 + ATTEST_GRACE_MS + late);
    // Up to the wait's own timer and no further: what it sets when it comes due is left for later.
    wait(ATTEST_GRACE_MS - 1);
    act(() => {
      vitest.advanceTimersToNextTimer();
    });
  }

  /** The task a wait that came due late leaves for a press: the fake clock puts a timer set by a timer a millisecond on. */
  const TASK_MS = 1;

  /** The same, and the wait is over: no press was told in the task it left for one. */
  function takesAndHolds(late: number) {
    takesAndComesDue(late);
    wait(TASK_MS);
  }

  it("is not reported the first time the keyboard goes back late, which a busy app may be the cause of: that is one grab like any other", () => {
    const { onGrabbing } = setup();
    message().focus();

    takesAndHolds(3000);

    expect(onGrabbing).not.toHaveBeenCalled();
    expect(holder()).toBe(message());
    expectOneGrab(onGrabbing);
  });

  it("is reported the second time the keyboard goes back late, and each time after that", () => {
    const { onGrabbing } = setup();
    message().focus();
    takesAndHolds(3000);

    takesAndHolds(3000);
    expect(onGrabbing).toHaveBeenCalledTimes(1);
    expect(holder()).toBe(message());

    takesAndHolds(3000);
    expect(onGrabbing).toHaveBeenCalledTimes(2);
  });

  it("is late from the first millisecond past what a busy app may be late by, and not at it", () => {
    const { onGrabbing } = setup();
    message().focus();

    takesAndHolds(LATE_MS);
    takesAndHolds(LATE_MS);
    expect(onGrabbing).not.toHaveBeenCalled();

    takesAndHolds(LATE_MS + 1);
    expect(onGrabbing).not.toHaveBeenCalled();
    takesAndHolds(LATE_MS + 1);
    expect(onGrabbing).toHaveBeenCalledTimes(1);
  });

  it("has the keyboard for one task more when the wait comes due late, and no longer", () => {
    setup();
    message().focus();

    takesAndComesDue(3000);
    expect(holder()).toBe(page());

    wait(TASK_MS);
    expect(holder()).toBe(message());
  });

  it("is not held to have taken it when the press is told right after the wait came due late: the press was on its way", () => {
    const { onGrabbing } = setup();
    message().focus();
    const focused = vitest.spyOn(message(), "focus");

    // The app was held up with the press waiting to be told, and the wait's timer came first.
    takesAndComesDue(3000);
    press();
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(page());
    expect(focused).not.toHaveBeenCalled();
    expect(onGrabbing).not.toHaveBeenCalled();
    expectNoGrab(onGrabbing);
  });

  it("was not late for a wait that a press ended after it came due: the next late one is its first", () => {
    const { onGrabbing } = setup();
    message().focus();
    takesAndComesDue(3000);
    press();
    wait(ATTEST_GRACE_MS);
    // The person goes back to the message, and the page takes the keyboard from it.
    message().focus();

    takesAndHolds(3000);

    expect(onGrabbing).not.toHaveBeenCalled();
    expect(holder()).toBe(message());
  });

  it("is not answered for by the frame that replaces it: that one may be late once too", () => {
    const { onGrabbing, show } = setup();
    message().focus();
    takesAndHolds(3000);

    show({ n: 1 });
    takesAndHolds(3000);
    expect(onGrabbing).not.toHaveBeenCalled();

    takesAndHolds(3000);
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

    // A hidden tab's timers run late, and a wait that ends late is held against the page.
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
    setup();
    message().focus();
    inFront(false);
    leave();
    takesBehind();

    // Back by the keyboard alone. A fifth of a second by the clock, not by the guard's own count
    // of it, and the time a page is waited on: by then the keys are the message's again.
    inFront(true);
    wait(200 + ATTEST_GRACE_MS);

    expect(holder()).toBe(message());
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

  /** The person passes over the app's window on the way to another: it says it is behind, in front and behind again in one task. */
  function passOver() {
    act(() => {
      fireEvent.blur(window);
      fireEvent.focus(window);
      fireEvent.blur(window);
    });
    // The task the window said it was in front in is long over.
    wait(0);
  }

  it("goes back within a beat of the person coming back by the keyboard alone to a window that went behind again before it was settled as back", () => {
    const { onGrabbing } = setup();
    message().focus();
    inFront(false);
    passOver();
    takesBehind();
    wait(BEHIND_LOOK_MS * 3);
    expect(holder()).toBe(page());

    comeBackUnheard();
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(message());
    expectOneGrab(onGrabbing);
  });

  it("goes back at a pointer in the app, where the window went behind again before it was settled as back", () => {
    const { onGrabbing } = setup();
    message().focus();
    inFront(false);
    passOver();
    takesBehind();

    fireEvent.pointerMove(knob());
    wait(ATTEST_GRACE_MS);

    expect(holder()).toBe(message());
    expectOneGrab(onGrabbing);
  });

  it("is still looked for on the beat when the window went behind again before it was settled as back, until it says it is in front", () => {
    setup();
    inFront(false);

    passOver();
    expect(vitest.getTimerCount()).toBe(1);
    wait(BEHIND_LOOK_MS * 3);
    expect(vitest.getTimerCount()).toBe(1);

    comeBack();
    expect(vitest.getTimerCount()).toBe(0);
  });

  /** The app puts the page up while its window is behind, where the person left off writing: no `blur` tells of it. */
  function putUpBehind() {
    inFront(false);
    render(<textarea aria-label="message" />);
    message().focus();
    return setup({ field: "gone" });
  }

  it("goes back within a beat of the person coming back by the keyboard alone to a window the page was put up behind", () => {
    const { onGrabbing } = putUpBehind();
    takesBehind();

    // Behind, the page is left with the focus, however long.
    wait(BEHIND_LOOK_MS * 3);
    expect(holder()).toBe(page());

    inFront(true);
    wait(BEHIND_LOOK_MS - 1);
    expect(holder()).toBe(page());
    wait(1);
    wait(ATTEST_GRACE_MS - 1);
    expect(holder()).toBe(page());
    wait(1);

    expect(holder()).toBe(message());
    expectOneGrab(onGrabbing);
  });

  it("goes back at a pointer in the app, where the window the page was put up behind has not said it is in front", () => {
    const { onGrabbing } = putUpBehind();
    takesBehind();

    fireEvent.pointerMove(knob());
    wait(ATTEST_GRACE_MS - 1);
    expect(holder()).toBe(page());
    wait(1);

    expect(holder()).toBe(message());
    expectOneGrab(onGrabbing);
  });

  it("is looked for on the beat from the time the page is put up behind the window, until the window says it is in front", () => {
    inFront(false);
    setup();
    expect(vitest.getTimerCount()).toBe(1);
    wait(BEHIND_LOOK_MS * 3);
    expect(vitest.getTimerCount()).toBe(1);

    comeBack();
    expect(vitest.getTimerCount()).toBe(0);
    wait(BEHIND_LOOK_MS * 3);
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

  it("leaves no offer waiting for its time to be over", () => {
    const { unmount } = setup();
    press();
    expect(vitest.getTimerCount()).toBe(1);

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
