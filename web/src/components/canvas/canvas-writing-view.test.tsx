import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import type { WritingItem } from "../../lib/canvas-writing";
import { CanvasWritingView } from "./canvas-writing-view";

const text = vi.canvas.writing;

const item = (fields: Partial<WritingItem> = {}): WritingItem => ({
  key: 7,
  callId: null,
  updates: 2,
  rewrite: false,
  id: null,
  title: "Kế hoạch tuần",
  kind: "markdown",
  content: "# Việc một\n\n- mua rau",
  bytes: 24,
  ...fields,
});

/** The frame with a button outside it, where a person's keyboard may be. */
function Screen({ fields, asked, onLeave }: { fields: Partial<WritingItem>; asked: number | null; onLeave(): void }) {
  return (
    <>
      <button type="button">Ngoài khung</button>
      <CanvasWritingView item={item(fields)} asked={asked} onLeave={onLeave} />
    </>
  );
}

function open(fields: Partial<WritingItem> = {}, asked: number | null = null) {
  const onLeave = vitest.fn();
  const view = render(<Screen fields={fields} asked={asked} onLeave={onLeave} />);
  const again = (next: Partial<WritingItem>, nextAsked: number | null = asked) =>
    view.rerender(<Screen fields={next} asked={nextAsked} onLeave={onLeave} />);
  return { onLeave, again };
}

const frame = () => screen.getByTestId("canvas-writing");
const outside = () => screen.getByRole("button", { name: "Ngoài khung" });
const closeButton = () => within(frame()).getByRole("button", { name: text.close });
/** Where the canvas's text is drawn, apart from the frame's own head and its icon. */
const body = () => frame().querySelector(".canvas-body") as HTMLElement;

afterEach(() => vitest.unstubAllGlobals());

describe("the head of a canvas being written", () => {
  it("names the canvas and its kind", () => {
    open();

    expect(within(frame()).getByRole("heading", { level: 2, name: "Kế hoạch tuần" })).toBeInTheDocument();
    expect(frame().querySelector(".canvas-header .badge")).toHaveTextContent(vi.canvas.kinds.markdown);
  });

  it("names no kind while none is known, and stands a plain word in for a missing title", () => {
    open({ title: null, kind: null });

    expect(within(frame()).getByRole("heading", { level: 2, name: text.untitledNew })).toBeInTheDocument();
    expect(frame().querySelector(".badge")).toBeNull();
  });

  it("writes the characters that hide in a title as marks", () => {
    open({ title: `a${String.fromCharCode(0x202e)}b` });
    expect(within(frame()).getByRole("heading", { level: 2, name: "a[U+202E]b" })).toBeInTheDocument();
  });

  it("says nothing is saved while the agent writes, and that the saving is on once it has finished", () => {
    const { again } = open();
    expect(within(frame()).getByText(text.unsaved)).toBeInTheDocument();
    expect(within(frame()).queryByText(text.saving)).toBeNull();

    again({ callId: "w1" });

    expect(within(frame()).getByText(text.saving)).toBeInTheDocument();
    expect(within(frame()).queryByText(text.unsaved)).toBeNull();
  });

  it("has the change from writing to saving read out, in the one place that says it", () => {
    const { again } = open();
    const band = within(frame()).getByRole("status");
    expect(band).toHaveTextContent(text.unsaved);

    again({ callId: "w1" });

    expect(within(frame()).getByRole("status")).toBe(band);
    expect(band).toHaveTextContent(text.saving);
  });

  it("is left by its close button", () => {
    const { onLeave } = open();

    fireEvent.click(closeButton());

    expect(onLeave).toHaveBeenCalledTimes(1);
  });

  it("offers nothing else to press, type in or follow", () => {
    open({ content: "chữ thường" });

    expect(within(frame()).getAllByRole("button")).toEqual([closeButton()]);
    expect(within(frame()).queryByRole("textbox")).toBeNull();
    expect(within(frame()).queryByRole("link")).toBeNull();
  });
});

describe("the text of a canvas being written", () => {
  it("reads markdown as markdown", () => {
    open();

    expect(within(frame()).getByRole("heading", { level: 1, name: "Việc một" })).toBeInTheDocument();
    expect(within(frame()).getByRole("listitem")).toHaveTextContent("mua rau");
    expect(frame().querySelector("pre.canvas-code")).toBeNull();
    expect(within(frame()).queryByText(text.source)).toBeNull();
  });

  it("shows the HTML written inside markdown as text, and builds nothing from it", () => {
    open({ content: 'Trước <img src="https://x.test/a.png" onerror="alert(1)"> <script>window.pwned = 1</script> sau' });

    expect(frame().querySelector("img, script, iframe")).toBeNull();
    expect(frame()).toHaveTextContent("onerror");
  });

  it.each(["html", "svg", "mermaid"])("shows a canvas of kind %s as its source, and says so", (kind) => {
    const content = '<svg onload="alert(1)"><script>window.pwned = 1</script></svg>\n<b>đậm</b>';
    open({ kind, content });

    expect(body().querySelector("pre.canvas-code")?.textContent).toBe(content);
    expect(body().querySelector("iframe, svg, script, b")).toBeNull();
    expect(frame().querySelector("iframe, script, b")).toBeNull();
    expect(within(frame()).getByText(text.source)).toBeInTheDocument();
  });

  it.each([null, "code", "image"])("shows a canvas of kind %s as plain text, with nothing more to say", (kind) => {
    open({ kind, content: "# không phải tiêu đề\n<i>x</i>" });

    expect(frame().querySelector("pre.canvas-code")?.textContent).toBe("# không phải tiêu đề\n<i>x</i>");
    expect(frame().querySelector("h1, i, img, iframe")).toBeNull();
    expect(within(frame()).queryByText(text.source)).toBeNull();
  });

  it("writes the characters that hide in the text as marks", () => {
    open({ kind: "code", content: `x = 1${String.fromCharCode(0x200b)}` });
    expect(frame().querySelector("pre.canvas-code")?.textContent).toBe("x = 1[U+200B]");
  });
});

describe("the keyboard and a canvas being written", () => {
  it("stays where it was when the canvas came up by itself", () => {
    const { again } = open();
    expect(document.body).toHaveFocus();

    outside().focus();
    again({ content: "# Việc một\n\n- mua rau\n- mua cá" });

    expect(outside()).toHaveFocus();
  });

  it("goes to the close button when the person asked to see it", () => {
    open({}, 1);
    expect(closeButton()).toHaveFocus();
  });

  it("stays outside when more text arrives after the person moved on", () => {
    const { again } = open({}, 1);
    outside().focus();

    again({ content: "# Việc một\n\n- mua rau\n- mua cá" }, 1);

    expect(outside()).toHaveFocus();
  });

  it("comes back to the close button when the person asks again", () => {
    const { again } = open({}, 1);
    outside().focus();

    again({}, 2);

    expect(closeButton()).toHaveFocus();
  });

  it("is not taken from a link inside the frame when the person asks again", () => {
    const { again } = open({ content: "[trang](https://example.test)" }, 1);
    const link = within(frame()).getByRole("link", { name: "trang" });
    link.focus();

    again({ content: "[trang](https://example.test)" }, 2);

    expect(link).toHaveFocus();
  });

  it("stays outside when the request is withdrawn", () => {
    const { again } = open({}, 1);
    outside().focus();

    again({}, null);

    expect(outside()).toHaveFocus();
  });
});

/** The size observer jsdom lacks: it keeps the callback so a case can say the text grew. */
class FakeResizeObserver {
  static latest: FakeResizeObserver | null = null;
  constructor(readonly callback: () => void) {
    FakeResizeObserver.latest = this;
  }
  observe() {}
  disconnect() {}
}

describe("the place in a canvas being written", () => {
  /** jsdom lays nothing out, so the body reports the height each case is about. */
  function tall(area: HTMLElement, scrollHeight: number) {
    Object.defineProperty(area, "scrollHeight", { configurable: true, value: scrollHeight });
    Object.defineProperty(area, "clientHeight", { configurable: true, value: 300 });
  }
  const grew = () => act(() => FakeResizeObserver.latest?.callback());

  it("follows the last line as the text grows, until the person scrolls up to read", () => {
    FakeResizeObserver.latest = null;
    vitest.stubGlobal("ResizeObserver", FakeResizeObserver);
    const { again } = open();
    const area = body();

    tall(area, 900);
    grew();
    expect(area.scrollTop).toBe(900);

    area.scrollTop = 100;
    fireEvent.scroll(area);
    again({ content: "# Việc một\n\n- mua rau\n- mua cá" });
    tall(area, 1500);
    grew();

    expect(area.scrollTop).toBe(100);
  });
});
