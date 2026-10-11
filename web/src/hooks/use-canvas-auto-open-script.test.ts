import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import type { NestedToolCall } from "../api/types";
import type { ThreadItem, ToolStatus } from "../state/thread-reducer";
import { useCanvasAutoOpen } from "./use-canvas-auto-open";

const NOTE = "0123456789ab";
const SHOP = "ba9876543210";
const PLAN = "00ff00ff00ff";

type Tool = Extract<ThreadItem, { kind: "tool" }>;
type Detail = { messages: { tool_calls: { id: string }[] }[] } | null;
type Props = { items: ThreadItem[]; detail: Detail; wide: boolean };

/** One call a script made, as the server lists it: what came back is a single cut line, and a
 *  call that wrote a canvas has that canvas's tag whole at the head of it. */
function nested(name: string, output: string, fields: Partial<NestedToolCall> = {}): NestedToolCall {
  return { name, arguments: {}, ok: true, output, ms: 12, cost_usd: null, metered: false, ...fields };
}
const tag = (canvas: string, version = 1, unchanged = false) => `[artifact ${canvas} v${version}${unchanged ? " unchanged" : ""}]`;
const created = (canvas: string) => nested("artifact_create", `${tag(canvas)} Đã tạo canvas "Thư trả lời" (markdown).`, { arguments: { title: "Thư trả lời" }, gated: true });
const importedNew = (canvas: string) => nested("artifact_import", `${tag(canvas)} Đã nhập.`, { arguments: { path: "thu.md" }, gated: true });

/** The script's own call in the thread, holding the calls it has been heard to make. */
function script(calls: NestedToolCall[], status: ToolStatus = "done", id = "s1"): Tool {
  const going = status === "running" || status === "awaiting";
  return { kind: "tool", id, name: "tool_script", arguments: { script: "…" }, output: going ? null : "xong", status, calls };
}

const history = (...ids: string[]): Detail => ({ messages: [{ tool_calls: ids.map((id) => ({ id })) }] });

/** The hook as the chat screen runs it: a dock whose `typing` the test can change, `open` recorded. */
function mount(initial: Partial<Props> = {}) {
  const person = { typing: false };
  const dock = { open: vitest.fn(), typing: vitest.fn(() => person.typing) };
  let props: Props = { items: [], detail: null, wide: true, ...initial };
  const view = renderHook((now: Props) => useCanvasAutoOpen({ state: { items: now.items }, detail: now.detail }, dock, now.wide), {
    initialProps: props,
  });
  const update = (next: Partial<Props>) => {
    props = { ...props, ...next };
    view.rerender(props);
  };
  return { dock, person, update };
}

const opened = (dock: { open: { mock: { calls: unknown[][] } } }) => dock.open.mock.calls;

describe("opening the canvas a script just made", () => {
  it("opens it quietly once the script is done, and not as each of its calls is heard", () => {
    const { dock, update } = mount();

    update({ items: [script([], "running")] });
    update({ items: [script([created(NOTE)], "running")] });
    update({ items: [script([created(NOTE), nested("workspace_read", "Kính gửi")], "running")] });
    expect(opened(dock)).toEqual([]);

    update({ items: [script([created(NOTE), nested("workspace_read", "Kính gửi")])] });

    expect(opened(dock)).toEqual([[NOTE, { quiet: true }]]);
  });

  it("does not open it a second time however often the thread draws again", () => {
    const { dock, update } = mount();
    update({ items: [script([created(NOTE)])] });

    update({ items: [script([created(NOTE)]), script([], "running", "s2")] });
    update({ items: [{ ...script([created(NOTE)]) }, { kind: "assistant", id: "m2", text: "xong", model: null }] });
    update({ wide: false });
    update({ wide: true });

    expect(opened(dock)).toEqual([[NOTE, { quiet: true }]]);
  });

  it("leaves the last canvas made open, of the several one script made", () => {
    const { dock, update } = mount();

    update({ items: [script([created(NOTE), importedNew(SHOP), created(PLAN), nested("artifact_edit", `${tag(NOTE, 2)} Đã sửa.`, { arguments: { id: NOTE } })])] });

    expect(opened(dock)).toEqual([[PLAN, { quiet: true }]]);
  });

  it("opens a file a script read into a canvas of its own, which made one", () => {
    const { dock, update } = mount();

    update({ items: [script([importedNew(SHOP)])] });

    expect(opened(dock)).toEqual([[SHOP, { quiet: true }]]);
  });

  it("opens each script's canvas, and a direct call's, in the order the calls stand", () => {
    const { dock, update } = mount();
    const direct: Tool = { kind: "tool", id: "c1", name: "artifact_create", arguments: {}, output: `${tag(PLAN)}\nCanvas was created.`, status: "done" };

    update({ items: [script([created(NOTE)], "done", "s1"), direct, script([created(SHOP)], "done", "s2")] });

    expect(opened(dock).map(([id]) => id)).toEqual([NOTE, PLAN, SHOP]);
  });

  it("opens it for a script still going when the screen was drawn, once that script ends", () => {
    const { dock, update } = mount({ items: [script([created(NOTE)], "running")] });
    expect(opened(dock)).toEqual([]);

    update({ items: [script([created(NOTE)])] });

    expect(opened(dock)).toEqual([[NOTE, { quiet: true }]]);
  });

  it("is judged by how the person was when the script ended, not when its call made the canvas", () => {
    const { dock, person, update } = mount();
    person.typing = true;
    update({ items: [script([created(NOTE)], "running")] });
    person.typing = false;

    update({ items: [script([created(NOTE)])] });

    expect(opened(dock)).toEqual([[NOTE, { quiet: true }]]);
  });
});

describe("what a script did that never opens a canvas by itself", () => {
  it("is an edit, a rewrite, a file read into a canvas it named or one that left its canvas as it was", () => {
    const { dock, update } = mount();

    update({
      items: [
        script([
          nested("artifact_edit", `${tag(NOTE, 2)} Đã sửa.`, { arguments: { id: NOTE }, gated: true }),
          nested("artifact_rewrite", `${tag(NOTE, 3)} Đã viết lại.`, { arguments: { id: NOTE }, gated: true }),
          nested("artifact_import", `${tag(NOTE, 4)} Đã nhập lại.`, { arguments: { id: NOTE, path: "thu.md" }, gated: true }),
          nested("artifact_import", `${tag(SHOP, 1, true)} Tệp không đổi.`, { arguments: { path: "thu.md" }, gated: true }),
          nested("artifact_read", `${tag(PLAN)} Kính gửi`),
          nested("web_search", `${tag(PLAN)} kết quả`),
        ]),
      ],
    });

    expect(opened(dock)).toEqual([]);
  });

  it("is a call of its own that failed, though what it answered opens with a canvas's tag", () => {
    const { dock, update } = mount();

    update({ items: [script([created(NOTE), { ...created(SHOP), ok: false }])] });

    // The one that failed is passed over; the one made before it is the last one made.
    expect(opened(dock)).toEqual([[NOTE, { quiet: true }]]);
  });

  it("needs the tag at the head of what the call answered to name a canvas", () => {
    const { dock, update } = mount();

    update({
      items: [
        script([
          nested("artifact_create", "Đã tạo canvas."),
          nested("artifact_create", `Đã tạo ${tag(NOTE)}`),
          nested("artifact_create", "[artifact 0123456789AB v1] Đã tạo."),
          nested("artifact_create", ""),
        ]),
      ],
    });

    expect(opened(dock)).toEqual([]);
  });

  it.each<ToolStatus>(["failed", "denied", "stopped"])("is anything a script that %s made before it did", (status) => {
    const { dock, update } = mount();

    update({ items: [script([created(NOTE)], "running")] });
    update({ items: [script([created(NOTE)], status)] });
    update({ items: [script([created(NOTE)], status), script([], "running", "s2")] });

    expect(opened(dock)).toEqual([]);
  });

  it("is a canvas a task the script handed off says the other agent wrote", () => {
    const { dock, update } = mount();
    const handedOff = nested("delegate", `conversation=3f9a1c0b7d2e status=done spent=$0.0123 steps=7 outcome=done ${tag(NOTE)} Thư trả lời Thư đã soạn xong.`, {
      arguments: { task: "Soạn thư", agent: "writer" },
      child_spent_usd: 0.0123,
    });

    update({ items: [script([handedOff])] });

    expect(opened(dock)).toEqual([]);
  });

  it("is a canvas on a screen too narrow to hold it beside the thread, even after the screen widens", () => {
    const { dock, update } = mount({ wide: false });

    update({ items: [script([created(NOTE)], "running")] });
    update({ items: [script([created(NOTE)])] });
    update({ wide: true });
    update({ items: [script([created(NOTE)]), script([], "running", "s2")] });

    expect(opened(dock)).toEqual([]);
  });

  it("is a canvas made while the person had the keyboard in the dock, even after they leave it", () => {
    const { dock, person, update } = mount();
    update({ items: [script([created(NOTE)], "running")] });
    person.typing = true;

    update({ items: [script([created(NOTE)])] });
    person.typing = false;
    update({ items: [script([created(NOTE)]), { kind: "assistant", id: "m2", text: "xong", model: null }] });

    expect(opened(dock)).toEqual([]);
    expect(dock.typing).toHaveBeenCalledTimes(1);
  });

  it("is a canvas a script made in a conversation this tab only read, whether it came with the mount or a load", () => {
    const { dock, update } = mount({ items: [script([created(NOTE)])], detail: history("s1") });

    update({ items: [], detail: null });
    update({ items: [script([created(NOTE)]), script([created(SHOP)], "done", "s2")], detail: history("s1", "s2") });

    expect(opened(dock)).toEqual([]);
  });

  it("is a canvas made by a script that had ended before this screen was drawn", () => {
    const { dock, update } = mount({ items: [script([created(NOTE)])], detail: null });
    expect(opened(dock)).toEqual([]);

    update({ items: [script([created(NOTE)]), script([created(SHOP)], "done", "s2")] });

    expect(opened(dock)).toEqual([[SHOP, { quiet: true }]]);
  });
});
