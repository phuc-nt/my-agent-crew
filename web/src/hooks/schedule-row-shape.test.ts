import { describe, expect, it } from "vitest";
import { readSchedules } from "../test/schedule-contract";
import { draftProblems, hasProblems, toPatch } from "./agent-draft-checks";
import { blankSchedule, sendableRow, usesCommand, usesScript, type ScheduleRow } from "./schedule-row-shape";

const SOURCE = 'orders = tools.workspace_read(path="orders.json")\nprint(len(orders))\n';
const prompt: ScheduleRow = { id: "brief", name: "Bản tin", cron: "0 7 * * *", every: null, prompt: "Tóm tắt", command: null, script: null, then_prompt: null, enabled: true, skills: ["core"] };
const command: ScheduleRow = { ...prompt, id: "backup", name: "Sao lưu", prompt: null, command: "make backup", skills: [] };
const script: ScheduleRow = { ...prompt, id: "sync", name: "Đồng bộ", prompt: null, script: SOURCE, then_prompt: "Tóm tắt đơn mới", skills: [] };

describe("which rows run a script", () => {
  it("is a row the file declared with a script, and no other", () => {
    expect(usesScript(script)).toBe(true);
    expect(usesScript({ ...script, then_prompt: null })).toBe(true);
    expect(usesScript(prompt)).toBe(false);
    expect(usesScript(command)).toBe(false);
    // A row from a server older than script jobs has no such key at all.
    const { script: _script, then_prompt: _then, ...older } = prompt;
    expect(usesScript(older)).toBe(false);
    // The form makes rows that nudge or run a command; a new one is never a script.
    expect(usesScript(blankSchedule())).toBe(false);
    expect(blankSchedule()).not.toHaveProperty("script");
  });

  // Both carry `prompt: null`; only the script tells them apart, and it is asked first.
  it("is not taken for a command row for having no prompt", () => {
    expect(usesCommand(script)).toBe(false);
    expect(usesCommand(command)).toBe(true);
  });
});

describe("a script row as it is sent back", () => {
  it("carries its script and the prompt to follow as they came, and neither a prompt nor a command", () => {
    expect(sendableRow(script)).toEqual({ id: "sync", name: "Đồng bộ", cron: "0 7 * * *", script: SOURCE, then_prompt: "Tóm tắt đơn mới", enabled: true, skills: [] });
  });

  // Indentation and the last line break are part of a script; a prompt's are not kept either way.
  it("sends the script character for character", () => {
    const spaced = "\n  if True:\n\tprint(1)  \n\n";
    expect(sendableRow({ ...script, script: spaced }).script).toBe(spaced);
  });

  it("leaves out the prompt to follow when the script has none", () => {
    for (const none of [null, undefined]) {
      const sent = sendableRow({ ...script, then_prompt: none });
      expect(sent).not.toHaveProperty("then_prompt");
      expect(sent.script).toBe(SOURCE);
    }
  });

  // A stray value in a box the row does not use must not ride along: the parser takes
  // exactly one action, and two would refuse the whole save.
  it("sends neither a prompt nor a command even when the row somehow holds one", () => {
    const sent = sendableRow({ ...script, prompt: "Tóm tắt", command: "make backup" });
    expect(sent).not.toHaveProperty("prompt");
    expect(sent).not.toHaveProperty("command");
    expect(sent.script).toBe(SOURCE);
  });

  it("keeps the timing, the switch, the skills and how long its approvals wait", () => {
    const sent = sendableRow({ ...script, cron: null, every: "6h", enabled: false, skills: ["core"], approval_ttl_seconds: 7200 });
    expect(sent).toEqual({ id: "sync", name: "Đồng bộ", every: "6h", script: SOURCE, then_prompt: "Tóm tắt đơn mới", enabled: false, skills: ["core"], approval_ttl_seconds: 7200 });
  });

  it("is what the parser takes, and reads back as the row it was", () => {
    const read = readSchedules([sendableRow(script), sendableRow({ ...script, id: "quiet", then_prompt: null })]);
    expect(read).toEqual({
      ok: [
        { ...script, approval_ttl_seconds: null },
        { ...script, id: "quiet", then_prompt: null, approval_ttl_seconds: null },
      ],
    });
  });
});

describe("the rows that run no script, as they are sent back", () => {
  // Declared with both keys null by a server that knows script jobs: sending a null
  // `then_prompt` beside a prompt is the one thing the parser refuses there.
  it("carry neither script key, whether these came as null or did not come", () => {
    const { script: _script, then_prompt: _then, ...older } = prompt;
    for (const row of [prompt, older, command]) {
      const sent = sendableRow(row);
      expect(sent).not.toHaveProperty("script");
      expect(sent).not.toHaveProperty("then_prompt");
    }
    expect(sendableRow(prompt)).toEqual({ id: "brief", name: "Bản tin", cron: "0 7 * * *", prompt: "Tóm tắt", enabled: true, skills: ["core"] });
    expect(sendableRow(command)).toEqual({ id: "backup", name: "Sao lưu", cron: "0 7 * * *", command: "make backup", enabled: true, skills: [] });
    expect(sendableRow(prompt)).toEqual(sendableRow(older));
  });

  // A prompt to follow has nothing to follow here, and is not this row's to send.
  it("do not send a prompt to follow left on a row with no script", () => {
    expect(sendableRow({ ...prompt, then_prompt: "Tóm tắt" })).not.toHaveProperty("then_prompt");
    expect(sendableRow({ ...prompt, script: "" })).not.toHaveProperty("script");
  });
});

describe("what holds a save, for a row that runs a script", () => {
  const draft = (...schedules: ScheduleRow[]) => ({ schedules });

  // Revealed, as after a save was tried: this is when a blank action is named.
  it("is not its missing prompt or command", () => {
    expect(draftProblems(draft(script), ["schedules"], {}, true)).toEqual({});
    expect(draftProblems(draft(script), ["schedules"])).toEqual({});
    expect(hasProblems(draftProblems(draft(script, prompt, command), ["schedules"], {}, true))).toBe(false);
  });

  it("is still a timing the scheduler would refuse", () => {
    const found = draftProblems(draft({ ...script, cron: "lúc 7 giờ" }), ["schedules"], {}, true);
    expect(Object.keys(found.schedules?.[0] ?? {})).toEqual(["timing"]);
  });

  // The check that lets a script row through must not let an ordinary blank row through.
  it("is still the blank box of a row beside it", () => {
    const found = draftProblems(draft(script, { ...prompt, prompt: " " }), ["schedules"], {}, true);
    expect(Object.keys(found.schedules ?? {})).toEqual(["1"]);
    expect(Object.keys(found.schedules?.[1] ?? {})).toEqual(["action"]);
  });

  it("leaves the whole list sendable: the script row among the others, in its place", () => {
    const patch = toPatch(draft(prompt, script, command), ["schedules"]);
    const sent = patch.schedules as Record<string, unknown>[];
    expect(sent.map((row) => row.id)).toEqual(["brief", "sync", "backup"]);
    expect(sent[1]).toEqual(sendableRow(script));
    expect(readSchedules(sent)).toHaveProperty("ok");
  });
});
