import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Conversation } from "../api/types";
import { vi } from "../i18n/vi";
import { emptyThread } from "../state/thread-reducer";
import { questionPending } from "../test/pending";
import { ConversationHeader } from "./conversation-header";
import { StatusLine } from "./status-line";

function conversation(id: string): Conversation {
  return {
    id, parent_call_id: "", agent_id: "default", channel: "", title: `Việc ${id}`, created_at: "", updated_at: "", autonomous: false,
    cost_cap_usd: 1, spent_usd: 0, unknown_cost_calls: 0, status: "idle", over_budget: false,
    summary: "Đã tạo thư mục", skills: [], auto_approve: [],
  };
}

function header(c: Conversation, compact: boolean) {
  return (
    <ConversationHeader
      conversation={c} agentName="Trợ lý" spentUsd={0} unknownCostCalls={0} skills={[]} compact={compact}
      onRename={() => {}} onSummarize={() => {}} onToggleAutonomous={() => {}} onToggleSkill={() => {}}
      onRevokeAutoApprove={() => {}} first={<button type="button">Canvas</button>}
      extra={<button type="button">Đội</button>}
    />
  );
}

const more = () => screen.getByRole("button", { name: vi.headerMore });

describe("the conversation header on a phone", () => {
  it("is the title row and the canvas until its toggle opens the other pills and the recap", async () => {
    render(header(conversation("c1"), true));
    expect(screen.getByText("Việc c1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Canvas" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Đội" })).toBeNull();
    expect(screen.queryByText("Đã tạo thư mục")).toBeNull();
    expect(more()).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(more());

    expect(more()).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByRole("button", { name: "Canvas" })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Đội" })).toBeInTheDocument();
    expect(screen.getByText("Đã tạo thư mục")).toBeInTheDocument();
  });

  it("folds again when another conversation opens", async () => {
    const { rerender } = render(header(conversation("c1"), true));
    await userEvent.click(more());
    rerender(header(conversation("c2"), true));
    expect(more()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "Đội" })).toBeNull();
  });

  it("shows everything with no toggle on a wider screen", () => {
    render(header(conversation("c1"), false));
    expect(screen.queryByRole("button", { name: vi.headerMore })).toBeNull();
    expect(screen.getByRole("button", { name: "Đội" })).toBeInTheDocument();
    expect(screen.getByText("Đã tạo thư mục")).toBeInTheDocument();
  });
});

describe("the status line on a phone", () => {
  const line = () => screen.getByRole("status");

  it("keeps quiet while all is well, and still says so to a screen reader", () => {
    render(<StatusLine thread={emptyThread} connected liveCount={0} quiet />);
    expect(line()).toHaveClass("calm");
    expect(line()).toHaveTextContent(vi.statusIdle);
  });

  it("speaks up for a turn, a request, a run elsewhere or a lost stream", () => {
    const { rerender } = render(<StatusLine thread={{ ...emptyThread, busy: true }} connected liveCount={0} quiet />);
    expect(line()).not.toHaveClass("calm");
    rerender(<StatusLine thread={{ ...emptyThread, pending: questionPending() }} connected liveCount={0} quiet />);
    expect(line()).not.toHaveClass("calm");
    rerender(<StatusLine thread={emptyThread} connected liveCount={1} quiet />);
    expect(line()).not.toHaveClass("calm");
    rerender(<StatusLine thread={emptyThread} connected={false} liveCount={0} quiet />);
    expect(line()).not.toHaveClass("calm");
  });

  it("is never quiet where it is not asked to be", () => {
    render(<StatusLine thread={emptyThread} connected liveCount={0} />);
    expect(line()).not.toHaveClass("calm");
  });
});
