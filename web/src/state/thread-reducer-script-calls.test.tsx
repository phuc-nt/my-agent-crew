import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { AgentEvent, NestedToolCall } from "../api/types";
import { ToolCallCard } from "../components/tool-call-card";
import { vi } from "../i18n/vi";
import { storedMessage } from "../test/fake-backend";
import { emptyThread, itemsFromMessages, threadReducer, type ThreadItem, type ThreadState } from "./thread-reducer";

type Tool = Extract<ThreadItem, { kind: "tool" }>;

const SOURCE = 'found = tools.mcp__notion__search(query="kế hoạch")\nprint(len(found))';
const script = { id: "s1", name: "tool_script", arguments: { script: SOURCE } };
const search: NestedToolCall = { name: "mcp__notion__search", arguments: { query: "kế hoạch" }, ok: true, output: "3 trang", ms: 120, cost_usd: null, metered: false };
const missing: NestedToolCall = { name: "workspace_read", arguments: { path: "a.md" }, ok: false, output: "không có tệp", ms: 4, cost_usd: null, metered: false };
const paid: NestedToolCall = { name: "pdf_read", arguments: { path: "a.pdf" }, ok: true, output: "Tổng chi 4,2 triệu.", ms: 1_500, cost_usd: 0.004, metered: true };

const asked = (...calls: { id: string; name: string; arguments: Record<string, unknown> }[]): AgentEvent => ({
  type: "assistant_message", message_id: "a", content: "", tool_calls: calls, provider: null, model: null, cost_usd: null,
});
const started = (call: { id: string; name: string; arguments: Record<string, unknown> } = script): AgentEvent => ({ type: "tool_call", tool_call_id: call.id, name: call.name, arguments: call.arguments });
const heard = (index: number, call: NestedToolCall, id = "s1"): AgentEvent => ({ type: "nested_call", tool_call_id: id, index, call });
const ended = (extra: Partial<Extract<AgentEvent, { type: "tool_result" }>> = {}): AgentEvent => ({
  type: "tool_result", tool_call_id: "s1", name: "tool_script", ok: true, output: "3", ...extra,
});

function run(events: AgentEvent[], from: ThreadState = { ...emptyThread, busy: true }): ThreadState {
  return events.reduce((state, event) => threadReducer(state, { type: "event", event }), from);
}

/** The thread read back from the store: the script's result with what it kept beside its output. */
function readBack(context: string, reply = "3"): ThreadItem[] {
  return itemsFromMessages([
    storedMessage("assistant", "", { tool_calls: [script] }),
    storedMessage("tool", reply, { tool_call_id: "s1", context }),
  ]);
}

const kept = (calls: NestedToolCall[], received: number | null, printed: number | null) =>
  JSON.stringify({ calls, received_chars: received, printed_chars: printed });

describe("what a script calls, on its card in the thread", () => {
  it("is listed call by call as each ends, while the card is still running", () => {
    const one = run([asked(script), started(), heard(0, search)]);
    expect(one.items).toEqual([{ kind: "tool", id: "s1", name: "tool_script", arguments: script.arguments, output: null, status: "running", calls: [search] }]);

    const two = run([heard(1, missing)], one);
    expect(two.items[0]).toMatchObject({ status: "running", output: null, calls: [search, missing] });
    expect(two.busy).toBe(true);
  });

  // A stream joined again is sent what it missed, the last of which it may have had.
  it("keeps a call heard twice once, in its place", () => {
    const state = run([asked(script), started(), heard(0, search), heard(1, missing), heard(1, missing), heard(0, search)]);
    expect(state.items[0]).toMatchObject({ calls: [search, missing] });
  });

  it("ends as the result says: the calls in the order the script made them, and its two measures", () => {
    // Heard as they ended, the second the script made first.
    const running = run([asked(script), started(), heard(0, paid), heard(1, search)]);

    const done = run([ended({ calls: [search, paid, missing], received_chars: 38, printed_chars: 1 })], running);

    expect(done.items).toEqual([
      { kind: "tool", id: "s1", name: "tool_script", arguments: script.arguments, output: "3", status: "done", calls: [search, paid, missing], received_chars: 38, printed_chars: 1 },
    ]);
  });

  it("puts nothing of the kind on the card of a tool that called nothing and is no script", () => {
    const read = { id: "r1", name: "workspace_read", arguments: { path: "a.md" } };
    for (const none of [{}, { calls: [], received_chars: null, printed_chars: null }]) {
      const state = run([asked(read), started(read), { type: "tool_result", tool_call_id: "r1", name: "workspace_read", ok: true, output: "hai dòng", ...none }]);
      expect(state.items).toEqual([{ kind: "tool", id: "r1", name: "workspace_read", arguments: read.arguments, output: "hai dòng", status: "done" }]);
    }
  });

  it("lists on the card of the script that made the call, and touches no other", () => {
    const other = { id: "s2", name: "tool_script", arguments: { script: "print(1)" } };
    const before = run([asked(script, other), started(), started(other)]);

    const after = run([heard(0, search, "s2")], before);

    expect(after.items[0]).toBe(before.items[0]);
    expect(after.items[0]).not.toHaveProperty("calls");
    expect(after.items[1]).toMatchObject({ id: "s2", calls: [search] });
    // A call for a card the thread does not hold changes none of them.
    const stray = run([heard(0, search, "zz")], before);
    expect(stray.items).toEqual(before.items);
  });
});

describe("what a script called, read back from the stored thread", () => {
  it("is on the card as it was when the result arrived", () => {
    const live = run([asked(script), started(), heard(0, search), ended({ calls: [search, missing, paid], received_chars: 38, printed_chars: 1 })]);

    const stored = readBack(kept([search, missing, paid], 38, 1));

    expect(stored).toEqual([
      { kind: "tool", id: "s1", name: "tool_script", arguments: script.arguments, output: "3", status: "done", calls: [search, missing, paid], received_chars: 38, printed_chars: 1 },
    ]);
    expect(stored).toEqual(live.items);
  });

  it("is the measures alone for a script that called nothing", () => {
    const [card] = readBack(kept([], 0, 1));
    expect(card).toMatchObject({ received_chars: 0, printed_chars: 1 });
    expect(card).not.toHaveProperty("calls");
  });

  it("leaves the status to the reply, as for any tool", () => {
    const [card] = readBack(kept([search, missing], 19, 0), "Công cụ lỗi: Script dừng ở dòng 2.");
    expect(card).toMatchObject({ status: "failed", calls: [search, missing] });
  });

  // The field holds a person's canvas note on another kind of message, and nothing on
  // the result of a tool that is no script.
  it.each(["", "[Canvas · Kế hoạch tuần]\n> chạy 5 km", '{"calls": [', "null", '{"calls": "mcp__notion__search"}'])(
    "is a plain card when the result kept nothing a script keeps: %j",
    (context) => {
      expect(readBack(context)).toEqual([{ kind: "tool", id: "s1", name: "tool_script", arguments: script.arguments, output: "3", status: "done" }]);
    },
  );
});

describe("the chat card of a script", () => {
  const drawn = (item: ThreadItem) => {
    render(<ToolCallCard item={item as Tool} />);
    return screen.getByTestId("tool-card");
  };
  const follows = (first: Element, second: Element) => Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING);

  it("lists after a reload each call it made: its name, whether it failed, how long it took, what it cost", async () => {
    const [item] = readBack(kept([search, missing, paid], 38, 1));
    const card = drawn(item);

    const list = within(card).getByTestId("script-calls") as HTMLDetailsElement;
    expect(list.querySelector("summary")).toHaveTextContent(/^Script đã gọi công cụ 3 lần · 1 lần lỗi$/);
    expect(list.open).toBe(false);
    await userEvent.click(list.querySelector("summary")!);
    const rows = within(list).getAllByTestId("script-call");
    expect(rows.map((row) => row.querySelector(".script-call-head")?.textContent)).toEqual([
      "mcp__notion__search120 ms",
      `workspace_read${vi.toolFailed}4 ms`,
      "pdf_read1.5 giây",
    ]);
    expect(rows.map((row) => row.getAttribute("data-ok"))).toEqual(["true", "false", "true"]);
    expect(within(rows[2]).getByTestId("script-call-cost")).toHaveTextContent(/^Có gọi model · \$0\.0040$/);
    expect(within(rows[0]).queryByTestId("script-call-cost")).toBeNull();
    expect(within(card).getByTestId("script-measures")).toHaveTextContent(/^Nhận 38 ký tự từ 3 lời gọi, trả về 1 ký tự$/);
  });

  it("reads top to bottom: what it was asked, what it called, what that came to, what it printed", () => {
    const [item] = readBack(kept([search], 7, 1));
    const card = drawn(item);

    const parts = [
      card.querySelector(".tool-arguments")!,
      within(card).getByRole("button", { name: vi.argumentsMore }),
      within(card).getByTestId("script-calls"),
      within(card).getByTestId("script-measures"),
      within(card).getByRole("button", { name: vi.showOutput }),
    ];
    for (let at = 1; at < parts.length; at += 1) expect(follows(parts[at - 1], parts[at]), `part ${at}`).toBe(true);
  });

  it.each(["running", "awaiting", "stopped", "denied"] as const)("lists its calls while %s and counts nothing yet", (status) => {
    const card = drawn({ kind: "tool", ...script, output: null, status, calls: [search, missing] });

    expect(within(card).getByTestId("script-calls").querySelector("summary")).toHaveTextContent(vi.scriptCalls(2, 1));
    expect(within(card).queryByTestId("script-measures")).toBeNull();
  });

  it("counts on a script that failed as on one that did not", () => {
    const [item] = readBack(kept([search, missing], 19, 0), "Công cụ lỗi: Script dừng ở dòng 2.");
    const card = drawn(item);

    expect(card).toHaveClass("failed");
    expect(within(card).getByTestId("script-measures")).toHaveTextContent(/^Nhận 19 ký tự từ 2 lời gọi, trả về 0 ký tự$/);
  });

  it("has neither a list nor a count on the card of any other tool", () => {
    const card = drawn({ kind: "tool", id: "r1", name: "workspace_read", arguments: { path: "a.md" }, output: "hai dòng", status: "done" });

    expect(within(card).queryByTestId("script-calls")).toBeNull();
    expect(within(card).queryByTestId("script-measures")).toBeNull();
  });
});
