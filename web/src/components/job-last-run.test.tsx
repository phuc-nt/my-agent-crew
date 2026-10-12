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
  origin: "profile",
};

function streak(failing: JobFailing | null | undefined): string | null {
  const job = failing === undefined ? brief : { ...brief, failing };
  render(<JobLastRun job={job} now={now} />);
  return within(screen.getByTestId("job-last")).queryByTestId("job-failing")?.textContent ?? null;
}

describe("a job that keeps failing, said on its row", () => {
  it("says how many runs in a row failed, when the owner was told and when it is told again", () => {
    const told = { count: 3, since: at(11, 7), told_at: at(12, 7, 1), next_notice_at: at(13, 7, 1), telling: false };
    expect(streak(told)).toBe(
      "Hỏng 3 lần liên tiếp từ Hôm qua 07:00. Đã báo Telegram lúc 07:01; còn hỏng thì nhắc lại sau 13/10 07:01.",
    );
  });

  it("says a notice has not got through yet, and that the next failure tries again", () => {
    const untold = { count: 2, since: at(9, 22, 5), told_at: null, next_notice_at: null, telling: false };
    expect(streak(untold)).toBe(
      "Hỏng 2 lần liên tiếp từ 09/10 22:05. Chưa báo được qua Telegram; lần hỏng kế tiếp sẽ thử lại.",
    );
  });

  // The page reads the row when the run ends, and Telegram answers a moment after that.
  it("says a notice is on its way while Telegram has not answered", () => {
    const telling = { count: 1, since: at(12, 7), told_at: null, next_notice_at: null, telling: true };
    expect(streak(telling)).toBe("Hỏng từ 07:00. Đang báo qua Telegram.");
  });

  it("goes on saying when the owner was told while a later notice is on its way", () => {
    const again = { count: 9, since: at(11, 7), told_at: at(12, 1, 1), next_notice_at: at(12, 7, 1), telling: true };
    expect(streak(again)).toBe(
      "Hỏng 9 lần liên tiếp từ Hôm qua 07:00. Đã báo Telegram lúc 01:01; còn hỏng thì nhắc lại sau 07:01.",
    );
  });

  it("does not call one failed run a streak of runs", () => {
    const once = { count: 1, since: at(12, 7), told_at: at(12, 7, 1), next_notice_at: at(12, 13, 1), telling: false };
    expect(streak(once)).toBe("Hỏng từ 07:00. Đã báo Telegram lúc 07:01; còn hỏng thì nhắc lại sau 13:01.");
  });

  // The type lets a notice be told with no time for the next one; the sentence ends at
  // what is known rather than naming a time that is not there.
  it("stops at when the owner was told if the server names no time for the next notice", () => {
    const told = { count: 4, since: at(11, 7), told_at: at(12, 7, 1), next_notice_at: null, telling: false };
    expect(streak(told)).toBe("Hỏng 4 lần liên tiếp từ Hôm qua 07:00. Đã báo Telegram lúc 07:01.");
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
    render(<JobLastRun job={{ ...brief, last_run: null, failing: { count: 1, since: at(12, 7), told_at: null, next_notice_at: null, telling: false } }} now={now} />);
    expect(screen.getByTestId("job-failing")).toHaveTextContent("Hỏng từ 07:00.");
  });
});
