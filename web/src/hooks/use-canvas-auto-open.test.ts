import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import type { ThreadItem, ToolStatus } from "../state/thread-reducer";
import { useCanvasAutoOpen } from "./use-canvas-auto-open";

const NOTE = "0123456789ab";
const SHOP = "ba9876543210";
const PLAN = "00ff00ff00ff";

type Tool = Extract<ThreadItem, { kind: "tool" }>;
type Detail = { messages: { tool_calls: { id: string }[] }[] } | null;
type Props = { items: ThreadItem[]; detail: Detail; wide: boolean };

const tag = (id: string, version = 1) => `[artifact ${id} v${version}]`;

function call(id: string, name: string, status: ToolStatus, fields: Partial<Tool> = {}): Tool {
  return { kind: "tool", id, name, arguments: {}, output: status === "done" ? "ok" : null, status, ...fields };
}

/** A canvas made: the tag opens a finished call's result, as the server writes it. */
const made = (id: string, canvas = NOTE, status: ToolStatus = "done") =>
  call(id, "artifact_create", status, { output: status === "done" ? `${tag(canvas)}\nCanvas was created.` : null });

const history = (...ids: string[]): Detail => ({ messages: [{ tool_calls: ids.map((id) => ({ id })) }] });

/** The hook as the chat screen runs it: a dock whose `typing` the test can change, `open` recorded. */
function mount(initial: Partial<Props> = {}) {
  const person = { typing: false };
  const dock = { open: vitest.fn(), typing: vitest.fn(() => person.typing) };
  let props: Props = { items: [], detail: null, wide: true, ...initial };
  const view = renderHook(
    (now: Props) => useCanvasAutoOpen({ state: { items: now.items }, detail: now.detail }, dock, now.wide),
    { initialProps: props },
  );
  const update = (next: Partial<Props>) => {
    props = { ...props, ...next };
    view.rerender(props);
  };
  return { dock, person, update };
}

const opened = (dock: { open: { mock: { calls: unknown[][] } } }) => dock.open.mock.calls;

describe("opening the canvas an agent just made", () => {
  it("opens it quietly, once the call is done in a turn this tab is showing", () => {
    const { dock, update } = mount();

    update({ items: [made("c1")] });

    expect(opened(dock)).toEqual([[NOTE, { quiet: true }]]);
  });

  it("does not open it a second time however often the thread draws again", () => {
    const { dock, update } = mount();
    update({ items: [made("c1")] });

    update({ items: [made("c1"), made("c9", SHOP, "running")] });
    update({ items: [{ ...made("c1") }, { kind: "assistant", id: "m2", text: "xong", model: null }] });
    update({ wide: false });
    update({ wide: true });

    expect(opened(dock)).toEqual([[NOTE, { quiet: true }]]);
  });

  it("opens each of two canvases made in one draw, in the order they were made", () => {
    const { dock, update } = mount();

    update({ items: [made("c1", NOTE), made("c2", SHOP)] });

    expect(opened(dock)).toEqual([
      [NOTE, { quiet: true }],
      [SHOP, { quiet: true }],
    ]);
  });

  it("takes the canvas the tag names, whatever the arguments say", () => {
    const { dock, update } = mount();

    update({ items: [{ ...made("c1", PLAN), arguments: { id: NOTE, title: "x" } }] });

    expect(opened(dock)).toEqual([[PLAN, { quiet: true }]]);
  });

  it("needs the tag at the start of the result to name a canvas", () => {
    const { dock, update } = mount();
    const untagged = [
      call("c1", "artifact_create", "done", { output: "Canvas created." }),
      call("c2", "artifact_create", "done", { output: `ok ${tag(NOTE)}` }),
      call("c3", "artifact_create", "done", { output: "[artifact 0123456789AB v1]" }),
      call("c4", "artifact_create", "done", { output: "[artifact a1 v1]" }),
      call("c5", "artifact_create", "done", { output: "", arguments: { id: NOTE } }),
    ];

    update({ items: untagged });

    expect(opened(dock)).toEqual([]);
  });

  it("opens it with no detail loaded, as for a first turn in a conversation just made", () => {
    const { dock, update } = mount({ detail: null });

    update({ items: [made("c1")] });

    expect(opened(dock)).toEqual([[NOTE, { quiet: true }]]);
  });
});

describe("what never opens by itself", () => {
  it("is an edit or a rewrite, which change a canvas the person may not be reading", () => {
    const { dock, update } = mount();

    update({
      items: [
        call("c1", "artifact_edit", "done", { output: `${tag(NOTE, 2)}\nok` }),
        call("c2", "artifact_rewrite", "done", { output: `${tag(NOTE, 3)}\nok` }),
        call("c3", "artifact_read", "done", { output: "text" }),
        call("c4", "web_search", "done", { output: `${tag(NOTE)}` }),
      ],
    });

    expect(opened(dock)).toEqual([]);
  });

  it.each<ToolStatus>(["failed", "denied", "stopped"])("is a create that %s", (status) => {
    const { dock, update } = mount();

    update({ items: [{ ...made("c1"), status, output: `${tag(NOTE)}\nok` }] });
    update({ items: [{ ...made("c1"), status, output: `${tag(NOTE)}\nok` }, made("c2", SHOP, "running")] });

    expect(opened(dock)).toEqual([]);
  });

  it("is a canvas made in a conversation this tab only read, whether it came with the mount or a load", () => {
    const old = [made("c1", NOTE), made("c2", SHOP)];
    const { dock, update } = mount({ items: [old[0]], detail: history("c1") });

    update({ items: [], detail: null });
    update({ items: old, detail: history("c1", "c2") });

    expect(opened(dock)).toEqual([]);
  });

  it("is a canvas made before this screen was drawn, which is not this tab's turn to announce", () => {
    const { dock, update } = mount({ items: [made("c1"), made("c2", SHOP, "running")], detail: null });

    update({ items: [made("c1"), made("c2", SHOP)] });
    update({ items: [made("c1"), made("c2", SHOP), made("c3", PLAN)] });

    expect(opened(dock)).toEqual([[PLAN, { quiet: true }]]);
  });

  it("is a canvas on a screen too narrow to hold it beside the thread, even after the screen widens", () => {
    const { dock, update } = mount({ wide: false });

    update({ items: [made("c1")] });
    update({ wide: true });
    update({ items: [made("c1"), made("c2", SHOP, "running")] });

    expect(opened(dock)).toEqual([]);
  });

  it("is a canvas finished while the person was typing, even after they stop", () => {
    const { dock, person, update } = mount();
    person.typing = true;

    update({ items: [made("c1")] });
    person.typing = false;
    update({ items: [made("c1"), { kind: "assistant", id: "m2", text: "xong", model: null }] });

    expect(opened(dock)).toEqual([]);
    expect(dock.typing).toHaveBeenCalledTimes(1);
  });
});

describe("a call that is not finished", () => {
  it("is passed over while it runs, and judged once it is done", () => {
    const { dock, update } = mount();

    update({ items: [made("c1", NOTE, "running")] });
    expect(opened(dock)).toEqual([]);
    update({ items: [made("c1", NOTE, "running"), made("c1b", SHOP, "running")] });
    expect(opened(dock)).toEqual([]);
    update({ items: [made("c1"), made("c1b", SHOP, "running")] });

    expect(opened(dock)).toEqual([[NOTE, { quiet: true }]]);
  });

  it("is passed over while it waits to be allowed, and opens once it is done", () => {
    const { dock, update } = mount();

    update({ items: [made("c1", NOTE, "awaiting")] });
    expect(opened(dock)).toEqual([]);
    update({ items: [made("c1", NOTE, "running")] });
    expect(opened(dock)).toEqual([]);
    update({ items: [made("c1")] });

    expect(opened(dock)).toEqual([[NOTE, { quiet: true }]]);
  });

  it("is judged by how the person was when it ended, not when it began", () => {
    const { dock, person, update } = mount();
    person.typing = true;
    update({ items: [made("c1", NOTE, "running")] });
    person.typing = false;

    update({ items: [made("c1")] });

    expect(opened(dock)).toEqual([[NOTE, { quiet: true }]]);
  });
});

describe("a call the conversation's saved history holds", () => {
  it("is not this turn's, even when it shows up done in a thread the screen has not seen", () => {
    const { dock, update } = mount();

    update({ items: [made("c1")], detail: history("c1") });

    expect(opened(dock)).toEqual([]);
  });

  it("does not stop a call of this turn, which the history does not hold yet", () => {
    const { dock, update } = mount({ detail: history("c0") });

    update({ items: [made("c0", NOTE), made("c1", SHOP)], detail: history("c0") });

    expect(opened(dock)).toEqual([[SHOP, { quiet: true }]]);
  });

  it("is told apart by the call, not by the canvas it made", () => {
    const { dock, update } = mount({ detail: history("c0") });

    update({ items: [made("c1", NOTE)], detail: history("c0") });

    expect(opened(dock)).toEqual([[NOTE, { quiet: true }]]);
  });
});
