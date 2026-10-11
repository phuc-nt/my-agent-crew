import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AgentEvent, NestedToolCall } from "../api/types";
import { vi } from "../i18n/vi";
import { conversationMarkdown } from "../lib/conversation-markdown";
import { notYetListed } from "../lib/nested-calls";
import { scriptCallsMarkdown } from "../lib/script-calls-markdown";
import { emptyThread, itemsFromMessages, threadReducer, type ThreadItem } from "../state/thread-reducer";
import { FakeBackend, fakeRun, storedMessage } from "../test/fake-backend";
import { RunCard } from "./run-timeline";
import { ScriptCalls } from "./script-calls";
import { ToolCallCard } from "./tool-call-card";

type Tool = Extract<ThreadItem, { kind: "tool" }>;

const base = { ok: true, cost_usd: null, metered: false };
/** A call that only read: it carries no `gated` key, as every call did before scripts could write. */
const read: NestedToolCall = { ...base, name: "mcp__notion__search", arguments: { query: "kế hoạch" }, output: "3 trang", ms: 120 };
/** A call that changed something, let through by the approval gate. */
const wrote: NestedToolCall = { ...base, name: "mcp__notion__create_page", arguments: { title: "Kế hoạch tuần" }, output: "đã tạo", ms: 340, gated: true };
/** Let through by the gate, and then it failed on its own. */
const failedWrite: NestedToolCall = { ...base, name: "workspace_write", arguments: { path: "a.md" }, ok: false, output: "hết chỗ", ms: 9, gated: true };
const CALLS = [read, wrote, failedWrite];

const READ_HEAD = `mcp__notion__search${vi.stepDuration(120)}`;
const WROTE_HEAD = `mcp__notion__create_page${vi.scriptCallGated}${vi.stepDuration(340)}`;
const FAILED_WRITE_HEAD = `workspace_write${vi.toolFailed}${vi.scriptCallGated}${vi.stepDuration(9)}`;

/** The head of each listed call as it reads, and the marks among them. */
function listed(within_: HTMLElement) {
  const rows = within(within_).queryAllByTestId("script-call");
  return {
    heads: rows.map((row) => row.querySelector(".script-call-head")?.textContent),
    marks: rows.map((row) => within(row).queryAllByTestId("script-call-gated").map((mark) => mark.textContent)),
  };
}

const script = { id: "s1", name: "tool_script", arguments: { script: "tools.mcp__notion__create_page(title='Kế hoạch tuần')" } };
const kept = (calls: unknown) => JSON.stringify({ calls, received_chars: 60, printed_chars: 8 });
const readBack = (context: string) =>
  itemsFromMessages([
    storedMessage("assistant", "", { tool_calls: [script] }),
    storedMessage("tool", "đã tạo", { tool_call_id: "s1", context }),
  ]);
function card(item: ThreadItem) {
  const { unmount } = render(<ToolCallCard item={item as Tool} />);
  return { ...listed(screen.getByTestId("tool-card")), unmount };
}

describe("a call a script made through the approval gate", () => {
  // The script's step shows one state for all its calls; only the call's own row can say
  // which of them changed something. In words: a colour says nothing to a screen reader.
  it("says so in words on its own row, after whether it failed and before how long it took", () => {
    render(<ScriptCalls calls={CALLS} />);
    const { heads, marks } = listed(screen.getByTestId("script-calls"));

    expect(heads).toEqual([READ_HEAD, WROTE_HEAD, FAILED_WRITE_HEAD]);
    expect(marks).toEqual([[], [vi.scriptCallGated], [vi.scriptCallGated]]);
    expect(vi.scriptCallGated.trim()).not.toBe("");
    // The count line is about failures, as before.
    expect(screen.getByTestId("script-calls").querySelector("summary")).toHaveTextContent(vi.scriptCalls(3, 1));
  });

  it("leaves a call without the key, or with it false, reading exactly as it did", () => {
    const { container } = render(<ScriptCalls calls={[read, { ...read, gated: false }]} />);
    const [bare, saidFalse] = Array.from(container.querySelectorAll('[data-testid="script-call"]'));

    expect(listed(container).heads).toEqual([READ_HEAD, READ_HEAD]);
    expect(saidFalse.outerHTML).toBe(bare.outerHTML);
    expect(bare.querySelector(".script-call-head")?.className).toBe("script-call-head");
    expect(bare.querySelector(".script-call-head")?.children).toHaveLength(2);
  });

  it("is marked on the chat card while the script runs and once it has ended", () => {
    const say = (events: AgentEvent[]) =>
      events.reduce((state, event) => threadReducer(state, { type: "event", event }), { ...emptyThread, busy: true });
    const opening: AgentEvent[] = [
      { type: "assistant_message", message_id: "a", content: "", tool_calls: [script], provider: null, model: null, cost_usd: null },
      { type: "tool_call", tool_call_id: "s1", name: "tool_script", arguments: script.arguments },
      { type: "nested_call", tool_call_id: "s1", index: 0, call: read },
      { type: "nested_call", tool_call_id: "s1", index: 1, call: wrote },
    ];

    const running = card(say(opening).items[0]);
    expect(running.heads).toEqual([READ_HEAD, WROTE_HEAD]);
    running.unmount();

    const ended = card(
      say([...opening, { type: "tool_result", tool_call_id: "s1", name: "tool_script", ok: true, output: "đã tạo", calls: CALLS, received_chars: 60, printed_chars: 8 }]).items[0],
    );
    expect(ended.heads).toEqual([READ_HEAD, WROTE_HEAD, FAILED_WRITE_HEAD]);
  });

  it("is marked on the chat card read back from the store", () => {
    const [item] = readBack(kept(CALLS));
    expect(item).toMatchObject({ calls: CALLS });
    expect(card(item).heads).toEqual([READ_HEAD, WROTE_HEAD, FAILED_WRITE_HEAD]);
  });

  // Every result stored before scripts could write has calls with no such key.
  it("lists the calls of an older stored result as before, with no mark", () => {
    const older = [read, { ...read, name: "workspace_read", ok: false, ms: 4 }];
    const [item] = readBack(kept(older));

    const { heads, marks } = card(item);

    expect(heads).toEqual([READ_HEAD, `workspace_read${vi.toolFailed}${vi.stepDuration(4)}`]);
    expect(marks).toEqual([[], []]);
  });

  // The stored field is read with care; a mark that is not a yes or a no is not a call.
  it("does not list a stored result whose mark is not a yes or a no", () => {
    for (const odd of ["yes", 1, null, {}]) {
      const [item] = readBack(kept([read, { ...wrote, gated: odd }]));
      expect(item).not.toHaveProperty("calls");
      expect(item).toMatchObject({ kind: "tool", status: "done", output: "đã tạo" });
    }
  });

  it("is marked on the script's step in a run", () => {
    const run = fakeRun({
      steps: [
        { kind: "tool", name: "tool_script", tool_call_id: "a", arguments: script.arguments, ok: true, output: "đã tạo", calls: CALLS, duration_ms: 600 },
        // Kept from before scripts could write.
        { kind: "tool", name: "tool_script", tool_call_id: "b", arguments: script.arguments, ok: true, output: "3", calls: [read], duration_ms: 200 },
      ],
    });
    render(<RunCard run={run} agentName="HLV" expanded />);
    const [writing, reading] = screen.getAllByTestId("run-step");

    expect(listed(writing).heads).toEqual([READ_HEAD, WROTE_HEAD, FAILED_WRITE_HEAD]);
    expect(listed(reading)).toEqual({ heads: [READ_HEAD], marks: [[]] });
  });

  it("is named in the exported conversation, on the call's line", () => {
    const lines = [
      `1. \`mcp__notion__search\` · ${vi.stepDuration(120)}`,
      `2. \`mcp__notion__create_page\` · ${vi.scriptCallGated} · ${vi.stepDuration(340)}`,
      `3. \`workspace_write\` · ${vi.toolFailed} · ${vi.scriptCallGated} · ${vi.stepDuration(9)}`,
    ];
    expect(scriptCallsMarkdown(CALLS)).toBe(`${vi.scriptCalls(3, 1)}:\n\n${lines.join("\n")}`);

    const exported = (calls: unknown) =>
      conversationMarkdown(
        new FakeBackend().create({
          title: "Ghi chú",
          messages: [
            storedMessage("user", "Lập kế hoạch tuần", { created_at: "2026-09-24T23:30:00Z" }),
            storedMessage("assistant", "", { created_at: "2026-09-24T23:30:05Z", tool_calls: [script] }),
            storedMessage("tool", "đã tạo", { created_at: "2026-09-24T23:30:09Z", tool_call_id: "s1", context: kept(calls) }),
          ],
        }),
        "Coach",
      );
    expect(exported(CALLS)).toContain(`\n\n${lines.join("\n")}\n`);
    // Without the key, and with it false, a line is what it was.
    const plain = exported([read, { ...read, gated: false }]);
    expect(plain).toContain(`\n\n${lines[0]}\n2. \`mcp__notion__search\` · ${vi.stepDuration(120)}\n`);
    expect(plain).not.toContain(vi.scriptCallGated);
  });

  // Heard as it ended without the key and named again by the result with it, or the other
  // way round, it is one call: taken for two, its cost would be added twice.
  it("is the same call whether or not a hearing of it carried the mark", () => {
    const { gated: _gated, ...unmarked } = wrote;
    expect(notYetListed([unmarked], [wrote])).toEqual([]);
    expect(notYetListed([wrote], [unmarked, read])).toEqual([read]);
    expect(notYetListed([{ ...wrote, gated: false }], [wrote])).toEqual([]);
  });
});
