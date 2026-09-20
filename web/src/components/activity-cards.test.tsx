import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { coachAgent, fakeRun } from "../test/fake-backend";
import { AttentionCenter } from "./attention-center";
import { JobsPanel } from "./jobs-panel";
import { RunCard } from "./run-timeline";
import { StatsPanel } from "./stats-panel";

const name = (id: string) => (id === "coach" ? "HLV" : "Agent");

describe("RunCard", () => {
  it("shows status, cost and expands into model and tool steps with durations", async () => {
    const run = fakeRun({
      status: "running",
      finished_at: null,
      spent_usd: 0.0042,
      unknown_cost_calls: 1,
      steps: [
        { kind: "fallback", provider: "openrouter", model: "glm-5.3-flash", error: "HTTP 429 from glm-5.3-flash", duration_ms: null },
        { kind: "model", chars: 12, provider: "fake", model: "echo", cost_usd: null, tool_calls: ["shell_run"], preview: "chạy lệnh", duration_ms: 1500 },
        { kind: "tool", name: "shell_run", tool_call_id: "tc", arguments: { command: "ls" }, ok: false, output: "no such dir", duration_ms: 20 },
      ],
    });
    const open = vitest.fn();
    render(<RunCard run={run} agentName="HLV" onOpenConversation={open} />);
    const card = screen.getByTestId("run-card");
    expect(card).toHaveTextContent("HLV");
    expect(card).toHaveTextContent(vi.runStatus.running);
    expect(card).toHaveTextContent("$0.0042");
    expect(card).toHaveTextContent("? 1");
    expect(screen.queryAllByTestId("run-step")).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    const [fallback, ...steps] = screen.getAllByTestId("run-step");
    expect(fallback).toHaveTextContent(vi.stepFallback);
    expect(fallback).toHaveTextContent("openrouter:glm-5.3-flash · HTTP 429 from glm-5.3-flash");
    expect(steps[0]).toHaveTextContent("echo");
    expect(steps[0]).toHaveTextContent(vi.stepChars(12));
    expect(steps[0]).toHaveTextContent(vi.stepCostUnknown);
    expect(steps[0]).toHaveTextContent("1.5 giây");
    expect(steps[0]).toHaveTextContent("→ shell_run");
    expect(steps[1]).toHaveTextContent(vi.toolFailed);
    expect(steps[1]).toHaveTextContent("20 ms");
    expect(steps[1]).toHaveTextContent("command=ls");
    await userEvent.click(within(steps[1]).getByRole("button", { name: vi.showOutput }));
    expect(steps[1]).toHaveTextContent("no such dir");
    await userEvent.click(screen.getByRole("button", { name: vi.openConversation }));
    expect(open).toHaveBeenCalledWith("c1");
  });
});

describe("AttentionCenter", () => {
  it("lists approvals, failures and halts by agent and opens their conversation", async () => {
    const open = vitest.fn();
    render(
      <AttentionCenter
        agentName={name}
        onOpenConversation={open}
        runs={[
          fakeRun({ id: "a", status: "awaiting_approval", agent_id: "coach", summary: "write_file" }),
          fakeRun({ id: "b", status: "error", conversation_id: null, summary: "kaput" }),
          fakeRun({ id: "c", status: "halted", conversation_id: "c9" }),
        ]}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent(vi.attentionAwaiting("HLV"));
    expect(items[1]).toHaveTextContent(vi.attentionFailed("Agent"));
    expect(items[2]).toHaveTextContent(vi.attentionHalted("Agent"));
    expect(within(items[1]).queryByRole("button")).not.toBeInTheDocument();
    await userEvent.click(within(items[2]).getByRole("button", { name: vi.openConversation }));
    expect(open).toHaveBeenCalledWith("c9");
  });

  it("says when nothing needs a human", () => {
    render(<AttentionCenter agentName={name} onOpenConversation={() => undefined} runs={[]} />);
    expect(screen.getByText(vi.attentionEmpty)).toBeInTheDocument();
  });
});

describe("JobsPanel", () => {
  it("shows schedule, next and last run, and fires run-now", async () => {
    const onRunNow = vitest.fn();
    render(
      <JobsPanel
        agentName={name}
        onRunNow={onRunNow}
        jobs={[
          { ...coachAgent.schedules[0], id: "coach/brief", schedule_id: "brief", agent_id: "coach", next_run: "2026-09-20T00:00:00Z", last_run: fakeRun({ status: "done" }), running: false },
          { id: "default/sync", schedule_id: "sync", agent_id: "default", name: "Đồng bộ", kind: "command", cron: null, every: "30m", prompt: null, command: "git pull", enabled: false, skills: [], next_run: null, last_run: null, running: true },
        ]}
      />,
    );
    const jobs = screen.getAllByTestId("job");
    expect(jobs[0]).toHaveTextContent("HLV · Bản tin sáng");
    expect(jobs[0]).toHaveTextContent("0 7 * * *");
    expect(jobs[0]).toHaveTextContent(vi.jobKindPrompt);
    expect(jobs[0]).toHaveTextContent(vi.runStatus.done);
    expect(jobs[0]).toHaveTextContent(`${vi.jobSkills}: goodreads`);
    expect(jobs[1]).not.toHaveTextContent(vi.jobSkills);
    expect(jobs[1]).toHaveTextContent("30m");
    expect(jobs[1]).toHaveTextContent(vi.jobKindCommand);
    expect(jobs[1]).toHaveTextContent(vi.jobNever);
    expect(jobs[1]).toHaveTextContent(vi.jobDisabled);
    expect(within(jobs[1]).getByRole("button")).toBeDisabled();
    await userEvent.click(within(jobs[0]).getByRole("button", { name: /Chạy ngay/ }));
    expect(onRunNow).toHaveBeenCalledWith("coach/brief");
  });

  it("explains an empty schedule and a failed load", () => {
    const { rerender } = render(<JobsPanel agentName={name} onRunNow={() => undefined} jobs={[]} />);
    expect(screen.getByText(vi.jobsEmpty)).toBeInTheDocument();
    rerender(<JobsPanel agentName={name} onRunNow={() => undefined} jobs={null} />);
    expect(screen.getByText(vi.loadFailed)).toBeInTheDocument();
  });
});

describe("StatsPanel", () => {
  it("renders totals and per-agent, per-model, per-day bars", () => {
    render(
      <StatsPanel
        agentName={name}
        stats={{ runs: 3, model_calls: 7, spent_usd: 0.3, unknown_cost_calls: 2, by_agent: { coach: 0.2, default: 0.1 }, by_model: { "deepseek": 0.3 }, by_day: { "2026-09-19": 0.3 }, pending_proposals: 0 }}
      />,
    );
    const stats = screen.getByTestId("stats");
    expect(stats).toHaveTextContent("$0.30");
    expect(stats).toHaveTextContent("? 2");
    expect(stats).toHaveTextContent("HLV");
    expect(stats).toHaveTextContent("deepseek");
    expect(stats).toHaveTextContent("2026-09-19");
  });

  it("says when nothing has been spent", () => {
    render(<StatsPanel agentName={name} stats={{ runs: 0, model_calls: 0, spent_usd: 0, unknown_cost_calls: 0, by_agent: {}, by_model: {}, by_day: {}, pending_proposals: 0 }} />);
    expect(screen.getByText(vi.costEmpty)).toBeInTheDocument();
  });
});
