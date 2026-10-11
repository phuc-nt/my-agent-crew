import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AgentEvent, NestedToolCall } from "../api/types";
import { vi } from "../i18n/vi";
import { conversationMarkdown } from "../lib/conversation-markdown";
import { scriptCallsMarkdown } from "../lib/script-calls-markdown";
import { emptyThread, itemsFromMessages, threadReducer, type ThreadItem } from "../state/thread-reducer";
import { FakeBackend, fakeRun, storedMessage } from "../test/fake-backend";
import { RunCard } from "./run-timeline";
import { ScriptCalls } from "./script-calls";
import { ToolCallCard } from "./tool-call-card";

type Tool = Extract<ThreadItem, { kind: "tool" }>;

/** A tool the script called, beside the model calls: it goes by its own name. */
const read: NestedToolCall = { name: "workspace_read", arguments: { path: "thu.md" }, ok: true, output: "Kính gửi quý khách", ms: 4, cost_usd: null, metered: false };
/** The two things a script can ask a model itself, as the server lists them: under names no tool has. */
const classify: NestedToolCall = {
  name: "llm.classify",
  arguments: { text: "Kính gửi quý khách, hoá đơn tháng 10…", labels: '["hoá đơn", "quảng cáo", "khác"]' },
  ok: true,
  output: "hoá đơn",
  ms: 812,
  cost_usd: 0.00021,
  metered: true,
};
const summarise: NestedToolCall = {
  name: "llm.summarise",
  arguments: { text: "…", max_chars: 500 },
  ok: true,
  output: "Khách hỏi về hoá đơn tháng 10 và xin hoãn hạn trả.",
  ms: 1_304,
  cost_usd: 0.0004,
  metered: true,
};
/** The model did not answer: still charged for, at a price nobody gave. */
const unanswered: NestedToolCall = { ...classify, ok: false, output: "model không trả lời", ms: 30_000, cost_usd: null };
const CALLS = [read, classify, summarise, unanswered];

const CLASSIFY = vi.scriptModelCall["llm.classify"];
const SUMMARISE = vi.scriptModelCall["llm.summarise"];
const HEADS = [
  `workspace_read${vi.stepDuration(4)}`,
  `${CLASSIFY}${vi.stepDuration(812)}`,
  `${SUMMARISE}${vi.stepDuration(1_304)}`,
  `${CLASSIFY}${vi.toolFailed}${vi.stepDuration(30_000)}`,
];
const COSTS = [null, vi.stepToolCost("$0.0002"), vi.stepToolCost("$0.0004"), vi.stepToolCost(vi.stepCostUnknown)];

/** Each listed call as it reads: its head, and the line that says what it paid a model. */
function listed(within_: HTMLElement) {
  const rows = within(within_).getAllByTestId("script-call");
  return {
    rows,
    heads: rows.map((row) => row.querySelector(".script-call-head")?.textContent),
    costs: rows.map((row) => within(row).queryByTestId("script-call-cost")?.textContent ?? null),
  };
}

const script = { id: "s1", name: "tool_script", arguments: { script: "llm.classify(text, ['hoá đơn', 'quảng cáo', 'khác'])" } };
const kept = (calls: unknown) => JSON.stringify({ calls, received_chars: 90, printed_chars: 8 });
function card(item: ThreadItem) {
  const { unmount } = render(<ToolCallCard item={item as Tool} />);
  return { ...listed(screen.getByTestId("tool-card")), unmount };
}

describe("a model a script asked itself", () => {
  it("is listed with the script's other calls, in words that say what it is, with what it cost", () => {
    render(<ScriptCalls calls={CALLS} />);
    const list = screen.getByTestId("script-calls");
    const { heads, costs } = listed(list);

    expect(heads).toEqual(HEADS);
    expect(costs).toEqual(COSTS);
    // Counted with the rest, a failure among them counted as one.
    expect(list.querySelector("summary")).toHaveTextContent(vi.scriptCalls(4, 1));
  });

  // The name such a call travels under is no tool's. Nothing here goes looking for it among
  // the tools, so there is no blank, no "unknown tool" and no missing icon to come back with:
  // a person reads the words, and never the name set as an identifier they might search for.
  it("is never read by the name it travels under, nor looked up as a tool", () => {
    render(<ScriptCalls calls={CALLS} />);
    const [tool, ...models] = listed(screen.getByTestId("script-calls")).rows;

    expect(tool.querySelector("code.script-call-name")).toHaveTextContent("workspace_read");
    for (const row of models) {
      expect(row.querySelector("code")).toBeNull();
      expect(row.querySelector(".script-call-name")?.textContent?.trim()).not.toBe("");
      expect(row.querySelector(".script-call-head")?.textContent).not.toMatch(/llm|undefined|null/);
      expect(row.querySelector("svg, img")).toBeNull();
    }
    // What it was asked and what it answered are shown as for any call.
    expect(models[0]).toHaveTextContent("hoá đơn");
    expect(within(models[1]).getByTestId("script-call-output")).toHaveTextContent(summarise.output);
  });

  it("is still said to be a model call when there is no word for what it was asked", () => {
    render(<ScriptCalls calls={[{ ...classify, name: "llm.translate" }]} />);
    const [row] = listed(screen.getByTestId("script-calls")).rows;

    expect(row.querySelector(".script-call-head")?.textContent).toBe(`${vi.scriptModelCallOther("translate")}${vi.stepDuration(812)}`);
    expect(row.querySelector("code")).toBeNull();
  });

  it("reads the same on the chat card while the script runs, once it has ended and read back from the store", () => {
    const say = (events: AgentEvent[]) =>
      events.reduce((state, event) => threadReducer(state, { type: "event", event }), { ...emptyThread, busy: true });
    const opening: AgentEvent[] = [
      { type: "assistant_message", message_id: "a", content: "", tool_calls: [script], provider: null, model: null, cost_usd: null },
      { type: "tool_call", tool_call_id: "s1", name: "tool_script", arguments: script.arguments },
      { type: "nested_call", tool_call_id: "s1", index: 0, call: read },
      { type: "nested_call", tool_call_id: "s1", index: 1, call: classify },
    ];

    const running = card(say(opening).items[0]);
    expect(running.heads).toEqual(HEADS.slice(0, 2));
    expect(running.costs).toEqual(COSTS.slice(0, 2));
    running.unmount();

    const ended = card(
      say([...opening, { type: "tool_result", tool_call_id: "s1", name: "tool_script", ok: true, output: "hoá đơn", calls: CALLS, received_chars: 90, printed_chars: 8 }]).items[0],
    );
    expect(ended.heads).toEqual(HEADS);
    expect(ended.costs).toEqual(COSTS);
    ended.unmount();

    const [stored] = itemsFromMessages([
      storedMessage("assistant", "", { tool_calls: [script] }),
      storedMessage("tool", "hoá đơn", { tool_call_id: "s1", context: kept(CALLS) }),
    ]);
    expect(stored).toMatchObject({ calls: CALLS });
    const readBack = card(stored);
    expect(readBack.heads).toEqual(HEADS);
    expect(readBack.costs).toEqual(COSTS);
  });

  it("reads the same on the script's step in a run, and has no step of its own", () => {
    const run = fakeRun({
      steps: [{ kind: "tool", name: "tool_script", tool_call_id: "s1", arguments: script.arguments, ok: true, output: "hoá đơn", calls: CALLS, duration_ms: 33_000 }],
    });
    render(<RunCard run={run} agentName="HLV" expanded />);
    const steps = screen.getAllByTestId("run-step");

    expect(steps).toHaveLength(1);
    expect(listed(steps[0]).heads).toEqual(HEADS);
    expect(listed(steps[0]).costs).toEqual(COSTS);
    expect(steps[0].querySelector(".script-calls")?.textContent).not.toContain("llm.");
  });

  it("is written in the same words in the exported conversation, with its price, and not as code", () => {
    const lines = [
      `1. \`workspace_read\` · ${vi.stepDuration(4)}`,
      `2. ${CLASSIFY} · ${vi.stepDuration(812)} · $0.0002`,
      `3. ${SUMMARISE} · ${vi.stepDuration(1_304)} · $0.0004`,
      `4. ${CLASSIFY} · ${vi.toolFailed} · ${vi.stepDuration(30_000)} · ${vi.stepCostUnknown}`,
    ];
    expect(scriptCallsMarkdown(CALLS)).toBe(`${vi.scriptCalls(4, 1)}:\n\n${lines.join("\n")}`);

    const exported = conversationMarkdown(
      new FakeBackend().create({
        title: "Thư khách",
        messages: [
          storedMessage("user", "Phân loại thư này", { created_at: "2026-09-24T23:30:00Z" }),
          storedMessage("assistant", "", { created_at: "2026-09-24T23:30:05Z", tool_calls: [script] }),
          storedMessage("tool", "hoá đơn", { created_at: "2026-09-24T23:30:09Z", tool_call_id: "s1", context: kept(CALLS) }),
        ],
      }),
      "Coach",
    );
    expect(exported).toContain(`\n\n${lines.join("\n")}\n`);
    expect(exported).not.toContain("`llm.");
  });
});
