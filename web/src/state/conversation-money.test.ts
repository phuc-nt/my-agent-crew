import { describe, expect, it } from "vitest";
import type { Conversation } from "../api/types";
import { conversationMoney } from "./conversation-money";

function row(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: "c1",
    agent_id: "coach",
    channel: "",
    title: "",
    created_at: "2026-09-19T00:00:00Z",
    updated_at: "2026-09-19T00:00:00Z",
    autonomous: false,
    cost_cap_usd: 1,
    skills: [],
    auto_approve: [],
    parent_call_id: "",
    spent_usd: 0,
    unknown_cost_calls: 0,
    status: "idle",
    over_budget: false,
    summary: "",
    ...overrides,
  };
}

const thread = (conversationId: string | null, spentUsd: number) => ({ conversationId, spentUsd });

describe("the spend of the conversation on screen", () => {
  it("is what the thread heard when the row has not been read since", () => {
    expect(conversationMoney(row({ spent_usd: 0 }), false, thread("c1", 0.0123)).spentUsd).toBe(0.0123);
    expect(conversationMoney(row({ spent_usd: 0.1 }), true, thread("c1", 0.25)).spentUsd).toBe(0.25);
  });

  it("is the row's when the row was read after the thread last heard", () => {
    expect(conversationMoney(row({ spent_usd: 0.4 }), true, thread("c1", 0.1)).spentUsd).toBe(0.4);
  });

  // A thread still on its way in is empty, and one that holds another conversation says
  // nothing about this one.
  it("is the row's while the thread on screen is not this conversation's", () => {
    expect(conversationMoney(row({ spent_usd: 0.3 }), true, thread(null, 0)).spentUsd).toBe(0.3);
    expect(conversationMoney(row({ spent_usd: 0.3 }), true, thread("other", 0.9)).spentUsd).toBe(0.3);
  });
});

describe("whether the spend has reached the cap", () => {
  it("is the server's rule on the one figure: a cap above zero that the spend has reached", () => {
    expect(conversationMoney(row({ spent_usd: 0.5 }), true, thread("c1", 1)).capReached).toBe(true);
    expect(conversationMoney(row({ spent_usd: 1 }), true, thread(null, 0)).capReached).toBe(true);
    expect(conversationMoney(row({ spent_usd: 0.5 }), true, thread("c1", 0.99)).capReached).toBe(false);
    expect(conversationMoney(row({ cost_cap_usd: 0, spent_usd: 3 }), true, thread("c1", 3)).capReached).toBe(false);
  });
});

describe("whether the conversation on screen has used up its cap", () => {
  it("is the server's word for a listed row, which is read again when a run ends", () => {
    expect(conversationMoney(row({ over_budget: false }), true, thread("c1", 1)).overBudget).toBe(false);
    expect(conversationMoney(row({ spent_usd: 1, over_budget: true }), true, thread("c1", 1)).overBudget).toBe(true);
  });

  it("is worked out for a conversation outside the list, whose row nothing reads again", () => {
    expect(conversationMoney(row({ over_budget: false }), false, thread("c1", 1)).overBudget).toBe(true);
    expect(conversationMoney(row({ over_budget: false }), false, thread("c1", 1.2)).overBudget).toBe(true);
    expect(conversationMoney(row({ over_budget: false }), false, thread("c1", 0.99)).overBudget).toBe(false);
  });

  it("never calls a conversation without a cap over budget", () => {
    expect(conversationMoney(row({ cost_cap_usd: 0 }), false, thread("c1", 5)).overBudget).toBe(false);
  });

  it("keeps the server's word for a conversation outside the list that it loaded over budget", () => {
    expect(conversationMoney(row({ spent_usd: 1, over_budget: true }), false, thread(null, 0)).overBudget).toBe(true);
  });

  it("lets go once a raised cap is loaded", () => {
    expect(conversationMoney(row({ cost_cap_usd: 2, spent_usd: 1 }), false, thread("c1", 1)).overBudget).toBe(false);
  });
});
