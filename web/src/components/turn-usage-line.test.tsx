import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AgentEvent, StoredMessage } from "../api/types";
import { emptyThread, itemsFromMessages, threadReducer, type ThreadState } from "../state/thread-reducer";
import { Item } from "./message-item";

function message(partial: Partial<StoredMessage> & { role: StoredMessage["role"] }): StoredMessage {
  return {
    id: partial.id ?? `m-${Math.random()}`,
    seq: 0,
    content: "",
    tool_calls: [],
    tool_call_id: null,
    name: null,
    provider: null,
    model: null,
    cost_usd: null,
    created_at: "2026-11-01T00:00:00Z",
    ...partial,
  };
}

const CALL = { id: "t1", name: "workspace_list", arguments: {} };

const reply = (state: ThreadState) => state.items.filter((i) => i.kind === "assistant");

describe("the usage under a reply", () => {
  it("adds every model call of the turn before it, the tool steps included", () => {
    const items = itemsFromMessages([
      message({ role: "user", content: "Liệt kê tệp" }),
      message({ role: "assistant", tool_calls: [CALL], prompt_tokens: 20000, cached_tokens: 0, cost_usd: 0.06 }),
      message({ role: "tool", tool_call_id: "t1", content: "a.md" }),
      message({ role: "assistant", content: "Có a.md", prompt_tokens: 20000, cached_tokens: 18000, cost_usd: 0.005 }),
      message({ role: "user", content: "Cảm ơn" }),
      message({ role: "assistant", content: "Không có gì", cost_usd: null }),
    ]);

    render(<>{items.map((item) => <Item key={item.id} item={item} agentId="default" speaker="Agent" />)}</>);

    const [first, second] = screen.getAllByTestId("turn-usage");
    expect(first).toHaveTextContent("2 lượt gọi model · 40k token vào · 45% từ cache · $0.07");
    expect(second).toHaveTextContent("1 lượt gọi model · ≥ $0.00 (chưa đủ giá)");
  });

  it("counts a live turn from its start", () => {
    const step = (content: string, cost: number): AgentEvent => ({
      type: "assistant_message",
      message_id: content || "step",
      content,
      tool_calls: [],
      provider: "anthropic",
      model: "claude-sonnet-5-5",
      cost_usd: cost,
      prompt_tokens: 1000,
      cached_tokens: 500,
    });
    let state = threadReducer(emptyThread, { type: "turn_started" });
    state = threadReducer(state, { type: "event", event: step("", 0.01) });
    state = threadReducer(state, { type: "event", event: step("Xong", 0.02) });
    expect(reply(state)[0]).toMatchObject({ usage: { steps: 2, promptTokens: 2000, costUsd: 0.03 } });

    state = threadReducer(state, { type: "turn_started" });
    state = threadReducer(state, { type: "event", event: step("Lượt mới", 0.01) });
    expect(reply(state)[1]).toMatchObject({ usage: { steps: 1, costUsd: 0.01 } });
  });
});
