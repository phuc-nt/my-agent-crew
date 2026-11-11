import { describe, expect, it } from "vitest";
import { draftProblems, isCron } from "./agent-draft-checks";
import { blankSchedule, type ScheduleRow } from "./schedule-row-shape";

// The same grammar and ranges as the scheduler's CronSpec.parse, so what the form lets
// through is what the server takes and what it holds back the server would refuse.
describe("a cron the form lets through", () => {
  it.each([
    "0 7 * * *",
    "*/15 * * * *",
    "0 9-17 * * 1-5",
    "30 6 1,15 * *",
    "0 0 * * 7",
    "0-59/5 * * * *",
    "5/10 * * * *",
    "59 23 31 12 0",
  ])("takes %s", (cron) => {
    expect(isCron(cron)).toBe(true);
  });

  it.each([
    "0 25 * * *",
    "60 * * * *",
    "0 7 0 * *",
    "0 7 32 * *",
    "0 7 * 13 *",
    "0 7 * * 8",
    "*/0 * * * *",
    "5-1 * * * *",
    "0 7 * *",
    "0 7 * * * *",
    "a b c d e",
    "0,,5 * * * *",
  ])("refuses %s", (cron) => {
    expect(isCron(cron)).toBe(false);
  });
});

// A row sent without an id is numbered by the server, whatever the row runs.
describe("a row that has no id", () => {
  const timed: ScheduleRow = { ...blankSchedule(), cron: "0 7 * * *" };
  const script = (id: string): ScheduleRow => ({ ...timed, id, prompt: null, script: "print(1)" });
  const found = (rows: ScheduleRow[], reveal: boolean) => draftProblems({ schedules: rows }, ["schedules"], {}, reveal);

  it.each(["", "   "])("holds nothing, before a save is tried or after, whether it runs a script, a prompt or a command (%j)", (id) => {
    const rows = [script(id), { ...timed, id, prompt: "chào" }, { ...timed, id, prompt: null, command: "make backup" }];
    expect(found(rows, false)).toEqual({});
    expect(found(rows, true)).toEqual({});
  });
});
