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

const CHILD = "conversation=child1 status=done spent=$0.0100 steps=2";

/** What a handed-off task returns, as the server writes it: under the two lines that say how it
 *  went stand the canvases the other agent wrote, then a blank line, then its reply. */
const result = (canvases: string[], outcome = "outcome=done") =>
  [CHILD, outcome, ...canvases.map((id, at) => `${tag(id, at + 1)} Báo cáo ${at + 1}`), "", "Đã viết báo cáo."].join("\n");

/** A task handed to another agent, which wrote the canvases named, in that order. */
const handed = (id: string, canvases: string[], status: ToolStatus = "done", fields: Partial<Tool> = {}) =>
  call(id, "delegate", status, {
    arguments: { agent: "researcher", task: "viết báo cáo tuần" },
    output: status === "running" || status === "awaiting" ? null : result(canvases),
    ...fields,
  });

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
    const { dock, update } = mount({ items: [made("c1"), handed("d1", [SHOP])], detail: null });
    expect(opened(dock)).toEqual([]);

    update({ items: [made("c1"), handed("d1", [SHOP]), made("c3", PLAN)] });

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

describe("a call still going when the screen was drawn, as when the person comes back to the chat mid-turn", () => {
  it("opens its canvas when it ends, for this tab watched it being made", () => {
    const { dock, update } = mount({ items: [made("c1"), made("c2", SHOP, "running")], detail: null });
    expect(opened(dock)).toEqual([]);

    update({ items: [made("c1"), made("c2", SHOP)] });

    expect(opened(dock)).toEqual([[SHOP, { quiet: true }]]);
  });

  it("opens the canvas of one that waited to be allowed, once it is done", () => {
    const { dock, update } = mount({ items: [made("c1", NOTE, "awaiting")], detail: null });

    update({ items: [made("c1", NOTE, "running")] });
    expect(opened(dock)).toEqual([]);
    update({ items: [made("c1")] });

    expect(opened(dock)).toEqual([[NOTE, { quiet: true }]]);
  });

  it("opens the canvas a task handed off before the screen was drawn wrote, once the task ends", () => {
    const { dock, update } = mount({ items: [handed("d1", [PLAN], "running")], detail: null });

    update({ items: [handed("d1", [PLAN, SHOP])] });

    expect(opened(dock)).toEqual([[PLAN, { quiet: true }]]);
  });

  it("opens only the once, however often the thread draws again", () => {
    const { dock, update } = mount({ items: [made("c1", NOTE, "running")], detail: null });
    update({ items: [made("c1")] });

    update({ items: [{ ...made("c1") }, { kind: "assistant", id: "m2", text: "xong", model: null }] });

    expect(opened(dock)).toEqual([[NOTE, { quiet: true }]]);
  });

  it("opens nothing when the saved history holds it, which is another screen's turn", () => {
    const { dock, update } = mount({ items: [made("c1", NOTE, "running"), handed("d1", [PLAN], "running")], detail: history("c1", "d1") });

    update({ items: [made("c1"), handed("d1", [PLAN])] });

    expect(opened(dock)).toEqual([]);
  });

  it.each<ToolStatus>(["failed", "denied", "stopped"])("opens nothing when it %s", (status) => {
    const { dock, update } = mount({ items: [made("c1", NOTE, "running")], detail: null });

    update({ items: [{ ...made("c1"), status, output: `${tag(NOTE)}\nok` }] });

    expect(opened(dock)).toEqual([]);
  });

  it("opens nothing on a screen too narrow, nor while the person has the keyboard in the dock", () => {
    const narrow = mount({ items: [made("c1", NOTE, "running")], wide: false });
    const busy = mount({ items: [made("c1", NOTE, "running")] });
    busy.person.typing = true;

    narrow.update({ items: [made("c1")] });
    busy.update({ items: [made("c1")] });

    expect(opened(narrow.dock)).toEqual([]);
    expect(opened(busy.dock)).toEqual([]);
    expect(busy.dock.typing).toHaveBeenCalledTimes(1);
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

describe("opening the canvas a handed-off task wrote", () => {
  it("opens it quietly, once the call is done in a turn this tab is showing", () => {
    const { dock, update } = mount();

    update({ items: [handed("d1", [PLAN], "running")] });
    expect(opened(dock)).toEqual([]);
    update({ items: [handed("d1", [PLAN])] });

    expect(opened(dock)).toEqual([[PLAN, { quiet: true }]]);
  });

  it("opens the first of the canvases the task wrote, and leaves the rest to the card", () => {
    const { dock, update } = mount();

    update({ items: [handed("d1", [SHOP, NOTE, PLAN])] });

    expect(opened(dock)).toEqual([[SHOP, { quiet: true }]]);
  });

  it("does not open it a second time however often the thread draws again", () => {
    const { dock, update } = mount();
    update({ items: [handed("d1", [PLAN])] });

    update({ items: [{ ...handed("d1", [PLAN]) }, { kind: "assistant", id: "m2", text: "xong", model: null }] });
    update({ wide: false });
    update({ wide: true });

    expect(opened(dock)).toEqual([[PLAN, { quiet: true }]]);
  });

  it("opens it whatever the task came to, so long as the call itself ended well", () => {
    const { dock, update } = mount();

    update({
      items: [
        handed("d1", [], "done", { output: result([NOTE], "outcome=partial reason=thiếu số liệu tuần trước") }),
        handed("d2", [], "done", { output: result([SHOP], "outcome=blocked reason=shell denied") }),
      ],
    });

    expect(opened(dock)).toEqual([
      [NOTE, { quiet: true }],
      [SHOP, { quiet: true }],
    ]);
  });

  it("opens each in turn when a canvas is made and another handed back in one draw", () => {
    const { dock, update } = mount();

    update({ items: [made("c1", NOTE), handed("d1", [PLAN])] });

    expect(opened(dock)).toEqual([
      [NOTE, { quiet: true }],
      [PLAN, { quiet: true }],
    ]);
  });

  it("leaves the canvas open that the task finishing last wrote, of two handed off side by side", () => {
    const { dock, update } = mount();
    update({ items: [handed("d1", [NOTE], "running"), handed("d2", [SHOP], "running")] });

    update({ items: [handed("d1", [NOTE], "running"), handed("d2", [SHOP])] });
    expect(opened(dock)).toEqual([[SHOP, { quiet: true }]]);
    update({ items: [handed("d1", [NOTE]), handed("d2", [SHOP])] });

    expect(opened(dock)).toEqual([
      [SHOP, { quiet: true }],
      [NOTE, { quiet: true }],
    ]);
  });
});

describe("a handed-off task that opens nothing by itself", () => {
  it("wrote no canvas, and asks nothing of the dock", () => {
    const { dock, update } = mount();

    update({ items: [handed("d1", [])] });
    update({ items: [handed("d1", []), handed("d2", [], "running")] });

    expect(opened(dock)).toEqual([]);
    expect(dock.typing).not.toHaveBeenCalled();
  });

  it("ran out of time as a call, though the canvas it had written by then is named", () => {
    const { dock, update } = mount();
    const late = handed("d1", [], "failed", {
      output: ["conversation=child1 status=running spent=$0.0100 steps=2", "outcome=failed reason=timeout", `${tag(NOTE)} Báo cáo`, "", ""].join("\n"),
    });

    update({ items: [late] });
    update({ items: [late, handed("d2", [], "running")] });

    expect(opened(dock)).toEqual([]);
  });

  it.each<ToolStatus>(["failed", "denied", "stopped"])("%s as a call, whatever its result names", (status) => {
    const { dock, update } = mount();

    update({ items: [handed("d1", [NOTE], status)] });
    update({ items: [handed("d1", [NOTE], status), handed("d2", [], "running")] });

    expect(opened(dock)).toEqual([]);
  });

  it("is in the conversation's saved history, or was there when the screen was drawn", () => {
    const { dock, update } = mount({ items: [handed("d0", [SHOP])], detail: null });

    update({ items: [handed("d0", [SHOP]), handed("d1", [NOTE])], detail: history("d1") });

    expect(opened(dock)).toEqual([]);
  });

  it("finished on a screen too narrow to hold a canvas beside the thread, even after the screen widens", () => {
    const { dock, update } = mount({ wide: false });

    update({ items: [handed("d1", [NOTE])] });
    update({ wide: true });
    update({ items: [handed("d1", [NOTE]), handed("d2", [], "running")] });

    expect(opened(dock)).toEqual([]);
  });

  it("finished while the person was typing in a canvas, even after they stop", () => {
    const { dock, person, update } = mount();
    person.typing = true;

    update({ items: [handed("d1", [NOTE])] });
    person.typing = false;
    update({ items: [handed("d1", [NOTE]), { kind: "assistant", id: "m2", text: "xong", model: null }] });

    expect(opened(dock)).toEqual([]);
    expect(dock.typing).toHaveBeenCalledTimes(1);
  });

  it("names a canvas only in its reply, under the blank line, where a line is the other agent's words", () => {
    const { dock, update } = mount();
    const quoted = [CHILD, "outcome=done", "", `${tag(NOTE)} Báo cáo`, "", "Xem canvas trên."].join("\n");
    const mixed = [CHILD, "outcome=done", `${tag(NOTE)} Báo cáo`, "và một dòng thường", "", "Đã viết."].join("\n");
    const unbroken = [CHILD, "outcome=done", `${tag(NOTE)} Báo cáo`].join("\n");

    update({
      items: [
        handed("d1", [], "done", { output: quoted }),
        handed("d2", [], "done", { output: mixed }),
        handed("d3", [], "done", { output: unbroken }),
      ],
    });

    expect(opened(dock)).toEqual([]);
  });

  it("was stored before a result said what the task came to, or says nothing a result does", () => {
    const { dock, update } = mount();

    update({
      items: [
        handed("d1", [], "done", { output: [CHILD, `${tag(NOTE)} Báo cáo`, "", "Đã viết."].join("\n") }),
        handed("d2", [], "done", { output: `${tag(NOTE)}\nCanvas was created.` }),
        handed("d3", [], "done", { output: "" }),
        handed("d4", [], "done", { output: null }),
        handed("d5", [], "done", { output: "delegate: unknown agent" }),
      ],
    });

    expect(opened(dock)).toEqual([]);
  });

  it("is not what a canvas tool returned: a result is read as the tool that gave it", () => {
    const { dock, update } = mount();

    update({
      items: [
        call("c1", "artifact_create", "done", { output: result([NOTE]) }),
        call("c2", "artifact_edit", "done", { output: result([SHOP]) }),
        call("c3", "web_search", "done", { output: result([PLAN]) }),
      ],
    });

    expect(opened(dock)).toEqual([]);
  });
});
