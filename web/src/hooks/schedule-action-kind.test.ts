import { describe, expect, it } from "vitest";
import { vi } from "../i18n/vi";
import { readSchedules } from "../test/schedule-contract";
import { draftProblems, hasProblems, problemsShown, toPatch } from "./agent-draft-checks";
import { same } from "./agent-draft-shape";
import { actionKind, blankSchedule, MAX_SCRIPT_CHARS, sendableRow, usesScript, type ScheduleRow } from "./schedule-row-shape";

const prompt: ScheduleRow = { id: "brief", name: "Bản tin", cron: "0 7 * * *", every: null, prompt: "Tóm tắt", command: null, script: null, then_prompt: null, enabled: true, skills: ["core"] };
const command: ScheduleRow = { ...prompt, id: "backup", prompt: null, command: "make backup", skills: [] };
const script: ScheduleRow = { ...prompt, id: "sync", prompt: null, script: "print(1)\n", then_prompt: "Tóm tắt đơn mới", skills: [] };
/** A row the form's choice has just turned into a script: nothing typed in it yet. */
const chosen: ScheduleRow = { ...prompt, id: "new", prompt: null, script: "", skills: [] };
const { script: _script, then_prompt: _then, ...older } = prompt;

const draft = (...schedules: ScheduleRow[]) => ({ schedules });
const found = (row: ScheduleRow, reveal = false) => draftProblems(draft(row), ["schedules"], {}, reveal);

describe("which of the three a row does", () => {
  it("is the one action the row holds", () => {
    expect([prompt, command, script, older, blankSchedule()].map(actionKind)).toEqual(["prompt", "command", "script", "prompt", "prompt"]);
  });

  // Chosen and not typed in yet, the row has to stay a script row or its box would vanish
  // under the person's cursor.
  it("is a script for a row switched to one, before anything is typed", () => {
    expect(actionKind(chosen)).toBe("script");
    expect(usesScript(chosen)).toBe(true);
  });

  // An empty script beside the action a row does is a stray key, not a choice.
  it("is not a script for an empty one beside a prompt or a command", () => {
    expect(actionKind({ ...prompt, script: "" })).toBe("prompt");
    expect(actionKind({ ...command, script: "" })).toBe("command");
    expect(actionKind({ ...command, command: "", script: null })).toBe("command");
  });
});

describe("what holds a save, for a script written in the form", () => {
  it("is an empty script: quietly at first, and named once a save is tried", () => {
    for (const blank of ["", "  \n\t"]) {
      const row = { ...chosen, script: blank };
      expect(found(row)).toEqual({ unfilled: true });
      expect(problemsShown(found(row))).toBe(false);
      expect(found(row, true)).toEqual({ schedules: { 0: { action: vi.editor.scriptMissing } } });
    }
  });

  // Each kind is told of its own box, never of the one beside it.
  it("names the box of the kind the row is", () => {
    expect(found({ ...prompt, prompt: "" }, true).schedules?.[0].action).toBe(vi.editor.promptMissing);
    expect(found({ ...command, command: "" }, true).schedules?.[0].action).toBe(vi.editor.commandMissing);
    expect(new Set([vi.editor.promptMissing, vi.editor.commandMissing, vi.editor.scriptMissing]).size).toBe(3);
  });

  it("is a script over the parser's bound, named at once and with the bound", () => {
    const atBound = { ...script, script: "x".repeat(MAX_SCRIPT_CHARS) };
    const over = { ...script, script: "x".repeat(MAX_SCRIPT_CHARS + 1) };
    expect(MAX_SCRIPT_CHARS).toBe(20_000);
    expect(found(atBound)).toEqual({});
    expect(found(over)).toEqual({ schedules: { 0: { action: vi.editor.scriptTooLong(MAX_SCRIPT_CHARS) } } });
    expect(vi.editor.scriptTooLong(MAX_SCRIPT_CHARS)).toContain("20.000");
    // The form's bound is the parser's: what one lets through the other takes.
    expect(readSchedules([sendableRow(atBound)])).toHaveProperty("ok");
    expect(readSchedules([sendableRow(over)])).toEqual({ error: "schedule sync: script is longer than 20000 characters" });
  });

  // Python counts characters; a string's length here counts an emoji as two.
  it("counts the bound in characters, as the parser does", () => {
    const emoji = { ...script, script: `print("${"😀".repeat(MAX_SCRIPT_CHARS - 9)}")` };
    expect(emoji.script?.length).toBeGreaterThan(MAX_SCRIPT_CHARS);
    expect(Array.from(emoji.script ?? "")).toHaveLength(MAX_SCRIPT_CHARS);
    expect(found(emoji)).toEqual({});
    expect(hasProblems(found({ ...emoji, script: `${emoji.script}#` }))).toBe(true);
  });

  it("is not a prompt to follow left blank, which is sent as no prompt at all", () => {
    for (const blank of [null, "", "  \n"]) {
      const row = { ...script, then_prompt: blank };
      expect(found(row, true)).toEqual({});
      expect(sendableRow(row)).not.toHaveProperty("then_prompt");
      expect(readSchedules([sendableRow(row)])).toHaveProperty("ok");
    }
  });
});

describe("a row switched from one kind to another, as it is sent", () => {
  // The parser takes exactly one of the three, and a prompt to follow only beside a script.
  it("carries the one action it now does, whatever its other keys still hold", () => {
    const rows = [
      { ...prompt, script: "", then_prompt: null },
      { ...command, script: "", then_prompt: "Tóm tắt" },
      { ...script, prompt: "Tóm tắt", command: "make backup" },
    ];
    const sent = toPatch(draft(...rows), ["schedules"]).schedules as Record<string, unknown>[];
    const actions = (row: Record<string, unknown>) => ["prompt", "command", "script", "then_prompt"].filter((key) => key in row);
    expect(sent.map(actions)).toEqual([["prompt"], ["command"], ["script", "then_prompt"]]);
    expect(readSchedules(sent)).toHaveProperty("ok");
  });
});

describe("whether a row was changed", () => {
  // Switched to a script and back, a row from an older server holds two keys it came
  // without, both null: that is the row the file has, and there is nothing to save.
  it("is not for the two script keys held as null where the file has none", () => {
    expect(same([{ ...older, script: null, then_prompt: null }], [older])).toBe(true);
    expect(same([older], [prompt])).toBe(true);
  });

  it("is for a script, or a prompt to follow, that is there", () => {
    expect(same([{ ...older, script: "" }], [older])).toBe(false);
    expect(same([script], [{ ...script, then_prompt: null }])).toBe(false);
    expect(same([script], [{ ...script, script: "print(2)\n" }])).toBe(false);
  });

  // The null of any other key is a value: a cleared route is not a route left alone.
  it("still tells a null from a value everywhere else", () => {
    expect(same({ escalation_route: null }, { escalation_route: { provider: "fake", model: "echo" } })).toBe(false);
    expect(same([{ ...prompt, command: null }], [{ ...prompt, command: "" }])).toBe(false);
  });
});
