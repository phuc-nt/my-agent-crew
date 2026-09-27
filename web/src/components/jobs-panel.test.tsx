import { act, render, screen, within } from "@testing-library/react";
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

    // On the row and read out with the switch: a hover title is never shown on a phone
    // and never reaches a screen reader.
    const job = screen.getByTestId("job");
    expect(within(job).getByText(vi.jobDisabledInProfile)).toBeVisible();
    expect(within(job).getByRole("checkbox")).toHaveAccessibleDescription(vi.jobDisabledInProfile);
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
    vitest.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] });
    // 04:00 on the 27th in Hanoi, where the suite runs.
    vitest.setSystemTime(new Date("2026-09-26T21:00:00Z"));
    // The scheduler writes its own clock, the owner's, to the minute and with no offset;
    // read as UTC, 07:00 would move seven hours later.
    const soon = { ...brief, next_run: "2026-09-27T07:00" };
    const later = { ...brief, id: "coach/later", next_run: "2026-09-29T07:00" };
    const panel = <JobsPanel jobs={[soon, later]} agentName={name} onRunNow={() => {}} onToggle={() => {}} />;
    const { rerender } = render(panel);

    const [first, second] = screen.getAllByTestId("job");
    const next = within(first).getByText("sau 3 giờ");
    expect(next).toHaveAttribute("title", formatDateTime(soon.next_run));
    expect(second).toHaveTextContent("29/09 07:00");

    // A list left open keeps counting, rather than promising three hours all morning.
    act(() => vitest.advanceTimersByTime((2 * 60 + 1) * 60_000));
    expect(within(first).getByText("sau 59 phút")).toBeInTheDocument();
    rerender(<></>);
    expect(vitest.getTimerCount()).toBe(0);
  });

  // A title shows on hover, and a phone never hovers: "sau 3 giờ" alone left the sum to the
  // person, and "Hôm qua" said nothing of when.
  it("prints the clock time beside the next and the last run, once", () => {
    vitest.useFakeTimers({ toFake: ["Date"] });
    vitest.setSystemTime(new Date("2026-09-26T21:00:00Z"));
    const ran = fakeRun({ started_at: "2026-09-26T18:00:00Z" });
    const soon = { ...brief, next_run: "2026-09-27T07:00", last_run: ran };
    const later = { ...brief, id: "coach/later", next_run: "2026-09-29T07:00" };
    const yesterday = { ...brief, id: "coach/y", last_run: fakeRun({ started_at: "2026-09-26T01:30:00Z" }) };
    render(<JobsPanel jobs={[soon, later, yesterday]} agentName={name} onRunNow={() => {}} onToggle={() => {}} />);

    const [first, second, third] = screen.getAllByTestId("job");
    expect(first).toHaveTextContent(`${vi.jobNext}: sau 3 giờ, lúc 07:00`);
    expect(within(first).getByTestId("job-last")).toHaveTextContent("3 giờ, lúc 01:00");
    // A later day's date already carries its time.
    expect(second).toHaveTextContent(`${vi.jobNext}: 29/09 07:00 ·`);
    expect(within(third).getByTestId("job-last")).toHaveTextContent("Hôm qua, lúc 08:30");
  });

  // An interval job's next run is its last run plus the interval, so one switched off for
  // days reports a time long gone, which a countdown read as "sắp tới".
  it("gives a job that will not run no next time, however far behind its last it is", () => {
    vitest.useFakeTimers({ toFake: ["Date"] });
    vitest.setSystemTime(new Date("2026-09-26T21:00:00Z"));
    const stale = { ...brief, cron: null, every: "1h", next_run: "2026-09-24T07:00", enabled: false };
    const paused = { ...stale, id: "coach/paused", paused: true };
    const soon = { ...brief, id: "coach/soon", next_run: "2026-09-27T07:00" };
    render(<JobsPanel jobs={[stale, paused, soon]} agentName={name} onRunNow={() => {}} onToggle={() => {}} />);

    const [off, held, on] = screen.getAllByTestId("job");
    for (const row of [off, held]) {
      expect(row).not.toHaveTextContent(vi.time.soon);
      expect(within(row).queryByText(/\d\d:\d\d/)).not.toBeInTheDocument();
    }
    expect(off).toHaveTextContent(`${vi.jobNext}: ${vi.jobDisabled}`);
    expect(held).toHaveTextContent(`${vi.jobNext}: ${vi.jobPaused}`);
    expect(on).toHaveTextContent(`${vi.jobNext}: sau 3 giờ`);
  });

  it("shows how the last run ended and what it said, and opens that run", async () => {
    vitest.useFakeTimers({ toFake: ["Date"] });
    vitest.setSystemTime(new Date("2026-09-26T21:00:00Z"));
    const onOpenRun = vitest.fn();
    const lastRun = fakeRun({
      id: "r-err",
      status: "error",
      summary: "Không gọi được API",
      started_at: "2026-09-26T18:00:00Z",
    });
    const failed = { ...brief, last_run: lastRun };
    const weekAgo = { ...brief, id: "coach/week", last_run: fakeRun({ started_at: "2026-09-19T08:00:00Z" }) };
    const never = { ...brief, id: "coach/never", last_run: null };
    const jobs = [failed, weekAgo, never];
    render(<JobsPanel jobs={jobs} agentName={name} onRunNow={() => {}} onToggle={() => {}} onOpenRun={onOpenRun} />);

    const [ran, older, idle] = screen.getAllByTestId("job-last");
    expect(within(ran).getByText(vi.runStatus.error)).toHaveClass("badge", "danger");
    expect(ran).toHaveTextContent("Không gọi được API");
    // Read the way the next run is, with the exact date and time in its title too.
    expect(within(ran).getByText("3 giờ")).toHaveAttribute("title", formatDateTime(lastRun.started_at));
    expect(within(older).getByText("19/09")).toHaveAttribute("dateTime", "2026-09-19T08:00:00Z");
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
