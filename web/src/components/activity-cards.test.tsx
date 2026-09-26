import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import type { JobInfo } from "../api/activity-types";
import { vi } from "../i18n/vi";
import { FakeBackend, coachAgent, fakeRun } from "../test/fake-backend";
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
    expect(fallback).toHaveTextContent("openrouter:glm-5.3-flash");
    expect(fallback).toHaveTextContent("HTTP 429 from glm-5.3-flash");
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

  it("draws a model call caught mid-answer as thinking, with no price it cannot know yet", async () => {
    const run = fakeRun({
      status: "running",
      finished_at: null,
      steps: [{ kind: "model", chars: 0, first_token_ms: null, duration_ms: null }],
    });
    render(<RunCard run={run} agentName="HLV" expanded />);
    const [step] = screen.getAllByTestId("run-step");
    expect(step).toHaveAttribute("data-state", "running");
    expect(step).toHaveTextContent(vi.runThinking);
    expect(step).not.toHaveTextContent("$");
    const header = screen.getByTestId("run-progress");
    expect(header).toHaveTextContent(vi.runThinking);
    expect(header).not.toHaveTextContent(vi.runDoing(vi.runThinking));
  });

  it("draws a question as a row that is waiting, not one that is working", async () => {
    const run = fakeRun({
      status: "awaiting_approval",
      finished_at: null,
      steps: [
        { kind: "model", chars: 5, provider: "fake", model: "echo", cost_usd: null, tool_calls: [], preview: "", duration_ms: 10 },
        { kind: "question", question: "Dời hạn sang thứ sáu?", duration_ms: null },
      ],
    });
    render(<RunCard run={run} agentName="HLV" expanded />);
    const asked = screen.getAllByTestId("run-step")[1];
    expect(asked).toHaveTextContent("Dời hạn sang thứ sáu?");
    expect(asked).toHaveTextContent(vi.stepQuestion);
    expect(asked).toHaveTextContent(vi.toolWaiting);
    expect(asked).toHaveAttribute("data-state", "waiting");
  });

  it("says when the model read a shortened tool output, and how it was shortened", async () => {
    const run = fakeRun({
      steps: [
        { kind: "tool", name: "shell_run", tool_call_id: "a", arguments: {}, ok: true, output: "{…}", shaped: { kind: "json", original_chars: 41000 }, duration_ms: 10 },
        { kind: "tool", name: "web_fetch", tool_call_id: "b", arguments: {}, ok: true, output: "…", shaped: { kind: "summary", original_chars: 90000 }, duration_ms: 10 },
        { kind: "tool", name: "workspace_read", tool_call_id: "c", arguments: {}, ok: true, output: "vừa", duration_ms: 10 },
      ],
    });
    render(<RunCard run={run} agentName="HLV" onOpenConversation={vitest.fn()} />);
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    const steps = screen.getAllByTestId("run-step");
    expect(steps[0]).toHaveTextContent(vi.stepShaped("json", 41000));
    expect(steps[1]).toHaveTextContent(vi.stepShaped("summary", 90000));
    expect(within(steps[2]).queryByTestId("step-shaped")).toBeNull();
  });

  it("stops showing a step as running once its run has died under it", async () => {
    // The step is recorded open (`ok: null`) because it was open when the row
    // was written. The run then errored without ever closing it. Painting that
    // as "running" leaves a spinner turning on work that stopped long ago.
    const run = fakeRun({
      status: "error",
      steps: [{ kind: "tool", name: "shell_run", tool_call_id: "tc", arguments: {}, ok: null, output: null, duration_ms: null }],
    });
    render(<RunCard run={run} agentName="HLV" expanded />);
    const [step] = screen.getAllByTestId("run-step");
    expect(step).toHaveAttribute("data-state", "stalled");
    expect(step).toHaveTextContent(vi.toolStalled);
    expect(step).not.toHaveTextContent(vi.toolRunning);
  });

  it("folds a retry loop into one row with its count and total time", async () => {
    const search = {
      kind: "tool" as const,
      name: "web_search",
      tool_call_id: "tc",
      arguments: {},
      ok: true,
      output: null,
      duration_ms: 100,
    };
    const run = fakeRun({ status: "done", steps: [search, search, search] });
    render(<RunCard run={run} agentName="HLV" expanded />);
    const steps = screen.getAllByTestId("run-step");
    expect(steps).toHaveLength(1);
    expect(steps[0]).toHaveTextContent(vi.stepRepeat(3));
    expect(steps[0]).toHaveTextContent(vi.stepDuration(300));
  });

  it("spends no width on a state word the row already implies, but still says it", async () => {
    // A plain success and a fallback both know their outcome without a label:
    // the first from its node colour, the second from the word "đổi tuyến". The
    // word still has to reach a screen reader, which only reads text.
    const run = fakeRun({
      status: "done",
      steps: [
        { kind: "tool", name: "read_file", tool_call_id: "tc", arguments: {}, ok: true, output: null, duration_ms: 10 },
        { kind: "fallback", provider: "openrouter", model: "glm", error: "429", duration_ms: 5 },
      ],
    });
    const { container } = render(<RunCard run={run} agentName="HLV" expanded />);
    expect(container.querySelectorAll(".step-state")).toHaveLength(0);
    const [ok, fallback] = screen.getAllByTestId("run-step");
    expect(ok).toHaveTextContent(vi.toolDone);
    expect(fallback).toHaveTextContent(vi.toolFailed);
  });

  it("gives an unfinished row its state in words, since no colour says it alone", async () => {
    const run = fakeRun({
      status: "running",
      steps: [{ kind: "tool", name: "shell_run", tool_call_id: "tc", arguments: {}, ok: null, output: null, duration_ms: null }],
    });
    const { container } = render(<RunCard run={run} agentName="HLV" expanded />);
    expect(container.querySelector(".step-state")).toHaveTextContent(vi.toolRunning);
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

  it("tells a question apart from a permission request", async () => {
    // Both pause the run the same way, but only one has Cho phép / Từ chối. Labelling a
    // question "đang chờ bạn duyệt" sends the person looking for buttons that are not
    // there, and that the server would refuse anyway.
    render(
      <AttentionCenter
        agentName={name}
        onOpenConversation={() => undefined}
        runs={[
          fakeRun({
            id: "q",
            status: "awaiting_approval",
            agent_id: "coach",
            summary: "Dời hạn sang thứ sáu?",
            steps: [{ kind: "question", question: "Dời hạn sang thứ sáu?", duration_ms: null }],
          }),
          fakeRun({ id: "t", status: "awaiting_approval", summary: "write_file" }),
        ]}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent(vi.attentionAsking("HLV"));
    expect(items[1]).toHaveTextContent(vi.attentionAwaiting("Agent"));
  });

  it("says when nothing needs a human", () => {
    render(<AttentionCenter agentName={name} onOpenConversation={() => undefined} runs={[]} />);
    expect(screen.getByText(vi.attentionEmpty)).toBeInTheDocument();
  });
});

describe("JobsPanel", () => {
  const brief: JobInfo = { ...coachAgent.schedules[0], id: "coach/brief", schedule_id: "brief", agent_id: "coach", next_run: "2026-09-20T00:00:00Z", last_run: fakeRun({ status: "done" }), running: false, paused: false };
  const sync: JobInfo = { id: "default/sync", schedule_id: "sync", agent_id: "default", name: "Đồng bộ", kind: "command", cron: null, every: "30m", prompt: null, command: "git pull", enabled: false, paused: false, skills: [], next_run: null, last_run: null, running: true };

  afterEach(() => vitest.unstubAllGlobals());

  it("shows schedule, next and last run, and fires run-now", async () => {
    const onRunNow = vitest.fn();
    render(<JobsPanel agentName={name} onRunNow={onRunNow} onToggle={() => undefined} jobs={[brief, sync]} />);
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
    expect(within(jobs[1]).getByRole("button", { name: /Chạy ngay/ })).toBeDisabled();
    await userEvent.click(within(jobs[0]).getByRole("button", { name: /Chạy ngay/ }));
    expect(onRunNow).toHaveBeenCalledWith("coach/brief");
  });

  it("pauses and resumes a schedule from its switch, but not one the profile turned off", async () => {
    const onToggle = vitest.fn();
    render(
      <JobsPanel
        agentName={name}
        onRunNow={() => undefined}
        onToggle={onToggle}
        jobs={[brief, { ...brief, id: "coach/paused", name: "Tạm", enabled: false, paused: true }, sync]}
      />,
    );
    const jobs = screen.getAllByTestId("job");
    const live = within(jobs[0]).getByRole("checkbox", { name: /Bật lịch/ });
    expect(live).toBeChecked();
    await userEvent.click(live);
    expect(onToggle).toHaveBeenCalledWith("coach/brief", false);

    expect(jobs[1]).toHaveTextContent(vi.jobPaused);
    const paused = within(jobs[1]).getByRole("checkbox", { name: /Bật lịch/ });
    expect(paused).not.toBeChecked();
    expect(paused).toBeEnabled();
    await userEvent.click(paused);
    expect(onToggle).toHaveBeenLastCalledWith("coach/paused", true);

    // A schedule disabled in agent.yaml cannot be resumed from the UI.
    expect(within(jobs[2]).getByRole("checkbox", { name: /Bật lịch/ })).toBeDisabled();
    expect(jobs[2]).not.toHaveTextContent(vi.jobPaused);
  });

  it("loads the run history of a schedule on demand", async () => {
    const backend = new FakeBackend();
    backend.runs = [fakeRun({ id: "h1", source: "job:coach/brief", agent_id: "coach", summary: "Bản tin hôm qua" }), fakeRun({ id: "other", source: "chat" })];
    vitest.stubGlobal("fetch", backend.fetch);
    render(<JobsPanel agentName={name} onRunNow={() => undefined} onToggle={() => undefined} jobs={[brief]} />);
    expect(screen.queryByTestId("job-runs")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: vi.showHistory }));
    const history = await screen.findByTestId("job-runs");
    expect(within(history).getAllByTestId("run-card")).toHaveLength(1);
    expect(history).toHaveTextContent("Bản tin hôm qua");
    expect(backend.requests.some((r) => r.path === "/jobs/coach/brief/runs")).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: vi.hideHistory }));
    expect(screen.queryByTestId("job-runs")).not.toBeInTheDocument();
  });

  it("explains an empty schedule and a failed load", () => {
    const { rerender } = render(<JobsPanel agentName={name} onRunNow={() => undefined} onToggle={() => undefined} jobs={[]} />);
    expect(screen.getByText(vi.jobsEmpty)).toBeInTheDocument();
    rerender(<JobsPanel agentName={name} onRunNow={() => undefined} onToggle={() => undefined} jobs={null} />);
    expect(screen.getByText(vi.loadFailed)).toBeInTheDocument();
  });
});

describe("StatsPanel", () => {
  it("renders totals, per-agent bars, the recent days with tokens and the model table", () => {
    const usage = { calls: 7, cost_usd: 0.3, prompt_tokens: 1200, completion_tokens: 300, unknown_cost_calls: 2 };
    render(
      <StatsPanel
        agentName={name}
        stats={{
          runs: 3, model_calls: 7, spent_usd: 0.3, unknown_cost_calls: 2, by_agent: { coach: 0.2, default: 0.1 }, by_model: { deepseek: 0.3 }, by_day: { "2026-09-19": 0.3 },
          days: [{ day: "2026-09-18", calls: 0, cost_usd: 0, prompt_tokens: 0, completion_tokens: 0, unknown_cost_calls: 0 }, { day: "2026-09-19", ...usage }],
          models: [{ model: "openrouter:deepseek", ...usage }],
          pending_proposals: 0,
        }}
      />,
    );
    const stats = screen.getByTestId("stats");
    expect(stats).toHaveTextContent("$0.30");
    expect(stats).toHaveTextContent("? 2");
    expect(stats).toHaveTextContent("HLV");
    const days = screen.getByTestId("stat-days");
    expect(days).toHaveTextContent("2026-09-19");
    expect(days).toHaveTextContent(vi.costCalls(7));
    expect(days).toHaveTextContent(vi.tokens(1200, 300));
    const models = screen.getByTestId("stat-models");
    expect(models).toHaveTextContent("openrouter:deepseek");
    expect(models).toHaveTextContent(vi.tokens(1200, 300));
    expect(models).toHaveTextContent("$0.30");
  });

  it("says when nothing has been spent", () => {
    render(<StatsPanel agentName={name} stats={{ runs: 0, model_calls: 0, spent_usd: 0, unknown_cost_calls: 0, by_agent: {}, by_model: {}, by_day: {}, days: [], models: [], pending_proposals: 0 }} />);
    expect(screen.getByText(vi.costEmpty)).toBeInTheDocument();
  });
});
