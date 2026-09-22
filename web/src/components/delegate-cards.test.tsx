import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import type { Conversation } from "../api/types";
import { vi } from "../i18n/vi";
import { runGroups } from "../state/activity-reducer";
import type { ThreadItem } from "../state/thread-reducer";
import { FakeBackend, coachAgent, fakeAgent, fakeRun } from "../test/fake-backend";
import { ConversationHeader } from "./conversation-header";
import { ConversationList } from "./conversation-list";
import { RunGroupCard } from "./run-timeline";
import { SettingsPanel } from "./settings-panel";
import { ToolCallCard } from "./tool-call-card";

const HEADER = "conversation=c-child status=done spent=$0.0250 steps=4";

function delegateCall(overrides: Partial<Extract<ThreadItem, { kind: "tool" }>> = {}) {
  return {
    kind: "tool" as const,
    id: "t1",
    name: "delegate",
    arguments: { agent: "coach", task: "Dọn mã trong thư mục web" },
    status: "done" as const,
    output: `${HEADER}\nĐã dọn xong.`,
    ...overrides,
  };
}

function conversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: "c1",
    agent_id: "default",
    title: "Cuộc của tôi",
    status: "idle",
    channel: "",
    created_at: "2026-09-20T01:00:00Z",
    updated_at: "2026-09-20T01:00:00Z",
    autonomous: false,
    cost_cap_usd: 1,
    spent_usd: 0.1,
    over_budget: false,
    summary: "",
    skills: [],
    auto_approve: [],
    parent_call_id: "",
    ...overrides,
  } as Conversation;
}

describe("the card for a handed-off task", () => {
  it("names who took it, what it cost, and opens the conversation it created", async () => {
    const open = vitest.fn();
    render(
      <ToolCallCard
        item={delegateCall()}
        agentName={(id) => (id === "coach" ? "HLV sức khoẻ" : id)}
        onOpenConversation={open}
      />,
    );

    const card = screen.getByTestId("delegate-card");
    expect(card).toHaveTextContent("HLV sức khoẻ");
    expect(card).toHaveTextContent("Dọn mã trong thư mục web");
    expect(within(card).getByTestId("delegate-status")).toHaveTextContent("done");
    expect(card).toHaveTextContent("$0.0250");
    expect(card).toHaveTextContent(vi.delegateSteps.replace("{n}", "4"));
    // The header is bookkeeping; the reply is what the person wanted to read.
    await userEvent.click(screen.getByRole("button", { name: vi.showOutput }));
    expect(screen.getByText("Đã dọn xong.")).toBeInTheDocument();
    expect(card).not.toHaveTextContent("spent=$");

    await userEvent.click(screen.getByRole("button", { name: vi.delegateOpenChild }));
    expect(open).toHaveBeenCalledWith("c-child");
  });

  it("shows a task still running, with no result to open yet", () => {
    render(<ToolCallCard item={delegateCall({ status: "running", output: null })} />);

    const card = screen.getByTestId("delegate-card");
    expect(card).toHaveTextContent(vi.delegateRunning);
    expect(screen.queryByTestId("delegate-status")).toBeNull();
    expect(screen.queryByRole("button", { name: vi.delegateOpenChild })).toBeNull();
  });
});

describe("the conversation a work agent is in", () => {
  it("is marked as work, with its cap and step budget in reach", () => {
    render(
      <ConversationHeader
        conversation={conversation()}
        agentName="HLV sức khoẻ"
        agent={{ ...coachAgent, mode: "work", cost_cap_usd: 5, max_steps: 60 }}
        childCount={2}
        spentUsd={0.1}
        unknownCostCalls={0}
        skills={[]}
        onRename={() => {}}
        onSummarize={() => {}}
        onToggleAutonomous={() => {}}
        onToggleSkill={() => {}}
        onRevokeAutoApprove={() => {}}
        onOpenSettings={() => {}}
      />,
    );

    expect(screen.getByTestId("work-badge")).toHaveAttribute(
      "title",
      vi.modeWorkHint.replace("{cap}", "5").replace("{steps}", "60"),
    );
    // Spend already rolls up the children, so the tooltip says where the money went.
    expect(screen.getByTestId("budget")).toHaveAttribute(
      "title",
      `${vi.budget} · ${vi.delegateIncludesChildren.replace("{n}", "2")}`,
    );
  });

  it("carries no work badge for an assistant", () => {
    render(
      <ConversationHeader
        conversation={conversation()}
        agentName="Agent"
        agent={fakeAgent}
        spentUsd={0.1}
        unknownCostCalls={0}
        skills={[]}
        onRename={() => {}}
        onSummarize={() => {}}
        onToggleAutonomous={() => {}}
        onToggleSkill={() => {}}
        onRevokeAutoApprove={() => {}}
        onOpenSettings={() => {}}
      />,
    );

    expect(screen.queryByTestId("work-badge")).toBeNull();
    expect(screen.getByTestId("budget")).toHaveAttribute("title", vi.budget);
  });
});

describe("the conversation list", () => {
  it("marks a conversation an agent opened and sorts it below the person's own", () => {
    render(
      <ConversationList
        conversations={[
          conversation({ id: "child", title: "Việc được giao", parent_call_id: "tc-1" }),
          conversation({ id: "mine", title: "Cuộc của tôi" }),
        ]}
        activeId="mine"
        onSelect={() => {}}
        onCreate={() => {}}
        onDelete={() => {}}
      />,
    );

    const titles = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(titles[0]).toContain("Cuộc của tôi");
    expect(titles[1]).toContain("Việc được giao");
    expect(screen.getAllByTestId("child-marker")).toHaveLength(1);
  });
});

describe("the run rail", () => {
  it("tucks a delegated run under the run that handed out the work", () => {
    const parent = fakeRun({ id: "r-parent", conversation_id: "c1", source: "chat" });
    const child = fakeRun({
      id: "r-child",
      agent_id: "coach",
      conversation_id: "c-child",
      source: "delegate:c1",
      title: "Dọn mã",
    });
    const [group] = runGroups([parent, child]);

    render(<RunGroupCard group={group} agentName={(id) => id} />);

    const children = screen.getByTestId("run-children");
    expect(within(children).getByTestId("run-card")).toHaveTextContent("Dọn mã");
    expect(screen.getAllByTestId("run-card")).toHaveLength(2);
  });
});

describe("the settings panel", () => {
  it("lists the crew with the master first and what each role may hand off", () => {
    render(
      <SettingsPanel
        settings={null}
        agents={[{ ...coachAgent, mode: "work", tools: ["shell_run"], delegates: ["coder"] }, { ...fakeAgent, delegates: ["coach"] }]}
        onClose={() => {}}
      />,
    );

    // A failed settings load must not hide the crew: it is what the panel is for.
    const crew = screen.getByTestId("settings-crew-list");
    const rows = within(crew).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("default");
    expect(rows[0]).toHaveTextContent(vi.crew.master);
    expect(rows[1]).toHaveTextContent(vi.modeWork);
    expect(rows[1]).toHaveTextContent(vi.toolCount.replace("{n}", "1"));
    expect(rows[1]).toHaveTextContent("coder");
    expect(rows[1]).not.toHaveTextContent(vi.crew.master);
    expect(screen.queryByTestId("template-list")).not.toBeInTheDocument();
  });

  it("shows the zone the machine reads its days in, and says when it is only the machine's", () => {
    const { settings } = new FakeBackend();
    const { rerender } = render(<SettingsPanel settings={settings} onClose={() => {}} />);
    expect(screen.getByText(vi.timezone).nextElementSibling).toHaveTextContent("Asia/Ho_Chi_Minh");
    expect(screen.getByText(vi.timezone).nextElementSibling).not.toHaveTextContent(vi.machineZone);

    rerender(<SettingsPanel settings={{ ...settings, timezone: "", zone: "UTC" }} onClose={() => {}} />);
    expect(screen.getByText(vi.timezone).nextElementSibling).toHaveTextContent(`UTC (${vi.machineZone})`);
  });
});
