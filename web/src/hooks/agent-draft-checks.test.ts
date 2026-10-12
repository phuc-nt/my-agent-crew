import { describe, expect, it } from "vitest";
import { vi } from "../i18n/vi";
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

// What a script keeps is stored under its row's id, and a row sent without one is numbered
// by its place at every start, so the id of a script row is not left for the server to give.
describe("a row that runs a script and has no id", () => {
  const timed: ScheduleRow = { ...blankSchedule(), cron: "0 7 * * *" };
  const script = (id: string): ScheduleRow => ({ ...timed, id, prompt: null, script: "print(1)" });
  const found = (rows: ScheduleRow[], reveal: boolean) => draftProblems({ schedules: rows }, ["schedules"], {}, reveal);

  it.each(["", "   "])("holds the save, unnamed, until a save is tried (%j)", (id) => {
    expect(found([script(id)], false)).toEqual({ unfilled: true });
  });

  it.each(["", "   "])("is named at its id box once a save was tried (%j)", (id) => {
    expect(found([{ ...timed, prompt: "chào" }, script(id)], true)).toEqual({ schedules: { 1: { id: vi.editor.scheduleIdMissing } } });
  });

  it("is not a script with an id, nor a prompt or a command without one", () => {
    const rows = [script("orders"), { ...timed, prompt: "chào" }, { ...timed, prompt: null, command: "make backup" }];
    expect(found(rows, false)).toEqual({});
    expect(found(rows, true)).toEqual({});
  });

  it("is left alone on a form whose schedules nobody changed", () => {
    expect(draftProblems({ schedules: [script("")] }, [], {}, true)).toEqual({});
  });
});
