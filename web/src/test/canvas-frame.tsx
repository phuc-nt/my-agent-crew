import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { vi as vitest } from "vitest";
import { CanvasFrame } from "../components/canvas/canvas-frame";

/**
 * The frame of a canvas page on a fake clock, with what it tells the panel as spies, and the things
 * a page and a person do to it: the page says something to the app's window or over the port its
 * reporter handed over, takes the keyboard, and the person writes in a field of the app's.
 */

export function startFrame(): void {
  vitest.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
}

/** Takes the frame down, then the fields `writing` put beside it. */
export function stopFrame(): void {
  cleanup();
  vitest.useRealTimers();
  vitest.restoreAllMocks();
  for (const field of document.body.querySelectorAll(":scope > input")) field.remove();
}

export type Setup = { version?: number; connected?: boolean };

/** The frame with what it tells the panel as spies; `show` puts it up again with other props. */
export function setup(first: Setup = {}) {
  const onMount = vitest.fn();
  const onError = vitest.fn();
  const onSilenced = vitest.fn();
  const element = (now: Setup) => (
    <CanvasFrame
      artifactId="a1"
      title="Trang chủ"
      version={now.version ?? first.version ?? 1}
      connected={now.connected ?? first.connected ?? true}
      onMount={onMount}
      onError={onError}
      onSilenced={onSilenced}
    />
  );
  const view = render(element(first));
  const show = (now: Setup) => view.rerender(element(now));
  return { ...view, onMount, onError, onSilenced, show };
}

export function frameIn(container: HTMLElement): HTMLIFrameElement {
  const found = container.querySelector("iframe");
  if (!found) throw new Error("the page is not in a frame");
  return found;
}

/** The page's own window, which is what a report must come from. */
export function windowOf(frame: HTMLIFrameElement): Window {
  if (!frame.contentWindow) throw new Error("the frame has no window");
  return frame.contentWindow;
}

/** A message as the browser delivers it: from a window, with the origin a sandboxed page is given. */
export function deliver(source: Window | null, data: unknown, origin = "null", ports: unknown[] = []) {
  act(() => {
    window.dispatchEvent(Object.assign(new Event("message"), { source, origin, data, ports }));
  });
}

/** One end of a message channel, as far as the panel uses it: it listens on it and closes it. */
export type Port = { onmessage: ((event: { data: unknown }) => void) | null; close: ReturnType<typeof vitest.fn> };
const port = (): Port => ({ onmessage: null, close: vitest.fn() });

/** The hello of the page's reporter, with the port it tells of presses over. */
export function hello(frame: HTMLIFrameElement, source: Window | null = windowOf(frame), origin = "null"): Port {
  const handed = port();
  deliver(source, { type: "canvas-hello" }, origin, [handed]);
  return handed;
}

/** What the page's reporter says over the port when a person presses a pointer inside the page. */
export const PRESS = { type: "press" };

/** Something comes over `port`, if the panel listens on it. */
export function tell(over: Port, data: unknown = PRESS) {
  act(() => over.onmessage?.({ data }));
}

export const failure = { type: "canvas-error", message: "boom", source: "page.html", line: 3, column: 7 };

/** `times` messages from `source`, one after another. The answer is how often what they carry was read. */
export function flood(source: Window | null, times: number, data: unknown = failure): number {
  let read = 0;
  const carried = {
    get() {
      read += 1;
      return data;
    },
  };
  act(() => {
    for (let n = 0; n < times; n++) {
      const event = Object.assign(new Event("message"), { source, origin: "null" });
      window.dispatchEvent(Object.defineProperty(event, "data", carried));
    }
  });
  return read;
}

/** The person has the frame's focus: what the browser says of `document.activeElement` once they click in. */
export function focusOn(frame: HTMLIFrameElement) {
  vitest.spyOn(document, "activeElement", "get").mockReturnValue(frame);
}

/** The box the frame is put in. */
export function boxOf(frame: HTMLIFrameElement): HTMLElement {
  if (!frame.parentElement) throw new Error("the frame is in no box");
  return frame.parentElement;
}

/** A field of the app's beside the canvas, which the person is writing in. */
export function writing(): HTMLInputElement {
  const field = document.body.appendChild(document.createElement("input"));
  field.focus();
  return field;
}

/** The page takes the keyboard: its frame has the focus, and the app's window is told it lost it. */
export function grab(frame: HTMLIFrameElement) {
  act(() => {
    frame.focus();
    fireEvent.blur(window);
  });
}
