import { describe, expect, it } from "vitest";
import { REPORT_MAX, SOURCE_MAX, isLoadFailure, isPress, readFrameMessage, where } from "./frame-messages";

/** A frame whose window is a stand-in that only has to be told apart from another. */
function frameOf(own: Window | null): HTMLIFrameElement {
  return { contentWindow: own } as HTMLIFrameElement;
}

function messageFrom(source: unknown, data: unknown, origin = "null"): MessageEvent {
  return { source, origin, data } as MessageEvent;
}

const own = {} as Window;
const report = { type: "canvas-error", message: "boom", source: "page.html", line: 3, column: 7 };

/** The report `event` comes to, if it comes to one. */
const parseFrameMessage = (event: MessageEvent, frame: HTMLIFrameElement | null) => readFrameMessage(event, frame)?.error ?? null;

describe("what a page in the canvas frame may tell the panel", () => {
  it("takes a report from the frame's own window, whose origin the browser writes as null", () => {
    expect(parseFrameMessage(messageFrom(own, report), frameOf(own))).toEqual({
      message: "boom",
      source: "page.html",
      line: 3,
      column: 7,
    });
  });

  it("drops a report from any other window, and one from nowhere", () => {
    const frame = frameOf(own);
    expect(parseFrameMessage(messageFrom({} as Window, report), frame)).toBeNull();
    expect(parseFrameMessage(messageFrom(null, report), frame)).toBeNull();
  });

  it("does not take a message from nowhere for one from a frame that is gone", () => {
    expect(parseFrameMessage(messageFrom(null, report), frameOf(null))).toBeNull();
    expect(parseFrameMessage(messageFrom(undefined, report), frameOf(null))).toBeNull();
    expect(parseFrameMessage(messageFrom(own, report), null)).toBeNull();
  });

  it("drops a report from the frame's window when the origin is not null", () => {
    const frame = frameOf(own);
    expect(parseFrameMessage(messageFrom(own, report, window.location.origin), frame)).toBeNull();
    expect(parseFrameMessage(messageFrom(own, report, "https://example.com"), frame)).toBeNull();
    expect(parseFrameMessage(messageFrom(own, report, ""), frame)).toBeNull();
  });

  it("drops data that is not an object, and an object that is not a canvas error", () => {
    const frame = frameOf(own);
    for (const data of ["canvas-error", 42, true, null, undefined]) {
      expect(parseFrameMessage(messageFrom(own, data), frame)).toBeNull();
    }
    expect(parseFrameMessage(messageFrom(own, { ...report, type: "canvas-note" }), frame)).toBeNull();
    expect(parseFrameMessage(messageFrom(own, { ...report, type: undefined }), frame)).toBeNull();
  });

  it("drops a report whose message is not text", () => {
    const frame = frameOf(own);
    for (const message of [undefined, null, 7, { text: "x" }, ["x"]]) {
      expect(parseFrameMessage(messageFrom(own, { ...report, message }), frame)).toBeNull();
    }
  });

  it("keeps an empty message, which the page did say", () => {
    expect(parseFrameMessage(messageFrom(own, { ...report, message: "" }), frameOf(own))?.message).toBe("");
  });

  it("cuts the message at 2000 characters and the file at 300", () => {
    const long = { ...report, message: "m".repeat(5000), source: "s".repeat(900) };
    const taken = parseFrameMessage(messageFrom(own, long), frameOf(own));

    expect(REPORT_MAX).toBe(2000);
    expect(SOURCE_MAX).toBe(300);
    expect(taken?.message).toBe("m".repeat(2000));
    expect(taken?.source).toBe("s".repeat(300));
  });

  it("never cuts between the two halves of a character outside the basic plane", () => {
    const message = `${"x".repeat(1999)}😀`;
    const taken = parseFrameMessage(messageFrom(own, { ...report, message }), frameOf(own));

    expect(taken?.message).toBe("x".repeat(1999));
  });

  it("names no file when the page gave none that is text", () => {
    const frame = frameOf(own);
    for (const source of [undefined, null, 5, {}, []]) {
      expect(parseFrameMessage(messageFrom(own, { ...report, source }), frame)?.source).toBe("");
    }
  });

  it("turns a position that is not a count into 0, and cuts a fraction down", () => {
    const frame = frameOf(own);
    const odd = [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, -4, "7", null, undefined, {}];
    for (const value of odd) {
      const taken = parseFrameMessage(messageFrom(own, { ...report, line: value, column: value }), frame);
      expect(taken).toMatchObject({ line: 0, column: 0 });
    }
    const fraction = parseFrameMessage(messageFrom(own, { ...report, line: 3.9, column: 7.2 }), frame);
    expect(fraction).toMatchObject({ line: 3, column: 7 });
  });

  it("turns a position too large to be a count into 0, and keeps the largest that is one", () => {
    const frame = frameOf(own);
    for (const value of [1e308, Number.MAX_VALUE, 1e21, 2 ** 53]) {
      const taken = parseFrameMessage(messageFrom(own, { ...report, line: value, column: value }), frame);
      expect(taken).toMatchObject({ line: 0, column: 0 });
      // What the list would show for it: the file alone, and no `1e+308` after it.
      expect(taken && where(taken)).toBe("page.html");
    }
    const largest = Number.MAX_SAFE_INTEGER;
    const kept = parseFrameMessage(messageFrom(own, { ...report, line: largest, column: largest }), frame);
    expect(kept).toMatchObject({ line: largest, column: largest });
    expect(kept && where(kept)).toBe("page.html:9007199254740991:9007199254740991");
  });

  it("keeps nothing of the page beyond the four fields", () => {
    const taken = parseFrameMessage(messageFrom(own, { ...report, html: "<img onerror=x>", extra: 1 }), frameOf(own));

    expect(Object.keys(taken ?? {}).sort()).toEqual(["column", "line", "message", "source"]);
  });
});

describe("the hello of a page's reporter", () => {
  const port = { name: "first" } as unknown as MessagePort;
  const other = { name: "second" } as unknown as MessagePort;
  const hello = (ports: MessagePort[], source: unknown = own, origin = "null") =>
    ({ source, origin, data: { type: "canvas-hello" }, ports }) as unknown as MessageEvent;

  it("hands over the port it carries, and is no report", () => {
    const read = readFrameMessage(hello([port]), frameOf(own));

    expect(read?.port).toBe(port);
    expect(read?.error).toBeUndefined();
  });

  it("hands over the first port of several, and nothing when it carries none", () => {
    expect(readFrameMessage(hello([port, other]), frameOf(own))?.port).toBe(port);
    expect(readFrameMessage(hello([]), frameOf(own))).toBeNull();
  });

  it("hands nothing over from another window, from nowhere, or under an origin that is not null", () => {
    const frame = frameOf(own);

    expect(readFrameMessage(hello([port], {} as Window), frame)).toBeNull();
    expect(readFrameMessage(hello([port], null), frame)).toBeNull();
    expect(readFrameMessage(hello([port], null), frameOf(null))).toBeNull();
    expect(readFrameMessage(hello([port], own, window.location.origin), frame)).toBeNull();
    expect(readFrameMessage(hello([port], own, ""), frame)).toBeNull();
  });

  it("takes no port from a report that carries one", () => {
    const carrying = { source: own, origin: "null", data: report, ports: [port] } as unknown as MessageEvent;
    const read = readFrameMessage(carrying, frameOf(own));

    expect(read?.error).toEqual({ message: "boom", source: "page.html", line: 3, column: 7 });
    expect(read?.port).toBeUndefined();
  });

  it("reads what a message carries once, whatever the message is", () => {
    for (const data of [{ type: "canvas-hello" }, report, { type: "press" }, "x"]) {
      let read = 0;
      const event = {
        source: own,
        origin: "null",
        ports: [port],
        get data() {
          read += 1;
          return data;
        },
      } as unknown as MessageEvent;

      readFrameMessage(event, frameOf(own));

      expect(read).toBe(1);
    }
  });

  it("reads nothing of a message that is not the frame's own", () => {
    let read = 0;
    const event = (source: Window, origin: string) =>
      ({
        source,
        origin,
        ports: [port],
        get data() {
          read += 1;
          return report;
        },
      }) as unknown as MessageEvent;

    expect(readFrameMessage(event({} as Window, "null"), frameOf(own))).toBeNull();
    expect(readFrameMessage(event(own, "https://example.com"), frameOf(own))).toBeNull();
    expect(read).toBe(0);
  });
});

describe("what a page's reporter says over the port", () => {
  it("is a press when it is an object of that type", () => {
    expect(isPress({ type: "press" })).toBe(true);
    expect(isPress({ type: "press", more: 1 })).toBe(true);
  });

  it("is nothing else", () => {
    for (const data of ["press", null, undefined, 1, true, {}, ["press"], { type: "Press" }, { type: "canvas-hello" }, { kind: "press" }]) {
      expect(isPress(data)).toBe(false);
    }
  });

  it("is not a report: the word press on the window comes to nothing", () => {
    expect(readFrameMessage(messageFrom(own, { type: "press" }), frameOf(own))).toBeNull();
  });
});

describe("where a page says its error is", () => {
  it("writes the file, the line and the column as far as the page gave them", () => {
    expect(where({ message: "", source: "a.js", line: 3, column: 7 })).toBe("a.js:3:7");
    expect(where({ message: "", source: "a.js", line: 3, column: 0 })).toBe("a.js:3");
    expect(where({ message: "", source: "a.js", line: 0, column: 0 })).toBe("a.js");
    expect(where({ message: "", source: "", line: 3, column: 7 })).toBe("3:7");
    expect(where({ message: "", source: "", line: 0, column: 0 })).toBe("");
  });

  it("names no column of a line that was not given", () => {
    expect(where({ message: "", source: "a.js", line: 0, column: 9 })).toBe("a.js");
  });
});

describe("a file the page asked for that did not arrive", () => {
  it("is the reporter's own wording with no line", () => {
    const failed = { message: "failed to load https://x.test/a.png", source: "", line: 0, column: 0 };

    expect(isLoadFailure(failed)).toBe(true);
  });

  it("is not a script's error that happens to say the same, which names its line", () => {
    expect(isLoadFailure({ message: "failed to load the data", source: "a.js", line: 4, column: 2 })).toBe(false);
    expect(isLoadFailure({ message: "TypeError: x is undefined", source: "", line: 0, column: 0 })).toBe(false);
  });
});
