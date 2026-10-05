import { act, renderHook } from "@testing-library/react";
import { useLayoutEffect } from "react";
import { describe, expect, it, vi as vitest } from "vitest";
import type { DockView } from "../lib/canvas-dock-state";
import type { ThreadItem, ToolStatus } from "../state/thread-reducer";
import type { WritingPreview } from "../state/writing-previews";
import { useCanvasWriting } from "./use-canvas-writing";

const NOTE = "0123456789ab";
const SHOP = "ba9876543210";
const PLAN = "00ff00ff00ff";

/** What the tab knows of its canvases, as the dock's list answers. */
const TITLES: Record<string, string> = { [NOTE]: "Ghi chú" };
const KINDS: Record<string, string> = { [NOTE]: "code" };

/** A new canvas the model has written the start of, in two pieces unless said. */
const making = (fields: Partial<WritingPreview> = {}): WritingPreview => ({
  key: 1,
  index: 0,
  name: "artifact_create",
  text: '{"title":"Kế hoạch","kind":"markdown","content":"Việc một',
  attempt: 0,
  callId: null,
  updates: 2,
  ...fields,
});

/** Canvas `id` being written again. */
const rewriting = (id = NOTE, fields: Partial<WritingPreview> = {}) =>
  making({ name: "artifact_rewrite", text: `{"id":"${id}","content":"Bản mới`, ...fields });

const call = (status: ToolStatus, output: string | null = null, id = "w1"): ThreadItem => ({
  kind: "tool",
  id,
  name: "artifact_create",
  arguments: {},
  output,
  status,
});

const tag = (id: string, version = 1) => `[artifact ${id} v${version}]\nCanvas was written.`;

type Props = {
  previews: WritingPreview[];
  items: ThreadItem[];
  /** What the thread says of the turn: the person put a canvas being written away in it. */
  muted: boolean;
  wide: boolean;
  enabled: boolean;
  view: DockView;
  artifactId: string | null;
  /** A canvas asked for as the screen is drawn, before the hook has seen to what that drawing changed. */
  ask: number | null;
};

/** The hook beside a dock that stands where the test puts it, with a person who may have the
 *  keyboard in the dock (`typing`) or text of their own in its canvas (`editing`, which is both).
 *  The dock's list is another object each time the screen is drawn, as the real one is. The thread
 *  is told when the person puts a canvas away and says so from then on, until the test ends the turn. */
function mount(initial: Partial<Props> = {}) {
  const person = { typing: false, editing: false };
  const mutePreviews = vitest.fn(() => set({ muted: true }));
  const dock = {
    open: vitest.fn(),
    typing: vitest.fn(() => person.typing || person.editing),
    editing: vitest.fn(() => person.editing),
    selectTab: vitest.fn(),
    list: { titleOf: (id: string) => TITLES[id] ?? null, kindOf: (id: string) => KINDS[id] ?? null },
  };
  let props: Props = {
    previews: [],
    items: [],
    muted: false,
    wide: true,
    enabled: true,
    view: "closed",
    artifactId: null,
    ask: null,
    ...initial,
  };
  const view = renderHook(
    (now: Props) => {
      const writing = useCanvasWriting(
        { state: { previews: now.previews, items: now.items, previewsMuted: now.muted }, mutePreviews },
        { ...dock, list: { ...dock.list }, view: now.view, artifactId: now.artifactId },
        now.wide,
        now.enabled,
      );
      const { show } = writing;
      useLayoutEffect(() => {
        if (now.ask !== null) show(now.ask);
      }, [now.ask, show]);
      return writing;
    },
    { initialProps: props },
  );
  const set = (next: Partial<Props>) => {
    props = { ...props, ...next };
    view.rerender(props);
  };
  return { result: view.result, dock, person, set, mutePreviews };
}

describe("the canvases being written, for the thread", () => {
  it("lists what each open one says of its canvas so far", () => {
    const { result } = mount({ previews: [making({ updates: 1 }), rewriting(NOTE, { key: 2, index: 1, updates: 1 })] });

    expect(result.current.items).toEqual([
      { key: 1, callId: null, updates: 1, rewrite: false, id: null, title: "Kế hoạch", kind: "markdown", content: "Việc một", bytes: 12 },
      { key: 2, callId: null, updates: 1, rewrite: true, id: NOTE, title: "Ghi chú", kind: "code", content: "Bản mới", bytes: 11 },
    ]);
    expect(result.current.shown).toBeNull();
    expect(result.current.asked).toBeNull();
    expect(result.current.callId).toBeNull();
  });

  it("leaves out one whose call the answer has named: the thread shows that call instead", () => {
    const { result } = mount({ previews: [making({ callId: "w1" }), making({ key: 2, index: 1, updates: 1 })] });
    expect(result.current.items.map((item) => item.key)).toEqual([2]);
  });

  it("reads each once for every piece that arrives, however often the screen is drawn", () => {
    const { result, set } = mount({ previews: [making()] });
    const before = result.current.items;

    set({ wide: false });

    expect(result.current.items).toBe(before);
  });

  it("lists nothing and shows nothing when the preview is turned off", () => {
    const { result, dock } = mount({ previews: [making()], enabled: false });

    expect(result.current.items).toEqual([]);
    expect(result.current.shown).toBeNull();
    expect(dock.selectTab).not.toHaveBeenCalled();
  });

  it("stops listing them the moment the preview is turned off, and lists them again once it is back on", () => {
    const { result, set } = mount({ previews: [making({ updates: 1 })] });
    expect(result.current.items.map((item) => item.key)).toEqual([1]);

    set({ enabled: false });
    expect(result.current.items).toEqual([]);

    set({ enabled: true });
    expect(result.current.items.map((item) => item.key)).toEqual([1]);
  });
});

describe("a new canvas coming up by itself", () => {
  it("waits for the second piece, then shows without having been asked", () => {
    const { result, dock, set } = mount({ previews: [making({ updates: 1 })] });
    expect(result.current.shown).toBeNull();

    set({ previews: [making()] });

    expect(result.current.shown).toMatchObject({ key: 1, content: "Việc một" });
    expect(result.current.asked).toBeNull();
    expect(dock.selectTab).toHaveBeenCalledTimes(1);
    expect(dock.selectTab).toHaveBeenCalledWith("canvas");
    expect(dock.open).not.toHaveBeenCalled();
  });

  it("waits for text, however many pieces came without any", () => {
    const { result, set } = mount({ previews: [making({ text: '{"title":"Kế hoạch"', updates: 3 })] });
    expect(result.current.shown).toBeNull();

    set({ previews: [making({ text: '{"title":"Kế hoạch","content":"V', updates: 4 })] });

    expect(result.current.shown).toMatchObject({ key: 1, content: "V" });
  });

  it("follows the text as more of it arrives", () => {
    const { result, set } = mount({ previews: [making()] });

    set({ previews: [making({ text: '{"title":"Kế hoạch","kind":"markdown","content":"Việc một\\nViệc hai', updates: 3 })] });

    expect(result.current.shown).toMatchObject({ key: 1, content: "Việc một\nViệc hai", updates: 3 });
  });

  it("does not come up on a narrow screen, nor later when the screen widens", () => {
    const { result, dock, set } = mount({ previews: [making()], wide: false });
    expect(result.current.shown).toBeNull();

    set({ wide: true, previews: [making({ updates: 3 })] });

    expect(result.current.shown).toBeNull();
    expect(dock.selectTab).not.toHaveBeenCalled();
  });

  it("does not come up over what the person is typing in a canvas, nor once they stop", () => {
    const { result, person, set } = mount({ previews: [], view: "canvas", artifactId: SHOP });
    person.typing = true;
    set({ previews: [making()] });
    expect(result.current.shown).toBeNull();

    person.typing = false;
    set({ previews: [making({ updates: 3 })] });

    expect(result.current.shown).toBeNull();
  });

  it("does not come up for a call the answer has already named", () => {
    const { result } = mount({ previews: [making({ callId: "w1" })], items: [call("running")] });
    expect(result.current.shown).toBeNull();
  });

  it("leaves the one on show alone when a second canvas starts, and never puts the second in its place", () => {
    const { result, set } = mount({ previews: [making()] });
    const second = making({ key: 2, index: 1 });

    set({ previews: [making(), second] });
    expect(result.current.shown).toMatchObject({ key: 1 });

    set({ previews: [{ ...second, updates: 3 }] });
    expect(result.current.shown).toBeNull();
  });

  it("shows the first of two that become ready in the same piece", () => {
    const { result, dock } = mount({ previews: [making(), making({ key: 2, index: 1 })] });

    expect(result.current.shown).toMatchObject({ key: 1 });
    expect(dock.selectTab).toHaveBeenCalledTimes(1);
  });
});

describe("a canvas written again coming up by itself", () => {
  it("shows over the canvas it is rewriting when that is the one open", () => {
    const { result, dock } = mount({ previews: [rewriting()], view: "canvas", artifactId: NOTE });

    expect(result.current.shown).toMatchObject({ key: 1, rewrite: true, id: NOTE, title: "Ghi chú" });
    expect(result.current.asked).toBeNull();
    expect(dock.selectTab).toHaveBeenCalledWith("canvas");
  });

  it("does not show while another canvas is open", () => {
    const { result } = mount({ previews: [rewriting(SHOP)], view: "canvas", artifactId: NOTE });
    expect(result.current.shown).toBeNull();
  });

  it("does not show while the dock is closed or on its list", () => {
    expect(mount({ previews: [rewriting()] }).result.current.shown).toBeNull();
    expect(mount({ previews: [rewriting()], view: "list" }).result.current.shown).toBeNull();
  });

  it("does not show before the call has said which canvas it writes", () => {
    const unnamed = rewriting(NOTE, { text: '{"content":"Bản mới' });
    const { result } = mount({ previews: [unnamed], view: "canvas", artifactId: NOTE });
    expect(result.current.shown).toBeNull();
    // Naming no canvas is not naming the one a dock that holds none has open.
    expect(mount({ previews: [unnamed] }).result.current.shown).toBeNull();
    expect(mount({ previews: [unnamed], view: "list" }).result.current.shown).toBeNull();
  });

  it("does not show over what the person is typing there", () => {
    const { result, person, set } = mount({ view: "canvas", artifactId: NOTE });
    person.typing = true;

    set({ previews: [rewriting()] });

    expect(result.current.shown).toBeNull();
  });
});

describe("a canvas being written shown on request", () => {
  it("shows on a narrow screen from its first piece, and counts the asking", () => {
    const { result, dock } = mount({ previews: [making({ text: '{"title":"Kế', updates: 1 })], wide: false });

    act(() => result.current.show(1));

    expect(result.current.shown).toMatchObject({ key: 1, title: null, content: "" });
    expect(result.current.asked).toBe(1);
    expect(dock.selectTab).toHaveBeenCalledWith("canvas");
    expect(dock.open).not.toHaveBeenCalled();

    act(() => result.current.show(1));
    expect(result.current.asked).toBe(2);
  });

  it("shows over what the person is typing, since they asked", () => {
    const { result, person } = mount({ previews: [making({ updates: 1 })], view: "canvas", artifactId: SHOP });
    person.typing = true;

    act(() => result.current.show(1));

    expect(result.current.shown).toMatchObject({ key: 1 });
  });

  it("takes the place of the one that came up by itself", () => {
    const { result } = mount({ previews: [making(), making({ key: 2, index: 1 })] });

    act(() => result.current.show(2));

    expect(result.current.shown).toMatchObject({ key: 2 });
    expect(result.current.asked).toBe(1);
  });

  it("does not come up by itself afterwards, once the dock has moved on from it", () => {
    const { result, set } = mount({ previews: [making({ updates: 1 })] });
    act(() => result.current.show(1));

    set({ view: "list" });
    expect(result.current.shown).toBeNull();

    set({ view: "closed", previews: [making()] });
    expect(result.current.shown).toBeNull();
  });

  it("shows the one asked for in the very drawing that dropped the one on show", () => {
    const { result, set } = mount({ previews: [making()] });
    expect(result.current.shown).toMatchObject({ key: 1 });

    // The model starts over with another canvas, and the request lands before the hook has
    // put away the one that is gone: putting that away must not take the one asked for with it.
    set({ previews: [making({ key: 2, attempt: 1, updates: 1 })], ask: 2 });

    expect(result.current.shown).toMatchObject({ key: 2 });
    expect(result.current.asked).toBe(1);
  });

  it("shows nothing for a canvas that is no longer being written", () => {
    const { result } = mount({ previews: [making()], wide: false });

    act(() => result.current.show(9));

    expect(result.current.shown).toBeNull();
    expect(result.current.asked).toBeNull();
  });
});

describe("leaving a canvas being written", () => {
  it("puts it away, tells the thread, and keeps the rest of the turn from coming up by itself", () => {
    const { result, set, mutePreviews } = mount({ previews: [making()] });

    act(() => result.current.leave());
    expect(result.current.shown).toBeNull();
    expect(result.current.items.map((item) => item.key)).toEqual([1]);
    expect(mutePreviews).toHaveBeenCalledTimes(1);

    // The model starts its answer over: another canvas, in the same turn.
    set({ previews: [making({ key: 2, attempt: 1 })] });
    expect(result.current.shown).toBeNull();

    act(() => result.current.show(2));
    expect(result.current.shown).toMatchObject({ key: 2 });
  });

  it("lets the next turn's canvas come up again, once the thread has forgotten the one put away", () => {
    const { result, set } = mount({ previews: [making()] });
    act(() => result.current.leave());

    set({ previews: [], muted: false });
    set({ previews: [making({ key: 2 })] });

    expect(result.current.shown).toMatchObject({ key: 2 });
    expect(result.current.asked).toBeNull();
  });

  it("holds for a screen drawn anew in that turn, which has seen none of it: the thread remembers", () => {
    const { result, dock, set } = mount({ previews: [making()], muted: true });
    expect(result.current.shown).toBeNull();
    expect(result.current.items.map((item) => item.key)).toEqual([1]);

    set({ previews: [making({ updates: 3 }), making({ key: 2, index: 1 })] });
    expect(result.current.shown).toBeNull();
    expect(dock.selectTab).not.toHaveBeenCalled();

    act(() => result.current.show(1));
    expect(result.current.shown).toMatchObject({ key: 1 });
  });

  it("tells the thread again each time one shown on request is put away", () => {
    const { result, mutePreviews } = mount({ previews: [making()] });
    act(() => result.current.leave());
    act(() => result.current.show(1));

    act(() => result.current.leave());

    expect(result.current.shown).toBeNull();
    expect(mutePreviews).toHaveBeenCalledTimes(2);
  });

  it("tells the thread nothing when a canvas goes by itself", () => {
    const { result, set, mutePreviews } = mount({ previews: [making()] });

    // The model starts over, and the dock moves on from the next one: neither is the person's doing.
    set({ previews: [] });
    expect(result.current.shown).toBeNull();
    set({ previews: [making({ key: 2 })] });
    expect(result.current.shown).toMatchObject({ key: 2 });
    set({ view: "list" });

    expect(result.current.shown).toBeNull();
    expect(mutePreviews).not.toHaveBeenCalled();
  });
});

describe("what puts a canvas being written away by itself", () => {
  it("goes when the model starts over and its preview is dropped", () => {
    const { result, set } = mount({ previews: [making()] });

    set({ previews: [] });

    expect(result.current.shown).toBeNull();
    expect(result.current.callId).toBeNull();
  });

  it("goes when the dock moves, and does not come back when the dock returns", () => {
    const { result, set } = mount({ previews: [making()] });

    set({ view: "list" });
    expect(result.current.shown).toBeNull();

    set({ view: "closed", previews: [making({ updates: 3 })] });
    expect(result.current.shown).toBeNull();
  });

  it("goes when the dock opens another canvas than the one it stood on", () => {
    const { result, set } = mount({ previews: [rewriting()], view: "canvas", artifactId: NOTE });
    expect(result.current.shown).not.toBeNull();

    set({ artifactId: SHOP });
    expect(result.current.shown).toBeNull();

    set({ artifactId: NOTE });
    expect(result.current.shown).toBeNull();
  });

  it("goes when the preview is turned off", () => {
    const { result, set } = mount({ previews: [making()] });

    set({ enabled: false });
    expect(result.current.shown).toBeNull();

    set({ enabled: true });
    expect(result.current.shown).toBeNull();
  });
});

describe("the end of a canvas being written", () => {
  const bound = making({ callId: "w1" });

  /** A new canvas on show whose call the answer has named and started. */
  function ending(initial: Partial<Props> = {}) {
    const mounted = mount({ previews: [making()], ...initial });
    mounted.set({ previews: [bound], items: [call("running")] });
    return mounted;
  }

  it("stays on show through the call, and names the call it became", () => {
    const { result, dock, set } = ending();
    expect(result.current.shown).toMatchObject({ key: 1, callId: "w1" });
    expect(result.current.callId).toBe("w1");
    expect(result.current.items).toEqual([]);

    set({ items: [call("awaiting")] });

    expect(result.current.shown).toMatchObject({ key: 1 });
    expect(dock.open).not.toHaveBeenCalled();
  });

  it("opens the canvas the call made, quietly and once, and is put away", () => {
    const { result, dock, set } = ending();

    set({ items: [call("done", tag(PLAN))] });

    expect(dock.open).toHaveBeenCalledTimes(1);
    expect(dock.open).toHaveBeenCalledWith(PLAN, { quiet: true });
    expect(result.current.shown).toBeNull();
    expect(result.current.callId).toBeNull();

    set({ view: "canvas", artifactId: PLAN });
    set({ previews: [], items: [call("done", tag(PLAN)), { kind: "assistant", id: "a2", text: "Xong.", model: null }] });
    expect(dock.open).toHaveBeenCalledTimes(1);
  });

  it("opens the canvas the result names, whatever the call said it would write", () => {
    const { result, dock, set } = mount({ previews: [rewriting(SHOP, { updates: 1 })] });
    act(() => result.current.show(1));
    set({ previews: [rewriting(SHOP, { updates: 1, callId: "w1" })], items: [call("running")] });

    set({ items: [call("done", tag(PLAN, 3))] });

    expect(dock.open.mock.calls).toEqual([[PLAN, { quiet: true }]]);
  });

  it.each(["failed", "denied", "stopped"] as const)("is put away and opens nothing when the call ends %s", (status) => {
    const { result, dock, set } = ending();

    set({ items: [call(status, tag(PLAN))] });

    expect(result.current.shown).toBeNull();
    expect(dock.open).not.toHaveBeenCalled();
  });

  it("opens nothing when the result names no canvas", () => {
    const { result, dock, set } = ending();

    set({ items: [call("done", "Không có gì để viết.")] });

    expect(result.current.shown).toBeNull();
    expect(dock.open).not.toHaveBeenCalled();
  });

  it("opens nothing over what the person has typed meanwhile", () => {
    const { result, dock, person, set } = ending();
    person.editing = true;

    set({ items: [call("done", tag(PLAN))] });

    expect(result.current.shown).toBeNull();
    expect(dock.open).not.toHaveBeenCalled();
  });

  it("opens the canvas when the keyboard is in the dock and the person typed nothing there", () => {
    const { result, dock, person, set } = ending();
    person.typing = true;

    set({ items: [call("done", tag(PLAN))] });

    expect(result.current.shown).toBeNull();
    expect(dock.open).toHaveBeenCalledTimes(1);
    expect(dock.open).toHaveBeenCalledWith(PLAN, { quiet: true });
  });

  it("gives way to the canvas it rewrote, which is open already", () => {
    const { result, dock, set } = mount({ previews: [rewriting()], view: "canvas", artifactId: NOTE });
    set({ previews: [rewriting(NOTE, { callId: "w1" })], items: [call("running")] });
    expect(result.current.shown).not.toBeNull();

    set({ items: [call("done", tag(NOTE, 2))] });

    expect(result.current.shown).toBeNull();
    expect(dock.open).not.toHaveBeenCalled();
  });

  it("does not silence the canvas that comes after one that failed", () => {
    const { result, set } = ending();
    set({ items: [call("failed")] });

    set({ previews: [making({ key: 2 })] });

    expect(result.current.shown).toMatchObject({ key: 2 });
  });

  it("minds only its own call", () => {
    const { result, dock, set } = ending();

    set({ items: [call("running"), call("done", tag(SHOP), "w0")] });

    expect(result.current.shown).toMatchObject({ key: 1 });
    expect(dock.open).not.toHaveBeenCalled();
  });
});
