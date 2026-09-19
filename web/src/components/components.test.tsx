import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { ApprovalBar } from "./approval-bar";
import { BudgetIndicator, formatUsd } from "./budget-indicator";
import { Composer } from "./composer";
import { ConversationList } from "./conversation-list";
import { ToolCallCard, summarizeArguments } from "./tool-call-card";

describe("ToolCallCard", () => {
  it("shows name, status label and toggles the output", async () => {
    render(
      <ToolCallCard
        item={{ kind: "tool", id: "tc", name: "read_file", arguments: { path: "a.txt" }, output: "body text", status: "done" }}
      />,
    );
    expect(screen.getByText(/read_file/)).toBeInTheDocument();
    expect(screen.getByText(vi.toolDone)).toBeInTheDocument();
    expect(screen.queryByText("body text")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: vi.showOutput }));
    expect(screen.getByText("body text")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: vi.hideOutput }));
    expect(screen.queryByText("body text")).not.toBeInTheDocument();
  });

  it("hides the output toggle while a tool is still running", () => {
    render(<ToolCallCard item={{ kind: "tool", id: "tc", name: "x", arguments: {}, output: null, status: "running" }} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(vi.toolRunning)).toBeInTheDocument();
  });

  it("summarizes arguments compactly and truncates long values", () => {
    expect(summarizeArguments({ path: "a", n: 2 })).toBe("path=a, n=2");
    expect(summarizeArguments({ text: "x".repeat(80) })).toBe(`text=${"x".repeat(57)}…`);
  });
});

describe("BudgetIndicator", () => {
  it("renders spent against the cap with a progress bar", () => {
    render(<BudgetIndicator spentUsd={0.25} capUsd={1} unknownCostCalls={0} />);
    expect(screen.getByText(`${vi.budget}: ${vi.spent("$0.25", "$1.00")}`)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveValue(0.25);
    expect(screen.queryByText(/\? \d/)).not.toBeInTheDocument();
  });

  it("marks unlimited caps and unknown-cost calls", () => {
    render(<BudgetIndicator spentUsd={0} capUsd={0} unknownCostCalls={3} />);
    expect(screen.getByText(new RegExp(vi.unlimited))).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.getByTitle(vi.unknownCost(3))).toHaveTextContent("? 3");
  });

  it("flags an exhausted budget", () => {
    render(<BudgetIndicator spentUsd={1.2} capUsd={1} unknownCostCalls={0} />);
    expect(screen.getByTestId("budget")).toHaveClass("over");
  });

  it("formats sub-cent amounts with more precision", () => {
    expect(formatUsd(0.0042)).toBe("$0.0042");
    expect(formatUsd(1.5)).toBe("$1.50");
    expect(formatUsd(0)).toBe("$0.00");
  });
});

describe("ApprovalBar", () => {
  it("names the tool and reports the decision", async () => {
    const onDecide = vitest.fn();
    render(
      <ApprovalBar pending={{ approvalId: "ap", toolCallId: "tc", name: "write_file", arguments: { path: "x" } }} busy={false} onDecide={onDecide} />,
    );
    expect(screen.getByText(vi.approvalTitle("write_file"))).toBeInTheDocument();
    expect(screen.getByText("path=x")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: vi.deny }));
    await userEvent.click(screen.getByRole("button", { name: vi.approve }));
    expect(onDecide.mock.calls).toEqual([[false], [true]]);
  });

  it("disables both buttons while the resumed turn is running", () => {
    render(<ApprovalBar pending={{ approvalId: "ap", toolCallId: "tc", name: "x", arguments: {} }} busy onDecide={() => undefined} />);
    expect(screen.getByRole("button", { name: vi.approve })).toBeDisabled();
    expect(screen.getByRole("button", { name: vi.deny })).toBeDisabled();
  });
});

describe("Composer", () => {
  it("sends trimmed text on Enter and keeps newlines on Shift+Enter", async () => {
    const onSend = vitest.fn();
    render(<Composer disabled={false} busy={false} onSend={onSend} onStop={() => undefined} />);
    const box = screen.getByRole("textbox");
    await userEvent.type(box, "line one{Shift>}{Enter}{/Shift}line two ");
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.type(box, "{Enter}");
    expect(onSend).toHaveBeenCalledWith("line one\nline two");
    expect(box).toHaveValue("");
  });

  it("ignores empty submissions and disables send when empty", async () => {
    const onSend = vitest.fn();
    render(<Composer disabled={false} busy={false} onSend={onSend} onStop={() => undefined} />);
    expect(screen.getByRole("button", { name: vi.send })).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox"), "   {Enter}");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("offers a stop button while busy and blocks input while disabled", async () => {
    const onStop = vitest.fn();
    const { rerender } = render(<Composer disabled={false} busy onSend={() => undefined} onStop={onStop} />);
    await userEvent.click(screen.getByRole("button", { name: vi.stop }));
    expect(onStop).toHaveBeenCalled();
    rerender(<Composer disabled busy={false} onSend={() => undefined} onStop={onStop} />);
    expect(screen.getByRole("textbox")).toBeDisabled();
  });

  it("prefills the draft handed in from a suggestion", () => {
    render(<Composer disabled={false} busy={false} draft="gợi ý" onSend={() => undefined} onStop={() => undefined} />);
    expect(screen.getByRole("textbox")).toHaveValue("gợi ý");
  });
});

describe("ConversationList", () => {
  const base = {
    id: "c1", agent_id: "default", channel: "", title: "Web", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle" as const, over_budget: false,
  };

  it("tags conversations that come from a channel and leaves web ones plain", () => {
    render(
      <ConversationList
        conversations={[base, { ...base, id: "c2", channel: "telegram:42", title: "Telegram · 2026-09-19" }]}
        activeId="c1"
        onSelect={() => {}}
        onCreate={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(screen.getAllByText("Telegram")).toHaveLength(1);
    expect(screen.getByText("Web").parentElement?.querySelector(".channel-tag")).toBeNull();
  });
});

describe("vi labels", () => {
  it("names run sources and channels in Vietnamese", () => {
    expect(vi.runSource("chat")).toBe("trò chuyện");
    expect(vi.runSource("telegram")).toBe("Telegram");
    expect(vi.runSource("job:coach/brief")).toBe("lịch coach/brief");
    expect(vi.channelName("telegram:42")).toBe("Telegram");
    expect(vi.channelName("slack:x")).toBe("slack");
  });
});
