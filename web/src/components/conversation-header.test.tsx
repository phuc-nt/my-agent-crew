import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Conversation } from "../api/types";
import { vi } from "../i18n/vi";
import { ConversationHeader } from "./conversation-header";

function conversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: "c2",
    agent_id: "default",
    channel: "",
    title: "Việc (nhánh)",
    created_at: "",
    updated_at: "",
    autonomous: false,
    cost_cap_usd: 1,
    spent_usd: 0,
    unknown_cost_calls: 0,
    status: "idle",
    over_budget: false,
    summary: "",
    skills: [],
    auto_approve: [],
    forked_from: "",
    ...overrides,
  } as Conversation;
}

function header(extra: { conversation?: Conversation; sourceTitle?: string; onOpenSource?: () => void } = {}) {
  return render(
    <ConversationHeader
      conversation={extra.conversation ?? conversation()}
      agentName="Trợ lý"
      spentUsd={0}
      unknownCostCalls={0}
      skills={[]}
      onRename={() => {}}
      onSummarize={() => {}}
      onToggleAutonomous={() => {}}
      onToggleSkill={() => {}}
      onRevokeAutoApprove={() => {}}
      sourceTitle={extra.sourceTitle}
      onOpenSource={extra.onOpenSource}
    />,
  );
}

describe("the fork-origin line", () => {
  it("is absent when the conversation is not a fork", () => {
    header({ conversation: conversation({ forked_from: "" }) });
    expect(screen.queryByTestId("fork-origin")).toBeNull();
  });

  it("is absent when the conversation carries no forked_from field at all", () => {
    const plain = conversation();
    delete plain.forked_from;
    header({ conversation: plain });
    expect(screen.queryByTestId("fork-origin")).toBeNull();
  });

  it("names the source conversation and opens it on click", () => {
    let opened = false;
    header({
      conversation: conversation({ forked_from: "c1" }),
      sourceTitle: "Việc",
      onOpenSource: () => (opened = true),
    });
    const link = screen.getByTestId("fork-origin");
    expect(link).toHaveTextContent(vi.fork.from);
    expect(link).toHaveTextContent("Việc");
    link.querySelector("button")?.click();
    expect(opened).toBe(true);
  });

  it("falls back to the generic label when the source is not in the loaded list", () => {
    header({ conversation: conversation({ forked_from: "c1" }), sourceTitle: undefined });
    const link = screen.getByTestId("fork-origin");
    expect(link).toHaveTextContent(vi.fork.original);
  });
});
