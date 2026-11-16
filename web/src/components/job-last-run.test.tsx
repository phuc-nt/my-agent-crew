import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { JobFailing, JobInfo } from "../api/types";
import { coachAgent, fakeRun } from "../test/fake-backend";
import { JobLastRun } from "./job-last-run";

// Times are built from local clock fields, so each sentence reads the same in whatever
// zone the suite runs. "Now" is 09:30 on 12 October.
const at = (day: number, hour: number, minute = 0) => new Date(2026, 9, day, hour, minute).toISOString();
const now = new Date(2026, 9, 12, 9, 30);

const brief: JobInfo = {
  ...coachAgent.schedules[0],
  id: "coach/brief",
  schedule_id: "brief",
  agent_id: "coach",
  next_run: null,
  last_run: fakeRun({ id: "r-err", status: "error", started_at: at(12, 7), summary: "Hết hạn cookie." }),
  running: false,
  paused: false,
};

function streak(failing: JobFailing | null | undefined): string | null {
  const job = failing === undefined ? brief : { ...brief, failing };
  render(<JobLastRun job={job} now={now} />);
  return within(screen.getByTestId("job-last")).queryByTestId("job-failing")?.textContent ?? null;
}

describe("a job that keeps failing, said on its row", () => {
  it("says how many runs in a row failed and since when, and nothing of anyone told", () => {
    const streaked = { count: 3, since: at(11, 7) };
    expect(streak(streaked)).toBe("Hỏng 3 lần liên tiếp từ Hôm qua 07:00.");
  });

  it("dates a streak begun before yesterday", () => {
    expect(streak({ count: 2, since: at(9, 22, 5) })).toBe("Hỏng 2 lần liên tiếp từ 09/10 22:05.");
  });

  it("does not call one failed run a streak of runs", () => {
    expect(streak({ count: 1, since: at(12, 7) })).toBe("Hỏng từ 07:00.");
  });

  // A server from before the notices were dropped still sends what it told; the line
  // reads none of it.
  it("says nothing of a notice an older server names", () => {
    const older = { count: 1, since: at(12, 7), told_at: at(12, 7, 1), next_notice_at: null, telling: true };
    expect(streak(older)).toBe("Hỏng từ 07:00.");
  });

  it("says nothing on a row whose job is in no streak, although its last run failed", () => {
    expect(streak(null)).toBeNull();
    expect(screen.getByTestId("job-last")).toHaveTextContent("Hết hạn cookie.");
  });

  it("says nothing when an older server leaves the key out", () => {
    expect("failing" in brief).toBe(false);
    expect(streak(undefined)).toBeNull();
  });

  it("puts the sentence under a job that has never finished a run as well", () => {
    render(<JobLastRun job={{ ...brief, last_run: null, failing: { count: 1, since: at(12, 7) } }} now={now} />);
    expect(screen.getByTestId("job-failing")).toHaveTextContent("Hỏng từ 07:00.");
  });
});
