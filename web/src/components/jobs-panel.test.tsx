import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import type { JobInfo } from "../api/activity-types";
import { vi } from "../i18n/vi";
import { FakeBackend, coachAgent, fakeRun } from "../test/fake-backend";
import { failingJobs } from "./job-last-run";
import { JobsPanel } from "./jobs-panel";
import { formatDateTime } from "./run-timeline";

const name = (id: string) => (id === "coach" ? "HLV" : "Agent");
const brief: JobInfo = {
  ...coachAgent.schedules[0],
  id: "coach/brief",
  schedule_id: "brief",
  agent_id: "coach",
  next_run: null,
  last_run: null,
  running: false,
  paused: false,
};

describe("where the jobs list sends a person to change a schedule", () => {
  it("opens the agent's editor from the job's own edit button", async () => {
    const onEdit = vitest.fn();
    render(
      <JobsPanel jobs={[brief]} agentName={name} onRunNow={() => {}} onToggle={() => {}} onEditSchedules={onEdit} />,
    );

    const job = screen.getByTestId("job");
    await userEvent.click(within(job).getByRole("button", { name: vi.jobRow.editOf(brief.name) }));
    expect(onEdit).toHaveBeenCalledWith("coach");
  });

  // Schedules used to be added by hand in agent.yaml, and the empty list said so; the
  // editor adds them now, and the empty list is the place a person first looks.
  it("points an empty list at the crew, where schedules are added, not at a file", async () => {
    const onOpenCrew = vitest.fn();
    render(<JobsPanel jobs={[]} agentName={name} onRunNow={() => {}} onToggle={() => {}} onOpenCrew={onOpenCrew} />);

    expect(screen.getByText(vi.jobsEmpty)).not.toHaveTextContent("agent.yaml");
    await userEvent.click(screen.getByRole("button", { name: vi.jobRow.openCrew }));
    expect(onOpenCrew).toHaveBeenCalled();
  });

  it("tells a schedule switched off in its profile to be turned back on in the editor", () => {
    render(
      <JobsPanel
        jobs={[{ ...brief, enabled: false }]}
        agentName={name}
        onRunNow={() => {}}
        onToggle={() => {}}
        onEditSchedules={() => {}}
      />,
    );

    const toggle = within(screen.getByTestId("job")).getByRole("checkbox").closest("label");
    expect(toggle).toHaveAttribute("title", vi.jobDisabledInProfile);
    expect(vi.jobDisabledInProfile).not.toContain("agent.yaml");
    expect(vi.jobDisabledInProfile).toContain(vi.jobRow.edit);
  });
});

describe("a job read at a glance", () => {
  afterEach(() => {
    vitest.useRealTimers();
    vitest.unstubAllGlobals();
  });

  it("says when a job runs in words and keeps the schedule it was written as beside them", () => {
    const every: JobInfo = { ...brief, id: "coach/sync", cron: null, every: "30m" };
    const odd: JobInfo = { ...brief, id: "coach/odd", cron: "0 7 * 1 *" };
    render(<JobsPanel jobs={[brief, every, odd]} agentName={name} onRunNow={() => {}} onToggle={() => {}} />);

    const [daily, interval, raw] = screen.getAllByTestId("job");
    expect(daily).toHaveTextContent("Mỗi ngày 07:00");
    expect(within(daily).getByText("0 7 * * *").tagName).toBe("CODE");
    expect(interval).toHaveTextContent("Mỗi 30 phút");
    // No words for it, so the cron is shown once and not paraphrased.
    expect(within(raw).getAllByText("0 7 * 1 *")).toHaveLength(1);
  });

  it("counts down to the next run on the viewer's clock and keeps the exact time on hover", () => {
    vitest.useFakeTimers({ toFake: ["Date"] });
    vitest.setSystemTime(new Date("2026-09-26T21:00:00Z"));
    const soon = { ...brief, next_run: "2026-09-27T00:00:00Z" };
    const later = { ...brief, id: "coach/later", next_run: "2026-09-29T00:00:00Z" };
    render(<JobsPanel jobs={[soon, later]} agentName={name} onRunNow={() => {}} onToggle={() => {}} />);

    const [first, second] = screen.getAllByTestId("job");
    const next = within(first).getByText("sau 3 giờ");
    expect(next).toHaveAttribute("title", formatDateTime(soon.next_run));
    // 00:00 UTC is 07:00 in Hanoi, where the suite runs.
    expect(second).toHaveTextContent("29/09 07:00");
  });

  it("shows how the last run ended and what it said, and opens that run", async () => {
    const onOpenRun = vitest.fn();
    const failed = { ...brief, last_run: fakeRun({ id: "r-err", status: "error" as const, summary: "Không gọi được API" }) };
    const never = { ...brief, id: "coach/never", last_run: null };
    render(
      <JobsPanel jobs={[failed, never]} agentName={name} onRunNow={() => {}} onToggle={() => {}} onOpenRun={onOpenRun} />,
    );

    const [ran, idle] = screen.getAllByTestId("job-last");
    expect(within(ran).getByText(vi.runStatus.error)).toHaveClass("badge", "danger");
    expect(ran).toHaveTextContent("Không gọi được API");
    expect(ran).toHaveTextContent(formatDateTime(failed.last_run.started_at));
    // The same words the run cards in the history use for the same page.
    const open = within(ran).getByRole("button", { name: vi.jobRow.openRunOf(brief.name) });
    expect(open).toHaveTextContent(vi.replay.openLink);
    await userEvent.click(open);
    expect(onOpenRun).toHaveBeenCalledWith("r-err");

    expect(idle).toHaveTextContent(vi.jobNever);
    expect(within(idle).queryByRole("button")).not.toBeInTheDocument();
  });

  it("opens a run from the job's history on its own page", async () => {
    const backend = new FakeBackend();
    backend.runs = [fakeRun({ id: "h1", source: "job:coach/brief", agent_id: "coach", summary: "Bản tin hôm qua" })];
    vitest.stubGlobal("fetch", backend.fetch);
    const onOpenRun = vitest.fn();
    render(<JobsPanel jobs={[brief]} agentName={name} onRunNow={() => {}} onToggle={() => {}} onOpenRun={onOpenRun} />);

    await userEvent.click(screen.getByRole("button", { name: vi.showHistory }));
    const history = await screen.findByTestId("job-runs");
    await userEvent.click(within(history).getByRole("button", { expanded: false }));
    await userEvent.click(within(history).getByRole("button", { name: vi.replay.openLink }));
    expect(onOpenRun).toHaveBeenCalledWith("h1");
  });

  it("counts only the jobs whose latest run failed", () => {
    const ran = (status: "done" | "error" | "halted" | "running") => ({ ...brief, last_run: fakeRun({ status }) });
    expect(failingJobs(null)).toBe(0);
    expect(failingJobs([brief, ran("done"), ran("halted"), ran("running")])).toBe(0);
    expect(failingJobs([ran("error"), ran("done"), ran("error")])).toBe(2);
  });
});
